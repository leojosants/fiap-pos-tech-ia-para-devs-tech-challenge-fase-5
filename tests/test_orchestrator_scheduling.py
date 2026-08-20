"""Testes do orchestrator — escopo restrito ao Passo 4 (integração do
agendamento, método _agendar_se_possivel).

Não instancia o Orchestrator via __init__ real: isso exigiria GroqClient,
PropertyRanker e o módulo de scoring, nenhum recebido nesta sessão. Em
vez disso, constrói uma instância mínima (via __new__) e define
manualmente só as duas dependências que _agendar_se_possivel de fato usa
(_agendamento e _conversas), com SQLite real por trás.

Isso significa que este arquivo valida a integração pontual do passo
[4.5], não o turno completo (processar_mensagem) — que depende de
colaboradores fora do escopo desta sessão. O fluxo de ponta a ponta
(processar_mensagem completo, com recomendação e scoring reais) deve
ser validado na interface Streamlit ou por quem tiver acesso a
ranker.py e ao módulo de scoring.
"""

from datetime import datetime

import pytest

from src.agents.orchestrator import Orchestrator
from src.agents.scheduling_agent import SchedulingAgent
from src.core.enums import (
    AppointmentStatus,
    AppointmentType,
    EventType,
    Intent,
    LeadStatus,
)
from src.core.models import Appointment, Conversation, Lead
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema
from src.persistence.lead_repository import LeadRepository

REFERENCIA = datetime(2026, 8, 19, 9, 0, 0)  # quarta-feira


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def orchestrator_minimo(db_path) -> Orchestrator:
    """Instância do Orchestrator só com o necessário para o método testado."""
    orch = Orchestrator.__new__(Orchestrator)
    orch._agendamento = SchedulingAgent(AppointmentRepository(db_path))
    orch._conversas = ConversationRepository(db_path)
    return orch


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def conversas_repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


@pytest.fixture
def appointment_repo(db_path) -> AppointmentRepository:
    return AppointmentRepository(db_path)


def _lead_com_conversa(lead_repo, conversas_repo, **kwargs) -> tuple[Lead, int]:
    lead = lead_repo.criar(Lead(nome="Ana", **kwargs))
    conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
    return lead, conversa.id


class TestGuardaDeIntencaoIndefinida:

    def test_intencao_indefinida_nao_tenta_agendar(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.INDEFINIDA,
            disponibilidade_reuniao="sexta de manhã",
        )

        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "sexta de manhã"
        )

        assert resultado.appointment is None
        assert lead.status != LeadStatus.AGENDADO

    def test_disponibilidade_capturada_antes_da_intencao_nao_se_perde(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        """A informação fica represada em disponibilidade_reuniao e é
        processada assim que a intenção é definida, em outro turno."""
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.INDEFINIDA,
            disponibilidade_reuniao="sexta de manhã",
        )

        # turno 1: intenção ainda indefinida — nada acontece
        orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "sexta de manhã"
        )
        assert lead.status != LeadStatus.AGENDADO

        # turno 2: intenção agora definida — a disponibilidade já
        # persistida anteriormente é reaproveitada
        lead.intent = Intent.COMPRA
        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "pode ser assim mesmo"
        )

        assert resultado.houve_agendamento
        assert lead.status == LeadStatus.AGENDADO


class TestAgendamentoCriado:

    def test_disponibilidade_interpretavel_cria_appointment_e_atualiza_status(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.COMPRA,
            disponibilidade_reuniao="sexta de manhã",
        )

        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "sexta de manhã"
        )

        assert resultado.houve_agendamento
        assert lead.status == LeadStatus.AGENDADO

    def test_agendamento_criado_registra_evento(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.COMPRA,
            disponibilidade_reuniao="sexta de manhã",
        )

        orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "sexta de manhã"
        )

        eventos = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.AGENDAMENTO_CRIADO
        )
        assert len(eventos) == 1
        # regressão: "tipo" dentro de detalhes colidia com o parâmetro
        # posicional "tipo" de registrar_evento (EventType) — ver
        # scheduling_agent.eventos_do_resultado, chave tipo_compromisso
        assert "appointment_id" in eventos[0].detalhes
        assert "tipo_compromisso" in eventos[0].detalhes

    def test_texto_turno_cria_appointment_quando_disponibilidade_e_vaga(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        """Cobre o fallback do scheduling_agent: disponibilidade_reuniao
        já congelada vaga, mas a mensagem atual é interpretável."""
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.COMPRA,
            disponibilidade_reuniao="qualquer hora tá bom",
        )

        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "terça de manhã então"
        )

        assert resultado.houve_agendamento


class TestSugestoesNaoAlteramStatus:

    def test_disponibilidade_vaga_gera_sugestoes_sem_agendar(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.COMPRA,
            disponibilidade_reuniao="qualquer hora tá bom",
        )

        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "tanto faz"
        )

        assert resultado.appointment is None
        assert len(resultado.sugestoes) > 0
        assert lead.status != LeadStatus.AGENDADO

    def test_sugestoes_nao_registram_evento(
        self, orchestrator_minimo, lead_repo, conversas_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo,
            conversas_repo,
            intent=Intent.COMPRA,
            disponibilidade_reuniao="qualquer hora tá bom",
        )

        orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "tanto faz"
        )

        eventos = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.AGENDAMENTO_CRIADO
        )
        assert eventos == []


class TestAgendamentoJaExistente:

    def test_nao_duplica_nem_gera_novo_evento(
        self, orchestrator_minimo, lead_repo, conversas_repo, appointment_repo
    ):
        lead, conversa_id = _lead_com_conversa(
            lead_repo, conversas_repo, intent=Intent.COMPRA
        )
        appointment_repo.criar(
            Appointment(
                lead_id=lead.id,
                tipo=AppointmentType.REUNIAO_ONLINE,
                data_hora=datetime(2026, 8, 21, 15, 0),
            )
        )
        lead.status = LeadStatus.AGENDADO  # já teria sido setado quando criado

        resultado = orchestrator_minimo._agendar_se_possivel(
            lead, lead.id, conversa_id, "queria mudar para quarta"
        )

        assert resultado.ja_existia
        assert len(appointment_repo.listar_do_lead(lead.id)) == 1

        eventos = conversas_repo.listar_eventos(
            lead_id=lead.id, tipo=EventType.AGENDAMENTO_CRIADO
        )
        assert eventos == []