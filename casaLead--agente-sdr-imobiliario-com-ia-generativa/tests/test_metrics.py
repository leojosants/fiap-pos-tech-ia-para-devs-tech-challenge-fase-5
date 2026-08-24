"""Testes de src/observability/metrics.py (Etapa 7).

Banco SQLite temporário via tmp_path, isolado do banco de
desenvolvimento — mesmo padrão de tests/test_scoring_builder.py.
"""

from pathlib import Path

import pytest

from src.core.enums import Intent, LeadStatus, LeadTemperature, Zone
from src.core.models import Lead
from src.llm.groq_client import GroqClient
from src.observability import metrics
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import bootstrap
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    caminho = tmp_path / "teste_metrics.db"
    bootstrap(caminho)
    return caminho


# ============================================================
# leads_com_interacao
# ============================================================

def test_leads_com_interacao_exclui_lead_totalmente_vazio():
    vazio = Lead()
    com_intencao = Lead(intent=Intent.COMPRA)
    com_slot = Lead(zona_interesse=Zone.SUL)

    resultado = metrics.leads_com_interacao([vazio, com_intencao, com_slot])

    assert vazio not in resultado
    assert com_intencao in resultado
    assert com_slot in resultado


def test_leads_com_interacao_lista_vazia_devolve_vazia():
    assert metrics.leads_com_interacao([]) == []


# ============================================================
# funil_de_leads
# ============================================================

def test_funil_de_leads_oculta_leads_vazios_por_padrao(db_path):
    leads_repo = LeadRepository(db_path)
    leads_repo.criar(Lead())  # vazio — criado só ao abrir a conversa
    leads_repo.criar(Lead(intent=Intent.COMPRA, status=LeadStatus.EM_QUALIFICACAO))

    resultado = metrics.funil_de_leads(leads_repo)

    assert resultado["total_bruto"] == 2
    assert resultado["total"] == 1
    assert resultado["leads_vazios_ocultos"] == 1
    assert resultado["por_intencao"] == {str(Intent.COMPRA): 1}


def test_funil_de_leads_inclui_vazios_quando_solicitado(db_path):
    leads_repo = LeadRepository(db_path)
    leads_repo.criar(Lead())
    leads_repo.criar(Lead(intent=Intent.ALUGUEL))

    resultado = metrics.funil_de_leads(leads_repo, apenas_com_interacao=False)

    assert resultado["total"] == 2
    assert resultado["leads_vazios_ocultos"] == 0


def test_funil_de_leads_agrega_por_status_temperatura_e_score(db_path):
    leads_repo = LeadRepository(db_path)
    leads_repo.criar(
        Lead(
            intent=Intent.COMPRA,
            status=LeadStatus.QUALIFICADO,
            temperature=LeadTemperature.QUENTE,
            score=80,
        )
    )
    leads_repo.criar(
        Lead(
            intent=Intent.ALUGUEL,
            status=LeadStatus.QUALIFICADO,
            temperature=LeadTemperature.MORNO,
            score=40,
        )
    )

    resultado = metrics.funil_de_leads(leads_repo)

    assert resultado["por_status"] == {str(LeadStatus.QUALIFICADO): 2}
    assert resultado["por_temperatura"] == {
        str(LeadTemperature.QUENTE): 1,
        str(LeadTemperature.MORNO): 1,
    }
    assert resultado["score_medio"] == 60.0


def test_funil_de_leads_sem_nenhum_lead_nao_gera_divisao_por_zero(db_path):
    leads_repo = LeadRepository(db_path)

    resultado = metrics.funil_de_leads(leads_repo)

    assert resultado["total"] == 0
    assert resultado["score_medio"] == 0.0


# ============================================================
# coletar — painel completo
# ============================================================

def test_coletar_reune_todas_as_fontes(db_path):
    leads_repo = LeadRepository(db_path)
    conversas_repo = ConversationRepository(db_path)
    agendamentos_repo = AppointmentRepository(db_path)
    followups_repo = FollowupRepository(db_path)
    cliente = GroqClient()

    leads_repo.criar(Lead(intent=Intent.INVESTIMENTO))

    resultado = metrics.coletar(
        leads_repo=leads_repo,
        conversas_repo=conversas_repo,
        agendamentos_repo=agendamentos_repo,
        followups_repo=followups_repo,
        cliente=cliente,
    )

    assert set(resultado.keys()) == {
        "funil",
        "eventos",
        "agendamentos",
        "followups",
        "uso_llm",
    }
    assert resultado["funil"]["total"] == 1
    assert resultado["agendamentos"] == {"total": 0, "por_status": {}}
    assert resultado["followups"] == {"total": 0, "por_status": {}}
    assert resultado["uso_llm"]["chamadas"] == 0