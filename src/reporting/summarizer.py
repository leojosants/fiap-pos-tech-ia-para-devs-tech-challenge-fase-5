"""Gerador de resumo do lead para o corretor.

Usa o LLM (model_smart, via GroqClient.resumir()) para transformar os
dados estruturados do lead em um resumo em prosa. Quando o LLM não está
disponível (modo demonstrativo) ou a chamada falha, degrada para um
resumo determinístico por template — mesma estratégia de degradação já
usada no ConversationAgent: uma resposta sempre é produzida, e quem
chama sabe por qual caminho ela veio.

O resumo determinístico não tenta imitar prosa gerada por IA: lista os
mesmos dados estruturados que seriam enviados ao modelo. É menos natural
que um resumo em prosa, mas é honesto — não finge uma capacidade que não
está em uso no momento.
"""

import logging
from dataclasses import dataclass

from src.core.enums import AppointmentType, EventType
from src.core.models import Lead
from src.llm.groq_client import GroqClient
from src.llm.prompts import PROMPT_RESUMO_CORRETOR, montar_conteudo_resumo
from src.persistence.appointment_repository import AppointmentRepository

logger = logging.getLogger(__name__)

# Duplicado deliberadamente do dicionário equivalente em
# scheduling_agent.py: lá é privado (uso interno da interpretação de
# texto), e importar um símbolo privado de outro módulo criaria um
# acoplamento maior do que vale a pena para três entradas de texto.
_TIPOS_LEGIVEIS = {
    AppointmentType.VISITA_IMOVEL: "visita ao imóvel",
    AppointmentType.REUNIAO_ONLINE: "reunião online",
    AppointmentType.REUNIAO_PRESENCIAL: "reunião presencial",
}


@dataclass
class ResumoGerado:
    """Resumo produzido para o corretor, com metadados de rastreabilidade."""

    texto: str
    origem: str  # "llm" | "deterministico" | "fallback"
    modelo: str = ""
    latencia_ms: int = 0
    tokens: int = 0

    @property
    def usou_llm(self) -> bool:
        return self.origem == "llm"

    @property
    def houve_degradacao(self) -> bool:
        """Indica que o LLM estava previsto mas falhou."""
        return self.origem == "fallback"


class Summarizer:
    """Produz o resumo do lead para o corretor."""

    def __init__(
        self,
        cliente: GroqClient | None = None,
        agendamentos: AppointmentRepository | None = None,
    ) -> None:
        self._cliente = cliente or GroqClient()
        self._agendamentos = agendamentos or AppointmentRepository()

    # --------------------------------------------------------
    # Interface pública
    # --------------------------------------------------------

    def gerar(self, lead: Lead) -> ResumoGerado:
        """Gera o resumo do lead e grava em lead.resumo_corretor.

        Efeito colateral deliberado: muta o lead recebido, no mesmo
        padrão do QualificationAgent.qualificar(). A persistência em si
        continua sendo responsabilidade exclusiva de quem orquestra o
        turno, via LeadRepository.atualizar() — este método não toca
        em banco além da consulta ao agendamento ativo.
        """
        agendamento_texto = self._texto_agendamento(lead)

        if self._cliente.disponivel:
            resumo = self._gerar_com_llm(lead, agendamento_texto)
            if resumo is not None:
                lead.resumo_corretor = resumo.texto
                return resumo

            logger.warning(
                "Falha na geração do resumo via LLM; recorrendo ao template."
            )
            resumo = self._gerar_deterministico(
                lead, agendamento_texto, origem="fallback"
            )
        else:
            resumo = self._gerar_deterministico(
                lead, agendamento_texto, origem="deterministico"
            )

        lead.resumo_corretor = resumo.texto
        return resumo

    # --------------------------------------------------------
    # Agendamento ativo — contexto adicional para o resumo
    # --------------------------------------------------------

    def _texto_agendamento(self, lead: Lead) -> str:
        """Descreve o compromisso ativo do lead, se houver.

        O corretor precisa saber se já existe uma reunião marcada antes
        de ligar — omitir essa informação do resumo seria um contexto
        perdido, não uma simplificação inofensiva.
        """
        if lead.id is None:
            return ""

        appointment = self._agendamentos.proximo_agendamento_do_lead(lead.id)
        if appointment is None:
            return ""

        tipo_legivel = _TIPOS_LEGIVEIS.get(appointment.tipo, str(appointment.tipo))
        return (
            f"Compromisso agendado: "
            f"{appointment.data_hora.strftime('%d/%m às %Hh%M')} "
            f"({tipo_legivel})."
        )

    # --------------------------------------------------------
    # Modos de geração
    # --------------------------------------------------------

    def _gerar_com_llm(
        self, lead: Lead, agendamento_texto: str
    ) -> ResumoGerado | None:
        """Gera o resumo pelo modelo. Devolve None se a chamada falhar."""
        conteudo = montar_conteudo_resumo(lead, agendamento_texto)
        resposta = self._cliente.resumir(PROMPT_RESUMO_CORRETOR, conteudo)

        if not resposta.sucesso or not resposta.conteudo.strip():
            return None

        return ResumoGerado(
            texto=resposta.conteudo.strip(),
            origem="llm",
            modelo=resposta.modelo,
            latencia_ms=resposta.latencia_ms,
            tokens=resposta.total_tokens,
        )

    @staticmethod
    def _gerar_deterministico(
        lead: Lead, agendamento_texto: str, *, origem: str
    ) -> ResumoGerado:
        """Resumo por template — reaproveita montar_conteudo_resumo(),
        que já produz uma listagem estruturada adequada para leitura
        direta, sem depender do modelo para organizar o texto.
        """
        cabecalho = "Resumo do lead"
        if lead.nome:
            cabecalho += f" — {lead.nome}"

        texto = f"{cabecalho}\n\n{montar_conteudo_resumo(lead, agendamento_texto)}"
        return ResumoGerado(texto=texto, origem=origem)

    # --------------------------------------------------------
    # Eventos — mesmo contrato dos demais agentes
    # --------------------------------------------------------

    @staticmethod
    def eventos_do_resultado(resumo: ResumoGerado) -> list[tuple[EventType, dict]]:
        """Traduz o resultado em eventos para o log de observabilidade.

        Diferente dos outros agentes, sempre há algo a registrar: gerar
        um resumo é, por definição, uma ação que aconteceu neste turno.
        """
        return [(
            EventType.RESUMO_GERADO,
            {"origem": resumo.origem, "usou_llm": resumo.usou_llm},
        )]