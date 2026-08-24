"""Gerenciador de follow-up (cenário 3.3 do enunciado).

Identifica leads que iniciaram conversa e pararam de responder, decide
entre reengajar ou escalar para atendimento humano, e registra cada
tentativa.

A mensagem de reengajamento é determinística (template, sem chamada a
LLM): é uma mensagem proativa de background, não uma resposta a um
turno de conversa — gastar uma chamada de API para isso (e precisar de
fallback para o modo demo) seria desproporcional. Mesmo princípio já
aplicado em outras partes do sistema: o que pode ser determinístico não
vai ao modelo de linguagem.
"""

from dataclasses import dataclass

from src.core.enums import (
    ConversationStatus,
    EventType,
    FollowupStatus,
    Intent,
    InvestmentGoal,
    Zone,
)
from src.core.models import Followup, Lead
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository

# Após esta quantidade de tentativas sem resposta, o lead é escalado
# para atendimento humano em vez de receber uma nova tentativa.
MAX_TENTATIVAS = 2

# ============================================================
# Mensagens — templates determinísticos por número de tentativa
# ============================================================

_TEMPLATE_TENTATIVA_1 = (
    "Oi{saudacao_nome}! Vi que nossa conversa parou{detalhe_contexto} — "
    "ainda faz sentido continuarmos? Sem pressa, é só responder quando "
    "puder."
)

_TEMPLATE_TENTATIVA_2 = (
    "Oi{saudacao_nome}, passando de novo por aqui{detalhe_contexto}. Se "
    "ainda fizer sentido pra você, é só responder — e se não for mais o "
    "momento, sem problema nenhum."
)

_TEMPLATES = {1: _TEMPLATE_TENTATIVA_1, 2: _TEMPLATE_TENTATIVA_2}

_ZONAS_LEGIVEIS = {
    Zone.SUL: "zona sul",
    Zone.OESTE: "zona oeste",
    Zone.CENTRO: "região central",
    Zone.NORTE: "zona norte",
}

_OBJETIVOS_LEGIVEIS = {
    InvestmentGoal.RENDA: "renda mensal",
    InvestmentGoal.VALORIZACAO: "valorização do patrimônio",
    InvestmentGoal.DIVERSIFICACAO: "diversificação de investimentos",
}


def _detalhe_contexto(lead: Lead) -> str:
    """Um detalhe concreto já conhecido do lead, para a mensagem soar
    específica em vez de genérica. Vazio quando nada relevante foi
    capturado ainda — a mensagem cai para a forma neutra do template.
    """
    if lead.intent == Intent.INVESTIMENTO:
        rotulo = _OBJETIVOS_LEGIVEIS.get(lead.objetivo_investimento)
        if rotulo:
            return f" sobre o investimento em {rotulo}"
        return ""

    if lead.zona_interesse is not None:
        rotulo = _ZONAS_LEGIVEIS.get(lead.zona_interesse, str(lead.zona_interesse))
        return f" sobre o imóvel na {rotulo}"

    return ""


def _montar_mensagem(lead: Lead, tentativa: int) -> str:
    """Monta a mensagem de reengajamento para a tentativa informada.

    Função pura — não acessa banco nem relógio, testável isoladamente.
    Tentativas além das mapeadas reaproveitam o template da última
    (mais direto), em vez de falhar.
    """
    template = _TEMPLATES.get(tentativa, _TEMPLATE_TENTATIVA_2)
    saudacao_nome = f", {lead.nome}" if lead.nome else ""
    detalhe_contexto = _detalhe_contexto(lead)
    return template.format(
        saudacao_nome=saudacao_nome, detalhe_contexto=detalhe_contexto
    )


# ============================================================
# Resultado
# ============================================================

@dataclass
class ResultadoFollowup:
    """Ação tomada para um lead inativo neste processamento."""

    lead_id: int
    acao: str = "nenhuma"  # "enviado" | "escalado" | "nenhuma"
    followup: Followup | None = None
    tentativa: int = 0

    @property
    def houve_envio(self) -> bool:
        return self.acao == "enviado"

    @property
    def houve_escalada(self) -> bool:
        return self.acao == "escalado"


# ============================================================
# Gerenciador
# ============================================================

class FollowupManager:
    """Identifica leads inativos e decide reengajar ou escalar."""

    def __init__(
        self,
        followups: FollowupRepository | None = None,
        conversas: ConversationRepository | None = None,
        leads: LeadRepository | None = None,
    ) -> None:
        self._followups = followups or FollowupRepository()
        self._conversas = conversas or ConversationRepository()
        self._leads = leads or LeadRepository()

    # --------------------------------------------------------
    # Processamento em lote
    # --------------------------------------------------------

    def processar_inativos(self, *, horas: float = 24) -> list[ResultadoFollowup]:
        """Percorre os leads inativos e decide a ação para cada um.

        Reaproveita LeadRepository.buscar_inativos(), já existente desde
        etapas anteriores — este método não reimplementa esse filtro.
        """
        inativos = self._leads.buscar_inativos(horas=horas)
        return [self.processar_lead(lead) for lead in inativos]

    # --------------------------------------------------------
    # Processamento por lead
    # --------------------------------------------------------

    def processar_lead(self, lead: Lead) -> ResultadoFollowup:
        """Decide e executa a ação de follow-up para um único lead.

        Ordem de decisão:
          1. Sem conversa ativa — nada a fazer; não há para onde
             reengajar (conversa já encerrada/escalada, ou inexistente).
          2. Nenhuma tentativa registrada ainda — cria e envia a 1ª.
          3. Última tentativa já respondida — nada a fazer; não há
             inatividade a tratar (defensivo: buscar_inativos() já
             filtraria por atividade recente nesse caso).
          4. Última tentativa no limite (MAX_TENTATIVAS) — marca como
             sem resposta e escala para atendimento humano.
          5. Caso contrário — marca a tentativa anterior como sem
             resposta e envia a próxima.
        """
        if lead.id is None:
            raise ValueError("Lead sem id não pode ser processado.")

        conversa = self._conversas.conversa_ativa_do_lead(lead.id)
        if conversa is None:
            return ResultadoFollowup(lead_id=lead.id)

        ultima = self._followups.ultima_tentativa_do_lead(lead.id)

        if ultima is None:
            return self._enviar_tentativa(lead, conversa.id, tentativa=1)

        if ultima.status == FollowupStatus.RESPONDIDO:
            return ResultadoFollowup(lead_id=lead.id)

        if ultima.tentativa >= MAX_TENTATIVAS:
            self._followups.atualizar_status(ultima.id, FollowupStatus.SEM_RESPOSTA)
            return self._escalar(lead, conversa.id)

        self._followups.atualizar_status(ultima.id, FollowupStatus.SEM_RESPOSTA)
        return self._enviar_tentativa(
            lead, conversa.id, tentativa=ultima.tentativa + 1
        )

    # --------------------------------------------------------
    # Ações
    # --------------------------------------------------------

    def _enviar_tentativa(
        self, lead: Lead, conversation_id: int, *, tentativa: int
    ) -> ResultadoFollowup:
        """Registra e envia uma nova tentativa de reengajamento."""
        mensagem = _montar_mensagem(lead, tentativa)

        followup = self._followups.criar(
            Followup(
                lead_id=lead.id,
                conversation_id=conversation_id,
                tentativa=tentativa,
                mensagem=mensagem,
            )
        )
        self._followups.marcar_enviado(followup.id)

        self._conversas.atualizar_status_conversa(
            conversation_id, ConversationStatus.AGUARDANDO_LEAD
        )

        return ResultadoFollowup(
            lead_id=lead.id,
            acao="enviado",
            followup=followup,
            tentativa=tentativa,
        )

    def _escalar(self, lead: Lead, conversation_id: int) -> ResultadoFollowup:
        """Encerra a tentativa de reengajamento automático e escala.

        Equivalente ao que Orchestrator.encerrar_conversa(escalar=True)
        faz — chamado diretamente aqui, e não através do orquestrador,
        para não criar uma dependência circular (o orquestrador é quem
        vai depender deste módulo, não o contrário).
        """
        self._conversas.atualizar_status_conversa(
            conversation_id, ConversationStatus.ESCALADA
        )
        return ResultadoFollowup(lead_id=lead.id, acao="escalado")

    # --------------------------------------------------------
    # Eventos — mesmo contrato dos demais agentes
    # --------------------------------------------------------

    @staticmethod
    def eventos_do_resultado(
        resultado: ResultadoFollowup,
    ) -> list[tuple[EventType, dict]]:
        """Traduz o resultado em eventos para o log de observabilidade."""
        if resultado.houve_envio:
            return [(
                EventType.FOLLOWUP_ENVIADO,
                {
                    "followup_id": resultado.followup.id,
                    "tentativa": resultado.tentativa,
                },
            )]

        if resultado.houve_escalada:
            return [(
                EventType.LEAD_ESCALADO,
                {"motivo": "sem_resposta_apos_followups"},
            )]

        return []