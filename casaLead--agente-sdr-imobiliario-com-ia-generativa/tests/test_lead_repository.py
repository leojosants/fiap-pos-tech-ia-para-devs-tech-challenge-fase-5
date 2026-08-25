"""Testes do repositório de leads (src/persistence/lead_repository.py).

Cada teste roda contra um banco SQLite temporário isolado (`tmp_path`),
com apenas o schema criado — sem carregar o seed de imóveis, que não é
necessário para nenhum teste deste módulo (leads não têm FK para
properties).

Escopo:

1. CRUD básico: `criar`, `atualizar`, `salvar` (dispatch por presença
   de id), `remover`, `buscar_por_id`.
2. Round-trip de tipos compostos — o ponto de maior risco silencioso
   do repositório: listas serializadas em JSON (`bairros_interesse`,
   `preferencias`) e enums obrigatórios/opcionais convertidos entre
   `StrEnum` e `TEXT`. Um erro de mapeamento aqui não quebra a
   inserção (SQLite aceita qualquer TEXT) — só apareceria como dado
   corrompido na leitura, silenciosamente.
3. `listar()`: filtros combináveis e as três estratégias de ordenação.
4. `estatisticas()`: agregações que alimentam o dashboard.
5. `buscar_inativos()`: a consulta da qual depende o follow-up
   automático (cenário 3.3 do enunciado) — limiar de horas e exclusão
   de leads já encaminhados/perdidos.
"""

from datetime import datetime, timedelta

import pytest

from src.core.enums import (
    Intent,
    InvestmentGoal,
    InvestorProfile,
    LeadStatus,
    LeadTemperature,
    PropertyType,
    Urgency,
    Zone,
)
from src.core.models import Lead
from src.persistence.database import create_schema, get_connection
from src.persistence.lead_repository import LeadRepository


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "leads.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


class TestCriar:

    def test_atribui_id_ao_inserir(self, repo):
        lead = repo.criar(Lead(nome="Marcos"))
        assert lead.id is not None

    def test_define_created_at_e_updated_at(self, repo):
        lead = repo.criar(Lead())
        assert lead.created_at is not None
        assert lead.updated_at is not None

    def test_lead_criado_e_recuperavel_por_id(self, repo):
        criado = repo.criar(Lead(nome="Marcos"))
        recuperado = repo.buscar_por_id(criado.id)
        assert recuperado is not None
        assert recuperado.nome == "Marcos"


class TestRoundTripDeTiposCompostos:
    """Um erro de mapeamento aqui não quebra a escrita — só corrompe
    silenciosamente o que volta na leitura."""

    def test_listas_preenchidas_sobrevivem_ao_round_trip(self, repo):
        lead = Lead(
            bairros_interesse=["Moema", "Vila Mariana"],
            preferencias=["aceita pet", "vaga extra"],
        )
        criado = repo.criar(lead)

        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.bairros_interesse == ["Moema", "Vila Mariana"]
        assert recuperado.preferencias == ["aceita pet", "vaga extra"]

    def test_listas_vazias_voltam_como_lista_vazia_nao_none(self, repo):
        criado = repo.criar(Lead())
        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.bairros_interesse == []
        assert recuperado.preferencias == []

    def test_enums_obrigatorios_sobrevivem_ao_round_trip(self, repo):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            status=LeadStatus.QUALIFICADO,
            temperature=LeadTemperature.QUENTE,
            urgencia=Urgency.IMEDIATA,
            perfil_investidor=InvestorProfile.ARROJADO,
            objetivo_investimento=InvestmentGoal.VALORIZACAO,
        )
        criado = repo.criar(lead)

        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.intent is Intent.INVESTIMENTO
        assert recuperado.status is LeadStatus.QUALIFICADO
        assert recuperado.temperature is LeadTemperature.QUENTE
        assert recuperado.urgencia is Urgency.IMEDIATA
        assert recuperado.perfil_investidor is InvestorProfile.ARROJADO
        assert recuperado.objetivo_investimento is InvestmentGoal.VALORIZACAO

    def test_enum_opcional_none_sobrevive_ao_round_trip(self, repo):
        criado = repo.criar(Lead(zona_interesse=None, tipo_imovel=None))
        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.zona_interesse is None
        assert recuperado.tipo_imovel is None

    def test_enum_opcional_preenchido_sobrevive_ao_round_trip(self, repo):
        criado = repo.criar(
            Lead(zona_interesse=Zone.OESTE, tipo_imovel=PropertyType.STUDIO)
        )
        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.zona_interesse is Zone.OESTE
        assert recuperado.tipo_imovel is PropertyType.STUDIO

    def test_numeros_opcionais_none_sobrevivem_ao_round_trip(self, repo):
        criado = repo.criar(Lead(preco_min=None, ticket_disponivel=None))
        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.preco_min is None
        assert recuperado.ticket_disponivel is None


class TestAtualizar:

    def test_sem_id_levanta_value_error(self, repo):
        with pytest.raises(ValueError, match="sem id"):
            repo.atualizar(Lead())

    def test_grava_o_novo_estado(self, repo):
        criado = repo.criar(Lead(score=0))
        criado.score = 85
        criado.temperature = LeadTemperature.QUENTE
        repo.atualizar(criado)

        recuperado = repo.buscar_por_id(criado.id)
        assert recuperado.score == 85
        assert recuperado.temperature is LeadTemperature.QUENTE

    def test_atualizar_muda_updated_at_mas_preserva_created_at(self, repo):
        criado = repo.criar(Lead())
        created_at_original = criado.created_at

        criado.updated_at = datetime.now() - timedelta(days=1)  # valor será sobrescrito
        repo.atualizar(criado)
        recuperado = repo.buscar_por_id(criado.id)

        assert recuperado.created_at == created_at_original
        assert recuperado.updated_at >= created_at_original


class TestSalvar:

    def test_lead_sem_id_e_criado(self, repo):
        lead = repo.salvar(Lead(nome="Marcos"))
        assert lead.id is not None
        assert repo.contar() == 1

    def test_lead_com_id_e_atualizado_sem_duplicar(self, repo):
        criado = repo.criar(Lead(nome="Marcos"))
        criado.nome = "Marcos Silva"

        repo.salvar(criado)

        assert repo.contar() == 1
        assert repo.buscar_por_id(criado.id).nome == "Marcos Silva"


class TestRemover:

    def test_remove_o_lead(self, repo):
        criado = repo.criar(Lead())
        repo.remover(criado.id)
        assert repo.buscar_por_id(criado.id) is None

    def test_remover_id_inexistente_nao_falha(self, repo):
        repo.remover(9999)  # não deve levantar exceção


class TestBuscarPorId:

    def test_id_inexistente_retorna_none(self, repo):
        assert repo.buscar_por_id(9999) is None


class TestListar:

    def test_sem_filtro_lista_todos(self, repo):
        repo.criar(Lead())
        repo.criar(Lead())
        assert len(repo.listar()) == 2

    def test_filtra_por_status(self, repo):
        repo.criar(Lead(status=LeadStatus.NOVO))
        repo.criar(Lead(status=LeadStatus.QUALIFICADO))

        resultado = repo.listar(status=LeadStatus.QUALIFICADO)

        assert len(resultado) == 1
        assert resultado[0].status is LeadStatus.QUALIFICADO

    def test_filtra_por_temperature(self, repo):
        repo.criar(Lead(temperature=LeadTemperature.FRIO))
        repo.criar(Lead(temperature=LeadTemperature.QUENTE))

        resultado = repo.listar(temperature=LeadTemperature.QUENTE)

        assert len(resultado) == 1
        assert resultado[0].temperature is LeadTemperature.QUENTE

    def test_filtra_por_intent(self, repo):
        repo.criar(Lead(intent=Intent.COMPRA))
        repo.criar(Lead(intent=Intent.INVESTIMENTO))

        resultado = repo.listar(intent=Intent.INVESTIMENTO)

        assert len(resultado) == 1
        assert resultado[0].intent is Intent.INVESTIMENTO

    def test_filtros_combinados(self, repo):
        repo.criar(Lead(intent=Intent.COMPRA, status=LeadStatus.QUALIFICADO))
        repo.criar(Lead(intent=Intent.COMPRA, status=LeadStatus.NOVO))
        repo.criar(Lead(intent=Intent.INVESTIMENTO, status=LeadStatus.QUALIFICADO))

        resultado = repo.listar(intent=Intent.COMPRA, status=LeadStatus.QUALIFICADO)

        assert len(resultado) == 1

    def test_ordenacao_padrao_e_por_score_decrescente(self, repo):
        repo.criar(Lead(score=10))
        repo.criar(Lead(score=90))
        repo.criar(Lead(score=50))

        resultado = repo.listar()

        assert [lead.score for lead in resultado] == [90, 50, 10]

    def test_ordenar_por_recentes(self, repo):
        primeiro = repo.criar(Lead())
        segundo = repo.criar(Lead())

        # Força um updated_at posterior no primeiro lead, simulando
        # atividade mais recente nele.
        primeiro.nome = "Atualizado"
        repo.atualizar(primeiro)

        resultado = repo.listar(ordenar_por="recentes")

        assert resultado[0].id == primeiro.id
        assert resultado[1].id == segundo.id

    def test_ordenar_por_antigos(self, repo):
        with get_connection(repo._db_path) as conn:
            conn.execute(
                "INSERT INTO leads (created_at, updated_at) VALUES (?, ?)",
                ("2020-01-01T00:00:00", "2020-01-01T00:00:00"),
            )
            conn.execute(
                "INSERT INTO leads (created_at, updated_at) VALUES (?, ?)",
                ("2025-01-01T00:00:00", "2025-01-01T00:00:00"),
            )

        resultado = repo.listar(ordenar_por="antigos")

        assert resultado[0].created_at < resultado[1].created_at

    def test_ordenar_por_valor_desconhecido_usa_padrao_score(self, repo):
        repo.criar(Lead(score=10))
        repo.criar(Lead(score=90))

        resultado = repo.listar(ordenar_por="valor-que-nao-existe")

        assert [lead.score for lead in resultado] == [90, 10]

    def test_respeita_o_limite(self, repo):
        for _ in range(5):
            repo.criar(Lead())

        assert len(repo.listar(limite=2)) == 2


class TestContar:

    def test_zero_sem_leads(self, repo):
        assert repo.contar() == 0

    def test_reflete_quantidade_apos_insercoes(self, repo):
        repo.criar(Lead())
        repo.criar(Lead())
        assert repo.contar() == 2


class TestEstatisticas:

    def test_sem_leads_nao_gera_divisao_por_zero(self, repo):
        resultado = repo.estatisticas()

        assert resultado["total"] == 0
        assert resultado["por_status"] == {}
        assert resultado["por_temperatura"] == {}
        assert resultado["por_intencao"] == {}
        assert resultado["score_medio"] == 0.0

    def test_agrega_por_status_temperatura_intencao_e_score_medio(self, repo):
        repo.criar(
            Lead(status=LeadStatus.NOVO, temperature=LeadTemperature.FRIO,
                 intent=Intent.COMPRA, score=0)
        )
        repo.criar(
            Lead(status=LeadStatus.QUALIFICADO, temperature=LeadTemperature.QUENTE,
                 intent=Intent.COMPRA, score=100)
        )

        resultado = repo.estatisticas()

        assert resultado["total"] == 2
        assert resultado["por_status"] == {"novo": 1, "qualificado": 1}
        assert resultado["por_temperatura"] == {"frio": 1, "quente": 1}
        assert resultado["por_intencao"] == {"compra": 2}
        assert resultado["score_medio"] == 50.0


class TestBuscarInativos:

    def _forcar_updated_at(self, repo, lead_id: int, quando: datetime) -> None:
        """Simula inatividade sem esperar tempo real passar."""
        with get_connection(repo._db_path) as conn:
            conn.execute(
                "UPDATE leads SET updated_at = ? WHERE id = ?",
                (quando.isoformat(), lead_id),
            )

    def test_lead_recem_criado_nao_aparece_como_inativo(self, repo):
        repo.criar(Lead())
        assert repo.buscar_inativos(horas=24) == []

    def test_lead_parado_ha_mais_tempo_que_o_limiar_aparece(self, repo):
        lead = repo.criar(Lead())
        self._forcar_updated_at(repo, lead.id, datetime.now() - timedelta(hours=48))

        inativos = repo.buscar_inativos(horas=24)

        assert len(inativos) == 1
        assert inativos[0].id == lead.id

    def test_lead_parado_ha_menos_tempo_que_o_limiar_nao_aparece(self, repo):
        lead = repo.criar(Lead())
        self._forcar_updated_at(repo, lead.id, datetime.now() - timedelta(hours=2))

        assert repo.buscar_inativos(horas=24) == []

    def test_exclui_leads_ja_encaminhados_mesmo_inativos(self, repo):
        lead = repo.criar(Lead(status=LeadStatus.ENCAMINHADO))
        self._forcar_updated_at(repo, lead.id, datetime.now() - timedelta(hours=48))

        assert repo.buscar_inativos(horas=24) == []

    def test_exclui_leads_perdidos_mesmo_inativos(self, repo):
        lead = repo.criar(Lead(status=LeadStatus.PERDIDO))
        self._forcar_updated_at(repo, lead.id, datetime.now() - timedelta(hours=48))

        assert repo.buscar_inativos(horas=24) == []

    def test_ordena_por_score_decrescente(self, repo):
        lead_a = repo.criar(Lead(score=20))
        lead_b = repo.criar(Lead(score=80))
        self._forcar_updated_at(repo, lead_a.id, datetime.now() - timedelta(hours=48))
        self._forcar_updated_at(repo, lead_b.id, datetime.now() - timedelta(hours=48))

        inativos = repo.buscar_inativos(horas=24)

        assert [lead.id for lead in inativos] == [lead_b.id, lead_a.id]