"""Testes das propriedades públicas de leitura do Orchestrator (Etapa 7).

Diferente de test_orchestrator_scheduling.py e
test_orchestrator_summary_followup.py, aqui o Orchestrator é
instanciado por completo via __init__ real — não há necessidade de
GroqClient, PropertyRanker ou scoring com colaboradores substituídos:
o objetivo é só validar que as propriedades devolvem os repositórios
corretos, com dados reais indo até o SQLite e voltando.

GroqClient() não faz nenhuma chamada de rede na construção (o cliente
HTTP interno começa como None, só é criado na primeira chamada) —
seguro de instanciar em teste, mesmo sem GROQ_API_KEY configurada.
"""

from pathlib import Path

import pytest

from src.agents.orchestrator import Orchestrator
from src.core.enums import Intent
from src.core.models import Lead
from src.llm.groq_client import GroqClient
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import bootstrap
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository
from src.persistence.property_repository import PropertyRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    caminho = tmp_path / "teste_orchestrator_properties.db"
    bootstrap(caminho)
    return caminho


@pytest.fixture
def orquestrador(db_path: Path) -> Orchestrator:
    return Orchestrator(db_path=db_path)


def test_leads_expoe_lead_repository_funcional(orquestrador, db_path):
    assert isinstance(orquestrador.leads, LeadRepository)

    lead = orquestrador.leads.criar(Lead(intent=Intent.COMPRA))
    encontrado = orquestrador.leads.buscar_por_id(lead.id)

    assert encontrado is not None
    assert encontrado.intent == Intent.COMPRA


def test_conversas_expoe_conversation_repository_funcional(orquestrador):
    assert isinstance(orquestrador.conversas, ConversationRepository)

    lead, conversa, _ = orquestrador.iniciar_atendimento()
    mensagens = orquestrador.conversas.listar_mensagens(conversa.id)

    assert len(mensagens) == 1  # a saudação


def test_imoveis_expoe_property_repository_com_base_carregada(orquestrador):
    assert isinstance(orquestrador.imoveis, PropertyRepository)
    assert orquestrador.imoveis.contar() > 0  # seed já carregado pelo bootstrap


def test_agendamentos_expoe_appointment_repository_funcional(orquestrador):
    assert isinstance(orquestrador.agendamentos, AppointmentRepository)
    assert orquestrador.agendamentos.estatisticas() == {"total": 0, "por_status": {}}


def test_followups_expoe_followup_repository_funcional(orquestrador):
    assert isinstance(orquestrador.followups, FollowupRepository)
    assert orquestrador.followups.estatisticas() == {"total": 0, "por_status": {}}


def test_followups_repository_e_a_mesma_instancia_usada_pelo_followup_manager(
    orquestrador,
):
    """Garante o compartilhamento descrito no __init__: a propriedade
    pública não pode devolver uma segunda instância desalinhada da que
    o FollowupManager de fato usa internamente."""
    assert orquestrador.followups is orquestrador._followup._followups


def test_cliente_expoe_groq_client(orquestrador):
    assert isinstance(orquestrador.cliente, GroqClient)


def test_propriedades_sao_somente_leitura(orquestrador):
    with pytest.raises(AttributeError):
        orquestrador.leads = LeadRepository()