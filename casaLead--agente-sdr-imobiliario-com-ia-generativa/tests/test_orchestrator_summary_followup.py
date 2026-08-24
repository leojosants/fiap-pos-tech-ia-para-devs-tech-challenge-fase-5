"""Testes do orchestrator — integração final da Etapa 6 (resumo e
follow-up).

Mesma técnica de test_orchestrator_scheduling.py: instância mínima via
__new__, evitando depender de GroqClient real, PropertyRanker ou o
módulo de scoring completo — aqui só _resumo, _followup, _leads e
_conversas são necessários.
"""

from datetime import datetime, timedelta

import pytest

from src.agents.orchestrator import Orchestrator
from src.agents.scheduling_agent import ResultadoAgendamento
from src.core.enums import EventType, Intent, LeadTemperature
from src.core.models import Appointment, Conversation, Lead
from src.core.enums import AppointmentStatus, AppointmentType
from src.followup.followup_manager import FollowupManager
from src.llm.groq_client import LLMResponse
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema, get_connection
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository
from src.reporting.summarizer import Summarizer


class _ClienteFalso:
    """GroqClient falso — controla disponibilidade e resposta do resumir()."""

    def __init__(self, *, disponivel: bool = False):
        self.disponivel = disponivel
        self.chamadas = 0

    def resumir(self, prompt_sistema: str, conteudo: str) -> LLMResponse:
        self.chamadas += 1
        return LLMResponse(conteudo="Resumo gerado por LLM falso.", sucesso=True)


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def conversas_repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


@pytest.fixture
def appointment_repo(db_path) -> AppointmentRepository:
    return AppointmentRepository(db_path)


@pytest.fixture
def followup_repo(db_path) -> FollowupRepository:
    return FollowupRepository(db_path)


@pytest.fixture
def orchestrator_minimo(db_path, appointment_repo, followup_repo, conversas_repo, lead_repo):
    """Instância mínima — só com o necessário para os métodos testados."""
    cliente = _ClienteFalso(disponivel=False)  # modo demo: sem custo de API
    orch = Orchestrator.__new__(Orchestrator)
    orch._leads = lead_repo
    orch._conversas = conversas_repo
    orch._resumo = Summarizer(cliente, appointment_repo)
    orch._followup = FollowupManager(followup_repo, conversas_repo, lead_repo)
    return orch


def _lead_com_conversa(lead_repo, conversas_repo, **kwargs) -> tuple[Lead, int]:
    lead = lead_repo.criar(Lead(nome="Ana", **kwargs))
    conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
    return lead, conversa.id


# ============================================================
# _resumir_se_necessario
# ============================================================

class TestResumirSeNecessario:

    def test_lead_fica_quente_gera_resumo(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
            temperature=LeadTemperature.QUENTE,
        )

        resumo = orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=True,
            agendamento=ResultadoAgendamento(),
        )

        assert resumo is not None
        assert lead.resumo_corretor == resumo.texto

    def test_lead_fica_morno_nao_gera_resumo(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
            temperature=LeadTemperature.MORNO,
        )

        resumo = orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=True,
            agendamento=ResultadoAgendamento(),
        )

        assert resumo is None
        assert lead.resumo_corretor == ""

    def test_ja_estava_quente_sem_mudanca_nao_regenera(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        """Evita custo redundante: já era quente, continuou quente —
        não é um evento novo, não justifica outro resumo."""
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
            temperature=LeadTemperature.QUENTE,
        )

        resumo = orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=False,
            agendamento=ResultadoAgendamento(),
        )

        assert resumo is None

    def test_agendamento_confirmado_gera_resumo_mesmo_lead_frio(
        self, orchestrator_minimo, lead_repo, conversas_repo, appointment_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
            temperature=LeadTemperature.FRIO,
        )
        ap = Appointment(
            lead_id=lead.id, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=datetime.now() + timedelta(days=1),
        )
        resultado_agendamento = ResultadoAgendamento(appointment=ap, ja_existia=False)

        resumo = orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=False,
            agendamento=resultado_agendamento,
        )

        assert resumo is not None

    def test_agendamento_pre_existente_nao_dispara_resumo(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        """ja_existia=True significa que nada mudou neste turno."""
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
        )
        ap = Appointment(
            lead_id=lead.id, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=datetime.now() + timedelta(days=1),
        )
        resultado_agendamento = ResultadoAgendamento(appointment=ap, ja_existia=True)

        resumo = orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=False,
            agendamento=resultado_agendamento,
        )

        assert resumo is None

    def test_resumo_gerado_registra_evento(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA,
            temperature=LeadTemperature.QUENTE,
        )

        orchestrator_minimo._resumir_se_necessario(
            lead, lead.id, conversa_id,
            temperatura_mudou=True,
            agendamento=ResultadoAgendamento(),
        )

        eventos = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.RESUMO_GERADO
        )
        assert len(eventos) == 1


# ============================================================
# executar_verificacao_followup
# ============================================================

class TestExecutarVerificacaoFollowup:

    def _backdatar_lead(self, db_path, lead_id: int, horas: int = 48) -> None:
        antigo = (datetime.now() - timedelta(hours=horas)).isoformat()
        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE leads SET updated_at = ? WHERE id = ?", (antigo, lead_id)
            )

    def test_lead_inativo_recebe_primeiro_followup(
        self, orchestrator_minimo, lead_repo, conversas_repo, db_path
    ):
        lead, _ = _lead_com_conversa(lead_repo, conversas_repo)
        self._backdatar_lead(db_path, lead.id)

        resultados = orchestrator_minimo.executar_verificacao_followup(horas=24)

        assert len(resultados) == 1
        assert resultados[0].houve_envio

    def test_envio_registra_evento_followup_enviado(
        self, orchestrator_minimo, lead_repo, conversas_repo, db_path
    ):
        lead, _ = _lead_com_conversa(lead_repo, conversas_repo)
        self._backdatar_lead(db_path, lead.id)

        orchestrator_minimo.executar_verificacao_followup(horas=24)

        eventos = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.FOLLOWUP_ENVIADO
        )
        assert len(eventos) == 1

    def test_escalada_apos_max_tentativas_gera_resumo(
        self, orchestrator_minimo, lead_repo, conversas_repo, db_path
    ):
        lead, _ = _lead_com_conversa(lead_repo, conversas_repo, intent=Intent.COMPRA)
        self._backdatar_lead(db_path, lead.id)

        orchestrator_minimo.executar_verificacao_followup(horas=24)  # tentativa 1
        orchestrator_minimo.executar_verificacao_followup(horas=24)  # tentativa 2
        resultados = orchestrator_minimo.executar_verificacao_followup(horas=24)  # escala

        assert resultados[0].houve_escalada

        eventos_escalada = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.LEAD_ESCALADO
        )
        assert len(eventos_escalada) == 1

        eventos_resumo = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.RESUMO_GERADO
        )
        assert len(eventos_resumo) == 1

    def test_resumo_do_lead_escalado_e_persistido(
        self, orchestrator_minimo, lead_repo, conversas_repo, db_path
    ):
        lead, _ = _lead_com_conversa(lead_repo, conversas_repo, intent=Intent.COMPRA)
        self._backdatar_lead(db_path, lead.id)

        orchestrator_minimo.executar_verificacao_followup(horas=24)
        orchestrator_minimo.executar_verificacao_followup(horas=24)
        orchestrator_minimo.executar_verificacao_followup(horas=24)

        atualizado = lead_repo.buscar_por_id(lead.id)
        assert atualizado.resumo_corretor != ""

    def test_lead_recente_nao_gera_nenhum_resultado(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        _lead_com_conversa(lead_repo, conversas_repo)
        resultados = orchestrator_minimo.executar_verificacao_followup(horas=24)
        assert resultados == []