"""Testes da camada de banco de dados (src/persistence/database.py).

Cada teste roda contra um banco SQLite temporário isolado (via
`tmp_path`), nunca contra `data/runtime/casalead.db` — mesmo padrão já
usado em `test_property_repository.py`.

Escopo:

1. `create_schema()`: as sete tabelas existem e são criadas de forma
   idempotente (`IF NOT EXISTS` — chamar duas vezes não falha).
2. `get_connection()`: `PRAGMA foreign_keys = ON` está de fato ativo
   (chave estrangeira inválida é rejeitada), `row_factory` permite
   acesso por nome de coluna, commit automático em sucesso e rollback
   automático em exceção.
3. `load_seed_properties()`: idempotência (não duplica em chamadas
   repetidas), `force=True` recarrega do zero, e o erro claro quando o
   arquivo de seed não existe.
4. `bootstrap()`: composição de `create_schema` + `load_seed_properties`,
   idempotente ponta a ponta — a mesma propriedade de que depende a
   confiabilidade do deploy no Streamlit Cloud (filesystem efêmero,
   Seção 5 do contexto do projeto).
5. `reset_database()` e `get_db_path()`.
6. `ON DELETE CASCADE`: apagar um lead remove conversas, mensagens,
   agendamentos e follow-ups vinculados — comportamento do schema que
   nenhum teste de repositório individual teria motivo para exercitar.
"""

import sqlite3

import pytest

from src.persistence.database import (
    DEFAULT_DB_PATH,
    bootstrap,
    create_schema,
    get_connection,
    get_db_path,
    load_seed_properties,
    reset_database,
)

TABELAS_ESPERADAS = {
    "properties",
    "leads",
    "conversations",
    "messages",
    "appointments",
    "followups",
    "events",
}


def _tabelas_existentes(db_path) -> set[str]:
    with get_connection(db_path) as conn:
        linhas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {linha["name"] for linha in linhas}


class TestCreateSchema:

    def test_cria_as_sete_tabelas_do_sistema(self, tmp_path):
        db_path = tmp_path / "schema.db"
        create_schema(db_path)

        tabelas = _tabelas_existentes(db_path)

        assert TABELAS_ESPERADAS.issubset(tabelas)

    def test_e_idempotente_chamar_duas_vezes_nao_falha(self, tmp_path):
        db_path = tmp_path / "schema.db"
        create_schema(db_path)
        create_schema(db_path)  # não deve levantar exceção

        assert TABELAS_ESPERADAS.issubset(_tabelas_existentes(db_path))

    def test_cria_o_diretorio_pai_quando_nao_existe(self, tmp_path):
        db_path = tmp_path / "subpasta_nova" / "schema.db"
        create_schema(db_path)

        assert db_path.exists()


class TestGetConnection:

    def test_row_factory_permite_acesso_por_nome_de_coluna(self, tmp_path):
        db_path = tmp_path / "conexao.db"
        create_schema(db_path)

        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO leads (created_at, updated_at) VALUES ('2026-01-01', '2026-01-01')"
            )

        with get_connection(db_path) as conn:
            linha = conn.execute("SELECT * FROM leads").fetchone()

        assert linha["status"] == "novo"  # acesso por nome, não por índice

    def test_foreign_keys_pragma_esta_ativo(self, tmp_path):
        db_path = tmp_path / "fk.db"
        create_schema(db_path)

        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(db_path) as conn:
                # lead_id=999 não existe — deve ser rejeitado pela FK
                conn.execute(
                    "INSERT INTO conversations "
                    "(lead_id, started_at, last_activity_at) "
                    "VALUES (999, '2026-01-01', '2026-01-01')"
                )

    def test_commit_automatico_em_sucesso(self, tmp_path):
        db_path = tmp_path / "commit.db"
        create_schema(db_path)

        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO leads (created_at, updated_at) VALUES ('2026-01-01', '2026-01-01')"
            )

        # Nova conexão, mesmo arquivo — se o commit não tivesse
        # ocorrido, esta leitura veria a tabela vazia.
        with get_connection(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        assert total == 1

    def test_rollback_automatico_em_excecao(self, tmp_path):
        db_path = tmp_path / "rollback.db"
        create_schema(db_path)

        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(db_path) as conn:
                conn.execute(
                    "INSERT INTO leads (created_at, updated_at) VALUES ('2026-01-01', '2026-01-01')"
                )
                # Segunda instrução falha (NOT NULL violado em
                # started_at) — a inserção do lead acima não deve
                # sobreviver ao rollback.
                conn.execute("INSERT INTO conversations (lead_id) VALUES (1)")

        with get_connection(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        assert total == 0


class TestLoadSeedProperties:

    def test_carrega_os_60_imoveis_do_seed_real(self, tmp_path):
        db_path = tmp_path / "seed.db"
        create_schema(db_path)

        inseridos = load_seed_properties(db_path)

        assert inseridos == 60

    def test_e_idempotente_segunda_chamada_nao_duplica(self, tmp_path):
        db_path = tmp_path / "seed.db"
        create_schema(db_path)
        load_seed_properties(db_path)

        segunda_chamada = load_seed_properties(db_path)

        assert segunda_chamada == 0
        with get_connection(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        assert total == 60

    def test_force_recarrega_do_zero(self, tmp_path):
        db_path = tmp_path / "seed.db"
        create_schema(db_path)
        load_seed_properties(db_path)

        recarregados = load_seed_properties(db_path, force=True)

        assert recarregados == 60
        with get_connection(db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        assert total == 60  # sem duplicar, mesmo recarregando

    def test_arquivo_de_seed_inexistente_levanta_erro_claro(self, tmp_path):
        db_path = tmp_path / "seed.db"
        create_schema(db_path)
        seed_inexistente = tmp_path / "nao_existe.json"

        with pytest.raises(FileNotFoundError, match="generate_properties"):
            load_seed_properties(db_path, seed_path=seed_inexistente)


class TestBootstrap:

    def test_cria_schema_e_carrega_seed_em_uma_chamada(self, tmp_path):
        db_path = tmp_path / "bootstrap.db"

        resultado = bootstrap(db_path)

        assert resultado == {"imoveis_inseridos": 60, "imoveis_total": 60}
        assert TABELAS_ESPERADAS.issubset(_tabelas_existentes(db_path))

    def test_e_idempotente_ponta_a_ponta(self, tmp_path):
        # Propriedade da qual depende o Streamlit Cloud: bootstrap()
        # pode ser chamado a cada reciclagem do container sem duplicar
        # dados nem falhar.
        db_path = tmp_path / "bootstrap.db"
        bootstrap(db_path)

        segunda_execucao = bootstrap(db_path)

        assert segunda_execucao == {"imoveis_inseridos": 0, "imoveis_total": 60}


class TestGetDbPathEReset:

    def test_get_db_path_usa_padrao_sem_variavel_de_ambiente(self, monkeypatch):
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        assert get_db_path() == DEFAULT_DB_PATH

    def test_get_db_path_respeita_variavel_de_ambiente(self, monkeypatch, tmp_path):
        caminho_customizado = str(tmp_path / "outro.db")
        monkeypatch.setenv("DATABASE_PATH", caminho_customizado)

        assert str(get_db_path()) == caminho_customizado

    def test_reset_database_apaga_o_arquivo(self, tmp_path):
        db_path = tmp_path / "para_apagar.db"
        create_schema(db_path)
        assert db_path.exists()

        reset_database(db_path)

        assert not db_path.exists()

    def test_reset_database_sem_arquivo_nao_falha(self, tmp_path):
        db_path = tmp_path / "nunca_existiu.db"
        reset_database(db_path)  # não deve levantar exceção


class TestCascataDeExclusao:
    """ON DELETE CASCADE do schema: apagar um lead deve arrastar tudo
    que depende dele — conversas, mensagens, agendamentos e
    follow-ups. Nenhum teste de repositório individual exercitaria essa
    cadeia completa, porque cada repositório só cuida da própria
    tabela."""

    def test_apagar_lead_remove_conversas_mensagens_agendamentos_e_followups(
        self, tmp_path
    ):
        db_path = tmp_path / "cascata.db"
        create_schema(db_path)

        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO leads (id, created_at, updated_at) "
                "VALUES (1, '2026-01-01', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO conversations "
                "(id, lead_id, started_at, last_activity_at) "
                "VALUES (1, 1, '2026-01-01', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (1, 'lead', 'Oi', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO appointments "
                "(lead_id, tipo, data_hora, created_at) "
                "VALUES (1, 'visita_imovel', '2026-02-01', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO followups "
                "(lead_id, conversation_id, agendado_para) "
                "VALUES (1, 1, '2026-01-02')"
            )

        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM leads WHERE id = 1")

        with get_connection(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM followups").fetchone()[0] == 0

    def test_apagar_property_referenciada_apenas_zera_property_id_do_agendamento(
        self, tmp_path
    ):
        # appointments.property_id usa ON DELETE SET NULL, não CASCADE
        # — o agendamento em si é preservado mesmo se o imóvel sumir.
        db_path = tmp_path / "cascata_property.db"
        create_schema(db_path)

        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO leads (id, created_at, updated_at) "
                "VALUES (1, '2026-01-01', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO properties "
                "(id, codigo, titulo, tipo, operacao, zona, bairro) "
                "VALUES (1, 'AP-999', 'Teste', 'apartamento', 'venda', 'sul', 'Moema')"
            )
            conn.execute(
                "INSERT INTO appointments "
                "(id, lead_id, property_id, tipo, data_hora, created_at) "
                "VALUES (1, 1, 1, 'visita_imovel', '2026-02-01', '2026-01-01')"
            )

        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM properties WHERE id = 1")

        with get_connection(db_path) as conn:
            compromisso = conn.execute(
                "SELECT * FROM appointments WHERE id = 1"
            ).fetchone()

        assert compromisso is not None
        assert compromisso["property_id"] is None