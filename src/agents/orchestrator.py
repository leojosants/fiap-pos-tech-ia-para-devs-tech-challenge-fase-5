"""Orquestrador do agente CasaLead.

Coordena o processamento de um turno de conversa, delegando cada
responsabilidade ao agente apropriado e persistindo o resultado.

Fronteira arquitetural: é a única porta de entrada do domínio. A camada
de interface não conhece agentes, repositórios ou LLM — envia uma
mensagem e recebe um resultado pronto para exibição. Isso permite que a
mesma lógica sirva ao Streamlit hoje e a uma API REST ou integração com
WhatsApp amanhã, sem alteração.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.conversation_agent import ConversationAgent, RespostaAgente
from src.agents.qualification_agent import QualificationAgent, ResultadoQualificacao
from src.agents.scheduling_agent import ResultadoAgendamento, SchedulingAgent
from src.core.enums import (
    ConversationStatus,
    EventType,
    Intent,
    LeadStatus,
    LeadTemperature,
    MessageRole,
)
from src.core.models import Conversation, Lead, Message
from src.followup.followup_manager import FollowupManager, ResultadoFollowup
from src.llm.groq_client import GroqClient
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository
from src.recommendation.ranker import PropertyRanker, ResultadoRecomendacao
from src.persistence.property_repository import PropertyRepository
from src.reporting.summarizer import ResumoGerado, Summarizer
from src.scoring import calcular_score
from src.scoring.builder import construir_contexto

logger = logging.getLogger(__name__)

# Termos que indicam a intenção de forma explícita no texto do lead.
# Sua ausência, quando o modelo mesmo assim infere uma intenção, indica
# que a inferência veio de contexto e merece confirmação.
_TERMOS_EXPLICITOS = re.compile(
    r"\bcompr|\badquirir\b|\bfinanci|"
    r"\balug|\blocar\b|\bloca[çc][ãa]o\b|"
    r"\binvest|\brenda\b|\brentabilidade\b|\brentab|\bvaloriza",
    re.IGNORECASE,
)

_CONFIRMACAO_INTENCAO = (
    "Só para eu te ajudar direito: você está pensando em comprar, "
    "alugar ou investir?"
)


@dataclass
class ResultadoTurno:
    """Tudo que a interface precisa saber sobre um turno processado."""

    resposta: str
    lead: Lead
    conversation_id: int

    origem_resposta: str = ""
    slots_atualizados: dict = field(default_factory=dict)
    intent_identificada: Intent | None = None
    intencao_confirmada: bool = False
    divergencias: list[str] = field(default_factory=list)

    recomendacao: ResultadoRecomendacao | None = None
    agendamento: ResultadoAgendamento | None = None

    latencia_total_ms: int = 0
    usou_llm: bool = False
    houve_degradacao: bool = False

    @property
    def completude(self) -> float:
        return self.lead.completude()

    @property
    def qualificacao_completa(self) -> bool:
        return self.completude >= 1.0


class Orchestrator:
    """Coordena o fluxo de atendimento."""

    def __init__(
        self,
        db_path: Path | None = None,
        cliente: GroqClient | None = None,
    ) -> None:
        self._cliente = cliente or GroqClient()
        self._leads = LeadRepository(db_path)
        self._conversas = ConversationRepository(db_path)
        self._imoveis = PropertyRepository(db_path)  # NOVO — usado pelo scoring
        self._qualificacao = QualificationAgent(self._cliente)
        self._conversacao = ConversationAgent(self._cliente)
        self._ranker = PropertyRanker(self._imoveis)

        # Compartilhado entre SchedulingAgent e Summarizer — ambos só
        # leem/gravam a tabela appointments, sem estado próprio que
        # justifique instâncias separadas.
        self._agendamentos_repo = AppointmentRepository(db_path)
        self._agendamento = SchedulingAgent(self._agendamentos_repo)
        self._resumo = Summarizer(self._cliente, self._agendamentos_repo)
        self._followup = FollowupManager(
            FollowupRepository(db_path), self._conversas, self._leads
        )

    # --------------------------------------------------------
    # Abertura de atendimento
    # --------------------------------------------------------

    def iniciar_atendimento(
        self, *, canal: str = "web", nome: str = ""
    ) -> tuple[Lead, Conversation, str]:
        """Cria um lead e abre uma conversa, devolvendo a saudação.

        Retorna a tupla (lead, conversa, saudação) para que a interface
        exiba a primeira mensagem sem precisar de um turno de ida e volta.
        """
        lead = self._leads.criar(Lead(nome=nome, canal_origem=canal))
        conversa = self._conversas.criar_conversa(
            Conversation(lead_id=lead.id, canal=canal)
        )

        self._conversas.registrar_evento(
            EventType.LEAD_CRIADO, lead_id=lead.id, canal=canal
        )
        self._conversas.registrar_evento(
            EventType.CONVERSA_INICIADA,
            lead_id=lead.id,
            conversation_id=conversa.id,
        )

        saudacao = self._conversacao.saudacao()
        self._conversas.adicionar_mensagem(
            Message(
                conversation_id=conversa.id,
                role=MessageRole.AGENT,
                content=saudacao,
            )
        )

        return lead, conversa, saudacao

    def retomar_atendimento(self, lead_id: int) -> tuple[Lead, Conversation] | None:
        """Recupera o lead e sua conversa em aberto.

        Base da continuidade e do follow-up: o atendimento prossegue de
        onde parou, com o histórico preservado.
        """
        lead = self._leads.buscar_por_id(lead_id)
        if lead is None:
            return None

        conversa = self._conversas.conversa_ativa_do_lead(lead_id)
        if conversa is None:
            conversa = self._conversas.criar_conversa(
                Conversation(lead_id=lead_id)
            )

        return lead, conversa

    # --------------------------------------------------------
    # Processamento de turno
    # --------------------------------------------------------

    def processar_mensagem(
        self, lead_id: int, conversation_id: int, texto: str
    ) -> ResultadoTurno:
        """Processa uma mensagem do lead e devolve a resposta do agente.

        Executa, em ordem: persistência da entrada, qualificação,
        persistência do estado, geração da resposta e persistência da
        saída. Cada etapa gera eventos de observabilidade.
        """
        lead = self._leads.buscar_por_id(lead_id)
        if lead is None:
            raise ValueError(f"Lead {lead_id} não encontrado.")

        texto = texto.strip()
        if not texto:
            raise ValueError("Mensagem vazia.")

        # [1] Persistir a entrada
        self._conversas.adicionar_mensagem(
            Message(
                conversation_id=conversation_id,
                role=MessageRole.LEAD,
                content=texto,
            )
        )
        self._conversas.registrar_evento(
            EventType.MENSAGEM_RECEBIDA,
            lead_id=lead_id,
            conversation_id=conversation_id,
            caracteres=len(texto),
        )

        # [2] Qualificar
        intent_antes = lead.intent
        qualificacao = self._qualificacao.qualificar(lead, texto)

        precisa_confirmar = self._deve_confirmar_intencao(
            intent_antes, lead.intent, texto, qualificacao
        )

        # [3] Persistir estado e eventos
        self._atualizar_status(lead)
        self._leads.atualizar(lead)
        self._registrar_eventos_qualificacao(
            qualificacao, lead_id, conversation_id
        )

        # [4] Recomendar imóveis, quando houver critérios suficientes
        recomendacao = self._recomendar_se_possivel(
            lead, lead_id, conversation_id
        )
        imoveis_contexto = (
            self._ranker.formatar_para_prompt(recomendacao)
            if recomendacao
            else ""
        )

        # [4.5] Agendar, quando a disponibilidade permitir
        agendamento = self._agendar_se_possivel(
            lead, lead_id, conversation_id, texto
        )
        agendamento_contexto = self._agendamento.formatar_para_prompt(agendamento)

        # [5] Gerar a resposta
        if precisa_confirmar:
            resposta = self._responder_confirmando_intencao(lead)
        else:
            historico = self._conversas.historico_para_llm(conversation_id)
            resposta = self._conversacao.responder(
                lead,
                texto,
                historico,
                imoveis_contexto=imoveis_contexto,
                agendamento_contexto=agendamento_contexto,
            )

        # O motor determinístico pode inferir a intenção durante a geração
        # da resposta, após o lead já ter sido gravado. Regravamos para que
        # essa alteração não se perca entre reruns da interface.
        self._atualizar_status(lead)
        temperatura_mudou = self._atualizar_score(lead, lead_id, conversation_id)
        self._resumir_se_necessario(
            lead,
            lead_id,
            conversation_id,
            temperatura_mudou=temperatura_mudou,
            agendamento=agendamento,
        )
        self._leads.atualizar(lead)

        # [5] Persistir a saída
        self._conversas.adicionar_mensagem(
            Message(
                conversation_id=conversation_id,
                role=MessageRole.AGENT,
                content=resposta.texto,
                modelo_usado=resposta.modelo,
                latencia_ms=resposta.latencia_ms,
            )
        )
        self._conversas.registrar_evento(
            EventType.MENSAGEM_ENVIADA,
            lead_id=lead_id,
            conversation_id=conversation_id,
            origem=resposta.origem,
            latencia_ms=resposta.latencia_ms,
        )

        if resposta.houve_degradacao:
            self._conversas.registrar_evento(
                EventType.ERRO_LLM,
                lead_id=lead_id,
                conversation_id=conversation_id,
                detalhe="degradação para o motor determinístico",
            )

        return ResultadoTurno(
            resposta=resposta.texto,
            lead=lead,
            conversation_id=conversation_id,
            origem_resposta=resposta.origem,
            slots_atualizados=qualificacao.slots_atualizados,
            intent_identificada=qualificacao.intent_identificada,
            intencao_confirmada=precisa_confirmar,
            divergencias=qualificacao.divergencias,
            recomendacao=recomendacao,
            agendamento=agendamento,
            latencia_total_ms=qualificacao.latencia_ms + resposta.latencia_ms,
            usou_llm=resposta.usou_llm,
            houve_degradacao=resposta.houve_degradacao,
        )

    # --------------------------------------------------------
    # Confirmação de intenção ambígua
    # --------------------------------------------------------

    @staticmethod
    def _deve_confirmar_intencao(
        intent_antes: Intent,
        intent_depois: Intent,
        texto: str,
        qualificacao: ResultadoQualificacao,
    ) -> bool:
        """Decide se a intenção inferida merece confirmação do lead.

        Confirmamos quando a intenção acabou de ser definida, veio do
        modelo (não dos padrões) e o texto do lead não contém nenhum
        termo explícito de compra, aluguel ou investimento — indicando
        que a inferência partiu de contexto, não de declaração.

        O custo de confirmar é uma pergunta a mais; o custo de errar é
        conduzir toda a conversa pelo roteiro equivocado.
        """
        acabou_de_definir = (
            intent_antes == Intent.INDEFINIDA
            and intent_depois != Intent.INDEFINIDA
        )
        if not acabou_de_definir:
            return False

        if not qualificacao.usou_llm:
            return False

        return not _TERMOS_EXPLICITOS.search(texto)

    def _responder_confirmando_intencao(self, lead: Lead) -> RespostaAgente:
        """Monta a pergunta de confirmação, reconhecendo o que foi dito.

        A intenção inferida é preservada no lead — se o lead confirmar,
        nada muda; se corrigir, o próximo turno sobrescreve.
        """
        reconhecimento = f"Entendi, {lead.nome}." if lead.nome else "Entendi."
        return RespostaAgente(
            texto=f"{reconhecimento} {_CONFIRMACAO_INTENCAO}",
            origem="deterministico",
        )


    # --------------------------------------------------------
    # Recomendação de imóveis
    # --------------------------------------------------------

    def _recomendar_se_possivel(
        self, lead: Lead, lead_id: int, conversation_id: int
    ) -> ResultadoRecomendacao | None:
        """Consulta a base de imóveis quando o lead forneceu critérios.

        Retorna None quando ainda não há informação suficiente — nesse
        caso, nenhum imóvel é injetado no prompt, e o agente segue
        conduzindo a qualificação.

        A recomendação é recalculada a cada turno em vez de armazenada:
        os critérios do lead evoluem durante a conversa, e resultados
        desatualizados seriam piores que nenhum.
        """
        pode, _ = self._ranker.pode_recomendar(lead)
        if not pode:
            return None

        resultado = self._ranker.recomendar(lead)
        if not resultado.tem_resultados:
            return None

        self._conversas.registrar_evento(
            EventType.IMOVEIS_RECOMENDADOS,
            lead_id=lead_id,
            conversation_id=conversation_id,
            quantidade=len(resultado.recomendacoes),
            codigos=[r.imovel.codigo for r in resultado.recomendacoes],
            filtros_relaxados=resultado.criterios_usados.get(
                "filtros_relaxados", False
            ),
        )

        return resultado

    # --------------------------------------------------------
    # Agendamento
    # --------------------------------------------------------

    def _agendar_se_possivel(
        self, lead: Lead, lead_id: int, conversation_id: int, texto: str
    ) -> ResultadoAgendamento:
        """Tenta formalizar um compromisso a partir da disponibilidade do lead.

        Só tenta depois que a intenção está definida: nenhum roteiro
        pergunta sobre disponibilidade antes disso, e confirmar um
        horário sem saber se é para compra, aluguel ou investimento
        seria prematuro. Disponibilidade eventualmente capturada antes
        disso não se perde — o QualificationAgent já a persistiu em
        disponibilidade_reuniao, e este método volta a considerá-la assim
        que a intenção for definida em um turno seguinte.

        Quando um agendamento é criado, marca lead.status como AGENDADO
        diretamente em memória — não precisa persistir aqui: o turno já
        chama self._leads.atualizar(lead) mais adiante, depois da geração
        da resposta, e a guarda em _atualizar_status() impede que esse
        status seja sobrescrito na mesma passagem.
        """
        if lead.intent == Intent.INDEFINIDA:
            return ResultadoAgendamento()

        resultado = self._agendamento.agendar_se_possivel(lead, texto_turno=texto)

        if resultado.houve_agendamento:
            lead.status = LeadStatus.AGENDADO

        for tipo, detalhes in self._agendamento.eventos_do_resultado(resultado):
            self._conversas.registrar_evento(
                tipo,
                lead_id=lead_id,
                conversation_id=conversation_id,
                **detalhes,
            )

        return resultado

    # --------------------------------------------------------
    # Estado do lead
    # --------------------------------------------------------

    @staticmethod
    def _atualizar_status(lead: Lead) -> None:
        """Avança o status conforme a qualificação progride.

        A transição é derivada da completude, e não decidida pelo modelo:
        é regra de negócio determinística e auditável.
        """
        if lead.status in (LeadStatus.AGENDADO, LeadStatus.ENCAMINHADO):
            return

        completude = lead.completude()
        # Um lead sem intenção definida não está qualificado, ainda que
        # todos os demais campos estejam preenchidos: sem saber se quer
        # comprar, alugar ou investir, o corretor não sabe como abordá-lo.
        if completude >= 1.0 and lead.intent != Intent.INDEFINIDA:
            lead.status = LeadStatus.QUALIFICADO
        elif completude > 0 or lead.intent != Intent.INDEFINIDA:
            lead.status = LeadStatus.EM_QUALIFICACAO

    def _registrar_eventos_qualificacao(
        self,
        qualificacao: ResultadoQualificacao,
        lead_id: int,
        conversation_id: int,
    ) -> None:
        """Grava os eventos derivados da qualificação."""
        for tipo, detalhes in self._qualificacao.eventos_do_resultado(
            qualificacao, lead_id
        ):
            self._conversas.registrar_evento(
                tipo,
                lead_id=lead_id,
                conversation_id=conversation_id,
                **detalhes,
            )

        for divergencia in qualificacao.divergencias:
            logger.info("Divergência de extração: %s", divergencia)


    def _atualizar_score(
        self, lead: Lead, lead_id: int, conversation_id: int
    ) -> bool:
        """Recalcula score e temperatura do lead ao final do turno.

        Função de custo desprezível (sem chamada a LLM); roda a cada
        turno para que o score exibido nunca esteja desatualizado.
        O evento LEAD_CLASSIFICADO só é registrado quando a temperatura
        muda, para não poluir a trilha de observabilidade com eventos
        redundantes em turnos onde a classificação permanece igual.

        Devolve True quando a temperatura mudou neste turno — usado por
        _resumir_se_necessario() para decidir se um resumo é devido.
        """
        contexto = construir_contexto(
            lead,
            conversation_id,
            imoveis=self._imoveis,
            conversas=self._conversas,
        )
        temperatura_anterior = lead.temperature
        resultado = calcular_score(lead, contexto)
        lead.score = resultado.score
        lead.temperature = resultado.temperature

        mudou = resultado.temperature != temperatura_anterior
        if mudou:
            self._conversas.registrar_evento(
                EventType.LEAD_CLASSIFICADO,
                lead_id=lead_id,
                conversation_id=conversation_id,
                score=resultado.score,
                temperatura=resultado.temperature,
                temperatura_anterior=temperatura_anterior,
                detalhamento=resultado.detalhamento,
            )

        return mudou

    # --------------------------------------------------------
    # Resumo para o corretor
    # --------------------------------------------------------

    def _resumir_se_necessario(
        self,
        lead: Lead,
        lead_id: int,
        conversation_id: int,
        *,
        temperatura_mudou: bool,
        agendamento: ResultadoAgendamento,
    ) -> ResumoGerado | None:
        """Gera um resumo para o corretor quando algo relevante mudou.

        Gatilhos (decisão já validada antes da implementação): o lead
        acabou de ficar quente, ou um agendamento acabou de ser criado
        neste turno. Fora esses dois casos, gerar um resumo a cada turno
        seria custo sem benefício — o corretor não precisa de um resumo
        novo a cada mensagem trocada.
        """
        ficou_quente = temperatura_mudou and lead.temperature == LeadTemperature.QUENTE
        agendamento_confirmado = agendamento.houve_agendamento

        if not (ficou_quente or agendamento_confirmado):
            return None

        resumo = self._resumo.gerar(lead)

        for tipo, detalhes in self._resumo.eventos_do_resultado(resumo):
            self._conversas.registrar_evento(
                tipo,
                lead_id=lead_id,
                conversation_id=conversation_id,
                **detalhes,
            )

        return resumo

    # --------------------------------------------------------
    # Encerramento
    # --------------------------------------------------------

    def encerrar_conversa(
        self, conversation_id: int, *, escalar: bool = False
    ) -> None:
        """Encerra a sessão, opcionalmente escalando para atendimento humano."""
        status = (
            ConversationStatus.ESCALADA if escalar else ConversationStatus.ENCERRADA
        )
        self._conversas.atualizar_status_conversa(conversation_id, status)

    def marcar_aguardando_lead(self, conversation_id: int) -> None:
        """Sinaliza que a conversa aguarda retorno do lead.

        Estado intermediário que viabiliza o follow-up: a conversa não
        é encerrada, e o histórico permanece disponível para retomada.
        """
        self._conversas.atualizar_status_conversa(
            conversation_id, ConversationStatus.AGUARDANDO_LEAD
        )

    # --------------------------------------------------------
    # Follow-up
    # --------------------------------------------------------

    def executar_verificacao_followup(
        self, *, horas: float = 24
    ) -> list[ResultadoFollowup]:
        """Verifica leads inativos e decide reengajar ou escalar cada um.

        Sem gatilho automático dentro de processar_mensagem — ao
        contrário do agendamento e do resumo, follow-up não é reação a
        uma mensagem do lead, é o oposto: só faz sentido quando não há
        mensagem nenhuma. Ainda não há interface para disparar isso; o
        método fica pronto (mesma decisão já tomada com o agendamento
        antes de existir tela para ele), a ser chamado pela Etapa 7.

        Quando um lead é escalado, também gera o resumo do corretor —
        é exatamente o terceiro gatilho já definido para o Summarizer.
        """
        resultados = self._followup.processar_inativos(horas=horas)

        for resultado in resultados:
            for tipo, detalhes in self._followup.eventos_do_resultado(resultado):
                self._conversas.registrar_evento(
                    tipo,
                    lead_id=resultado.lead_id,
                    **detalhes,
                )

            if resultado.houve_escalada:
                self._resumir_lead_escalado(resultado.lead_id)

        return resultados

    def _resumir_lead_escalado(self, lead_id: int) -> None:
        """Gera e persiste o resumo de um lead recém-escalado.

        Diferente de _resumir_se_necessario() (chamado dentro de um
        turno, onde a persistência do lead já acontece logo em seguida
        no fluxo normal), aqui não há mais nenhum ponto adiante que vá
        persistir o lead — este método precisa fazer isso explicitamente.
        """
        lead = self._leads.buscar_por_id(lead_id)
        if lead is None:
            return

        resumo = self._resumo.gerar(lead)
        self._leads.atualizar(lead)

        for tipo, detalhes in self._resumo.eventos_do_resultado(resumo):
            self._conversas.registrar_evento(tipo, lead_id=lead_id, **detalhes)

    # --------------------------------------------------------
    # Consultas para a interface
    # --------------------------------------------------------

    def historico_da_conversa(self, conversation_id: int) -> list[Message]:
        return self._conversas.listar_mensagens(conversation_id)

    def diagnostico(self) -> dict:
        """Estado operacional do sistema, exibido no painel."""
        return {
            **self._cliente._settings.resumo_publico(),
            "uso_llm": self._cliente.stats.resumo(),
        }