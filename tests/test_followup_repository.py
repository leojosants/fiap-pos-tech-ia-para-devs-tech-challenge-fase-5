"""Testes da camada de persistência de follow-ups.

Banco isolado por teste (fixture padrão, escopo de função) — mesma
justificativa do test_appointment_repository.py: a entidade é escrita
e alterada pelos próprios testes, então compartilhar banco entre eles
tornaria a ordem de execução relevante para o resultado.
"""

from datetime import datetime

import pytest

from src.core.enums import ConversationStatus, FollowupStatus
from src.core.models import Conversation, Followup, Lead
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def repo(db_path) -> FollowupRepository:
    return FollowupRepository(db_path)


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def conversas_repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


@pytest.fixture
def lead_e_conversa(lead_repo, conversas_repo) -> tuple[int, int]:
    """IDs de um lead e de uma conversa reais, satisfazendo as FKs."""
    lead = lead_repo.criar(Lead(nome="Lead de Teste"))
    conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
    return lead.id, conversa.id


def _criar_followup(
    lead_id: int,
    conversation_id: int,
    *,
    tentativa: int = 1,
    mensagem: str = "Oi! Ainda tem interesse em conversar?",
    status: FollowupStatus = FollowupStatus.PENDENTE,
) -> Followup:
    return Followup(
        lead_id=lead_id,
        conversation_id=conversation_id,
        tentativa=tentativa,
        mensagem=mensagem,
        status=status,
    )


# ============================================================
# Escrita e leitura básica
# ============================================================

def test_criar_atribui_id(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu = repo.criar(_criar_followup(lead_id, conversa_id))
    assert fu.id is not None


def test_criar_exige_lead_existente(repo):
    fu = _criar_followup(lead_id=99999, conversation_id=99999)
    with pytest.raises(Exception):
        repo.criar(fu)


def test_buscar_por_id_existente(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    criado = repo.criar(_criar_followup(lead_id, conversa_id, tentativa=2))
    encontrado = repo.buscar_por_id(criado.id)

    assert encontrado is not None
    assert encontrado.lead_id == lead_id
    assert encontrado.conversation_id == conversa_id
    assert encontrado.tentativa == 2
    assert encontrado.status == FollowupStatus.PENDENTE
    assert encontrado.enviado_em is None


def test_buscar_por_id_inexistente_retorna_none(repo):
    assert repo.buscar_por_id(99999) is None


def test_mensagem_e_preservada_integralmente(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    texto = "Oi, Ana! Vi que paramos por aqui — ainda faz sentido continuarmos?"
    criado = repo.criar(_criar_followup(lead_id, conversa_id, mensagem=texto))
    assert repo.buscar_por_id(criado.id).mensagem == texto


# ============================================================
# marcar_enviado / atualizar_status
# ============================================================

def test_marcar_enviado_atualiza_status_e_carimbo(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu = repo.criar(_criar_followup(lead_id, conversa_id))

    antes = datetime.now()
    repo.marcar_enviado(fu.id)
    depois = datetime.now()

    atualizado = repo.buscar_por_id(fu.id)
    assert atualizado.status == FollowupStatus.ENVIADO
    assert atualizado.enviado_em is not None
    assert antes <= atualizado.enviado_em <= depois


def test_atualizar_status_para_respondido_nao_apaga_enviado_em(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu = repo.criar(_criar_followup(lead_id, conversa_id))
    repo.marcar_enviado(fu.id)
    carimbo_original = repo.buscar_por_id(fu.id).enviado_em

    repo.atualizar_status(fu.id, FollowupStatus.RESPONDIDO)

    atualizado = repo.buscar_por_id(fu.id)
    assert atualizado.status == FollowupStatus.RESPONDIDO
    assert atualizado.enviado_em == carimbo_original


def test_atualizar_status_para_sem_resposta_nao_apaga_enviado_em(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu = repo.criar(_criar_followup(lead_id, conversa_id))
    repo.marcar_enviado(fu.id)
    carimbo_original = repo.buscar_por_id(fu.id).enviado_em

    repo.atualizar_status(fu.id, FollowupStatus.SEM_RESPOSTA)

    atualizado = repo.buscar_por_id(fu.id)
    assert atualizado.status == FollowupStatus.SEM_RESPOSTA
    assert atualizado.enviado_em == carimbo_original


def test_followup_nunca_enviado_mantem_enviado_em_none(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu = repo.criar(_criar_followup(lead_id, conversa_id))
    repo.atualizar_status(fu.id, FollowupStatus.SEM_RESPOSTA)

    atualizado = repo.buscar_por_id(fu.id)
    assert atualizado.status == FollowupStatus.SEM_RESPOSTA
    assert atualizado.enviado_em is None


# ============================================================
# listar_do_lead / ultima_tentativa_do_lead / contar_tentativas
# ============================================================

def test_listar_do_lead_retorna_todas_em_ordem_cronologica(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=1))
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=2))
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=3))

    tentativas = repo.listar_do_lead(lead_id)

    assert len(tentativas) == 3
    assert [t.tentativa for t in tentativas] == [1, 2, 3]


def test_listar_do_lead_nao_mistura_leads_diferentes(
    repo, lead_repo, conversas_repo
):
    lead_a = lead_repo.criar(Lead(nome="Lead A"))
    conversa_a = conversas_repo.criar_conversa(Conversation(lead_id=lead_a.id))
    lead_b = lead_repo.criar(Lead(nome="Lead B"))
    conversa_b = conversas_repo.criar_conversa(Conversation(lead_id=lead_b.id))

    repo.criar(_criar_followup(lead_a.id, conversa_a.id))
    repo.criar(_criar_followup(lead_b.id, conversa_b.id))

    assert len(repo.listar_do_lead(lead_a.id)) == 1
    assert len(repo.listar_do_lead(lead_b.id)) == 1


def test_ultima_tentativa_do_lead_sem_nenhuma_retorna_none(repo, lead_e_conversa):
    lead_id, _ = lead_e_conversa
    assert repo.ultima_tentativa_do_lead(lead_id) is None


def test_ultima_tentativa_do_lead_retorna_a_mais_recente(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=1))
    segunda = repo.criar(_criar_followup(lead_id, conversa_id, tentativa=2))

    ultima = repo.ultima_tentativa_do_lead(lead_id)
    assert ultima.id == segunda.id
    assert ultima.tentativa == 2


def test_contar_tentativas_sem_nenhuma_retorna_zero(repo, lead_e_conversa):
    lead_id, _ = lead_e_conversa
    assert repo.contar_tentativas(lead_id) == 0


def test_contar_tentativas_soma_todas_independente_do_status(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu1 = repo.criar(_criar_followup(lead_id, conversa_id, tentativa=1))
    repo.marcar_enviado(fu1.id)
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=2))

    assert repo.contar_tentativas(lead_id) == 2


# ============================================================
# estatisticas
# ============================================================

def test_estatisticas_sem_followups(repo):
    stats = repo.estatisticas()
    assert stats["total"] == 0
    assert stats["por_status"] == {}


def test_estatisticas_conta_por_status(repo, lead_e_conversa):
    lead_id, conversa_id = lead_e_conversa
    fu1 = repo.criar(_criar_followup(lead_id, conversa_id, tentativa=1))
    fu2 = repo.criar(_criar_followup(lead_id, conversa_id, tentativa=2))
    repo.criar(_criar_followup(lead_id, conversa_id, tentativa=3))

    repo.marcar_enviado(fu1.id)
    repo.marcar_enviado(fu2.id)
    repo.atualizar_status(fu2.id, FollowupStatus.RESPONDIDO)

    stats = repo.estatisticas()

    assert stats["total"] == 3
    assert stats["por_status"] == {
        "enviado": 1,
        "respondido": 1,
        "pendente": 1,
    }