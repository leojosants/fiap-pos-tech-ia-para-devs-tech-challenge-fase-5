"""Testes da camada de persistência de agendamentos.

Diferente de test_property_repository.py — cujo fixture é escopado por
módulo porque os testes só leem uma base de imóveis compartilhada —,
aqui cada teste recebe um banco isolado (fixture padrão, escopo de
função). Agendamento é uma entidade que os próprios testes criam e
alteram; compartilhar o banco entre testes tornaria a ordem de
execução relevante para o resultado, o que é frágil e difícil de
depurar quando um teste falha.
"""

from datetime import datetime, timedelta

import pytest

from src.core.enums import AppointmentStatus, AppointmentType
from src.core.models import Appointment, Lead
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.database import create_schema, get_connection
from src.persistence.lead_repository import LeadRepository


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def db_path(tmp_path):
    """Banco temporário e isolado, com apenas o schema (sem seed de imóveis)."""
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def repo(db_path) -> AppointmentRepository:
    return AppointmentRepository(db_path)


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def lead_id(lead_repo) -> int:
    """Um lead persistido, satisfazendo a foreign key de appointments."""
    lead = lead_repo.criar(Lead(nome="Lead de Teste"))
    return lead.id


def _criar_agendamento(
    lead_id: int,
    *,
    dias_no_futuro: int = 2,
    tipo: AppointmentType = AppointmentType.VISITA_IMOVEL,
    status: AppointmentStatus = AppointmentStatus.AGENDADO,
) -> Appointment:
    """Fábrica de Appointment para reduzir repetição nos testes."""
    return Appointment(
        lead_id=lead_id,
        tipo=tipo,
        data_hora=datetime.now() + timedelta(days=dias_no_futuro),
        corretor="Ana Corretora",
        observacoes="Gerado pelo teste",
        status=status,
    )


# ============================================================
# Escrita e leitura básica
# ============================================================

def test_criar_atribui_id(repo, lead_id):
    ap = repo.criar(_criar_agendamento(lead_id))
    assert ap.id is not None


def test_criar_exige_lead_existente(repo):
    """A FK para leads deve ser respeitada — não é permitido agendar
    para um lead_id inexistente."""
    ap = _criar_agendamento(lead_id=99999)
    with pytest.raises(Exception):
        repo.criar(ap)


def test_buscar_por_id_existente(repo, lead_id):
    criado = repo.criar(_criar_agendamento(lead_id))
    encontrado = repo.buscar_por_id(criado.id)

    assert encontrado is not None
    assert encontrado.lead_id == lead_id
    assert encontrado.tipo == AppointmentType.VISITA_IMOVEL
    assert encontrado.status == AppointmentStatus.AGENDADO
    assert encontrado.corretor == "Ana Corretora"


def test_buscar_por_id_inexistente_retorna_none(repo):
    assert repo.buscar_por_id(99999) is None


def test_data_hora_preservada_com_precisao(repo, lead_id):
    """Garante que a conversão datetime <-> TEXT (ISO 8601) não perde
    informação — essencial para o scheduling_agent comparar horários."""
    momento = datetime(2026, 9, 15, 14, 30, 0)
    ap = Appointment(
        lead_id=lead_id,
        tipo=AppointmentType.REUNIAO_ONLINE,
        data_hora=momento,
    )
    criado = repo.criar(ap)
    encontrado = repo.buscar_por_id(criado.id)
    assert encontrado.data_hora == momento


# ============================================================
# Atualização de status
# ============================================================

def test_atualizar_status_altera_status(repo, lead_id):
    ap = repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(ap.id, AppointmentStatus.CONFIRMADO)

    atualizado = repo.buscar_por_id(ap.id)
    assert atualizado.status == AppointmentStatus.CONFIRMADO


def test_atualizar_status_nao_altera_outros_campos(repo, lead_id):
    ap = repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(ap.id, AppointmentStatus.CANCELADO)

    atualizado = repo.buscar_por_id(ap.id)
    assert atualizado.corretor == "Ana Corretora"
    assert atualizado.observacoes == "Gerado pelo teste"


# ============================================================
# listar_do_lead
# ============================================================

def test_listar_do_lead_retorna_todos(repo, lead_id):
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=1))
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=5))

    resultado = repo.listar_do_lead(lead_id)
    assert len(resultado) == 2


def test_listar_do_lead_ordena_por_data(repo, lead_id):
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=5))
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=1))

    resultado = repo.listar_do_lead(lead_id)
    assert resultado[0].data_hora < resultado[1].data_hora


def test_listar_do_lead_apenas_futuros_exclui_passado(repo, lead_id):
    passado = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=-3))
    futuro = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=3))

    resultado = repo.listar_do_lead(lead_id, apenas_futuros=True)

    ids = {ap.id for ap in resultado}
    assert futuro.id in ids
    assert passado.id not in ids


def test_listar_do_lead_nao_mistura_leads_diferentes(repo, lead_repo):
    lead_a = lead_repo.criar(Lead(nome="Lead A")).id
    lead_b = lead_repo.criar(Lead(nome="Lead B")).id

    repo.criar(_criar_agendamento(lead_a))
    repo.criar(_criar_agendamento(lead_b))

    assert len(repo.listar_do_lead(lead_a)) == 1
    assert len(repo.listar_do_lead(lead_b)) == 1


# ============================================================
# proximo_agendamento_do_lead — usado pelo scheduling_agent
# ============================================================

def test_proximo_agendamento_do_lead_sem_agendamento_retorna_none(repo, lead_id):
    assert repo.proximo_agendamento_do_lead(lead_id) is None


def test_proximo_agendamento_do_lead_encontra_agendado(repo, lead_id):
    criado = repo.criar(_criar_agendamento(lead_id))
    proximo = repo.proximo_agendamento_do_lead(lead_id)

    assert proximo is not None
    assert proximo.id == criado.id


def test_proximo_agendamento_do_lead_tambem_encontra_confirmado(repo, lead_id):
    """Confirmado ainda é um compromisso ativo — não deve ser ignorado."""
    criado = repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(criado.id, AppointmentStatus.CONFIRMADO)

    proximo = repo.proximo_agendamento_do_lead(lead_id)
    assert proximo is not None
    assert proximo.id == criado.id


def test_proximo_agendamento_do_lead_ignora_cancelado(repo, lead_id):
    """Evita que o agente ofereça reagendar em cima de um compromisso
    que o próprio lead já cancelou."""
    criado = repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(criado.id, AppointmentStatus.CANCELADO)

    assert repo.proximo_agendamento_do_lead(lead_id) is None


def test_proximo_agendamento_do_lead_ignora_realizado(repo, lead_id):
    criado = repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(criado.id, AppointmentStatus.REALIZADO)

    assert repo.proximo_agendamento_do_lead(lead_id) is None


def test_proximo_agendamento_do_lead_retorna_o_mais_proximo(repo, lead_id):
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=10))
    mais_proximo = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=2))

    proximo = repo.proximo_agendamento_do_lead(lead_id)
    assert proximo.id == mais_proximo.id


def test_proximo_agendamento_do_lead_ignora_compromisso_passado(repo, lead_id):
    """Um agendamento 'agendado' que já passou (não confirmado a tempo)
    não deve ser oferecido como 'seu próximo compromisso'."""
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=-1))
    assert repo.proximo_agendamento_do_lead(lead_id) is None


# ============================================================
# listar_proximos — insumo futuro do dashboard/page_broker
# ============================================================

def test_listar_proximos_respeita_janela_de_dias(repo, lead_id):
    dentro = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=3))
    fora = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=30))

    resultado = repo.listar_proximos(dias=7)
    ids = {ap.id for ap in resultado}

    assert dentro.id in ids
    assert fora.id not in ids


def test_listar_proximos_exclui_passado(repo, lead_id):
    repo.criar(_criar_agendamento(lead_id, dias_no_futuro=-1))
    resultado = repo.listar_proximos(dias=7)
    assert resultado == []


def test_listar_proximos_filtra_por_status(repo, lead_id):
    ap1 = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=1))
    ap2 = repo.criar(_criar_agendamento(lead_id, dias_no_futuro=2))
    repo.atualizar_status(ap2.id, AppointmentStatus.CONFIRMADO)

    apenas_agendados = repo.listar_proximos(dias=7, status=AppointmentStatus.AGENDADO)
    assert {ap.id for ap in apenas_agendados} == {ap1.id}


def test_listar_proximos_reune_varios_leads(repo, lead_repo):
    lead_a = lead_repo.criar(Lead(nome="Lead A")).id
    lead_b = lead_repo.criar(Lead(nome="Lead B")).id

    repo.criar(_criar_agendamento(lead_a, dias_no_futuro=1))
    repo.criar(_criar_agendamento(lead_b, dias_no_futuro=2))

    resultado = repo.listar_proximos(dias=7)
    assert len(resultado) == 2


def test_listar_proximos_respeita_limite(repo, lead_id):
    for i in range(5):
        repo.criar(_criar_agendamento(lead_id, dias_no_futuro=i + 1))

    resultado = repo.listar_proximos(dias=7, limite=3)
    assert len(resultado) == 3


# ============================================================
# estatisticas
# ============================================================

def test_estatisticas_sem_agendamentos(repo):
    stats = repo.estatisticas()
    assert stats["total"] == 0
    assert stats["por_status"] == {}


def test_estatisticas_conta_por_status(repo, lead_id):
    ap1 = repo.criar(_criar_agendamento(lead_id))
    ap2 = repo.criar(_criar_agendamento(lead_id))
    repo.criar(_criar_agendamento(lead_id))
    repo.atualizar_status(ap1.id, AppointmentStatus.CONFIRMADO)
    repo.atualizar_status(ap2.id, AppointmentStatus.CANCELADO)

    stats = repo.estatisticas()

    assert stats["total"] == 3
    assert stats["por_status"] == {
        "confirmado": 1,
        "cancelado": 1,
        "agendado": 1,
    }