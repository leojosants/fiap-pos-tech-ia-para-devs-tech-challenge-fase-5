"""Gerenciamento do banco de dados SQLite do CasaLead.

Responsabilidades:
    - Definir o schema das sete tabelas do sistema.
    - Fornecer conexões configuradas para os repositórios.
    - Executar o bootstrap: criar o schema e carregar a base de
      imóveis a partir do seed versionado, quando necessário.

O banco reside em data/runtime/ e é um artefato derivado — nunca
versionado. Pode ser apagado a qualquer momento; o bootstrap o
reconstrói na próxima execução.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

# Raiz do projeto (casaLead--agente-sdr-imobiliario-com-ia-generativa/),
# calculada a partir da localização deste arquivo — não do diretório de
# trabalho do processo. Necessário porque o Streamlit Community Cloud
# roda o app a partir da raiz do repositório Git (que contém esta pasta
# como subdiretório), não de dentro dela: um caminho relativo simples
# ("data/seed/...") resolveria contra o lugar errado e falharia com
# FileNotFoundError apenas em produção, nunca em desenvolvimento local
# (onde sempre rodamos "uv run streamlit run main.py" já de dentro
# desta pasta, mascarando o problema).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "runtime" / "casalead.db"
SEED_PROPERTIES = _PROJECT_ROOT / "data" / "seed" / "properties.json"


# ============================================================
# SCHEMA
# ============================================================

SCHEMA = """
-- Base simulada de imóveis (carregada do seed)
CREATE TABLE IF NOT EXISTS properties (
    id                      INTEGER PRIMARY KEY,
    codigo                  TEXT    NOT NULL UNIQUE,
    titulo                  TEXT    NOT NULL,
    tipo                    TEXT    NOT NULL,
    operacao                TEXT    NOT NULL,
    zona                    TEXT    NOT NULL,
    bairro                  TEXT    NOT NULL,
    endereco_aproximado     TEXT    NOT NULL DEFAULT '',
    preco_venda             REAL,
    preco_aluguel           REAL,
    condominio              REAL    NOT NULL DEFAULT 0,
    iptu                    REAL    NOT NULL DEFAULT 0,
    quartos                 INTEGER NOT NULL DEFAULT 0,
    suites                  INTEGER NOT NULL DEFAULT 0,
    banheiros               INTEGER NOT NULL DEFAULT 1,
    vagas                   INTEGER NOT NULL DEFAULT 0,
    area_util               REAL    NOT NULL DEFAULT 0,
    andar                   INTEGER,
    ano_construcao          INTEGER NOT NULL DEFAULT 2010,
    mobiliado               INTEGER NOT NULL DEFAULT 0,
    aceita_pet              INTEGER NOT NULL DEFAULT 1,
    caracteristicas         TEXT    NOT NULL DEFAULT '[]',
    descricao               TEXT    NOT NULL DEFAULT '',
    rentabilidade_estimada  REAL    NOT NULL DEFAULT 0,
    potencial_valorizacao   REAL    NOT NULL DEFAULT 0,
    perfil_investimento     TEXT    NOT NULL DEFAULT 'moderado'
);

CREATE INDEX IF NOT EXISTS idx_properties_zona    ON properties(zona);
CREATE INDEX IF NOT EXISTS idx_properties_tipo    ON properties(tipo);
CREATE INDEX IF NOT EXISTS idx_properties_quartos ON properties(quartos);
CREATE INDEX IF NOT EXISTS idx_properties_venda   ON properties(preco_venda);


-- Leads atendidos pelo agente
CREATE TABLE IF NOT EXISTS leads (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                    TEXT    NOT NULL DEFAULT '',
    telefone                TEXT    NOT NULL DEFAULT '',
    email                   TEXT    NOT NULL DEFAULT '',
    canal_origem            TEXT    NOT NULL DEFAULT 'site',
    intent                  TEXT    NOT NULL DEFAULT 'indefinida',
    status                  TEXT    NOT NULL DEFAULT 'novo',
    temperature             TEXT    NOT NULL DEFAULT 'frio',
    score                   INTEGER NOT NULL DEFAULT 0,

    -- Slots de compra e aluguel
    zona_interesse          TEXT,
    bairros_interesse       TEXT    NOT NULL DEFAULT '[]',
    tipo_imovel             TEXT,
    preco_min               REAL,
    preco_max               REAL,
    quartos_desejados       INTEGER,
    vagas_desejadas         INTEGER,
    preferencias            TEXT    NOT NULL DEFAULT '[]',
    urgencia                TEXT    NOT NULL DEFAULT 'nao_informada',
    disponibilidade_reuniao TEXT    NOT NULL DEFAULT '',

    -- Slots de investimento
    perfil_investidor       TEXT    NOT NULL DEFAULT 'nao_informado',
    ticket_disponivel       REAL,
    objetivo_investimento   TEXT    NOT NULL DEFAULT 'nao_informado',
    expectativa_retorno     REAL,
    prazo_investimento      TEXT    NOT NULL DEFAULT '',

    resumo_corretor         TEXT    NOT NULL DEFAULT '',
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_status      ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_temperature ON leads(temperature);
CREATE INDEX IF NOT EXISTS idx_leads_intent      ON leads(intent);


-- Sessões de atendimento
CREATE TABLE IF NOT EXISTS conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id           INTEGER NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'ativa',
    canal             TEXT    NOT NULL DEFAULT 'web',
    started_at        TEXT    NOT NULL,
    last_activity_at  TEXT    NOT NULL,
    ended_at          TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversations_lead   ON conversations(lead_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);


-- Histórico turno a turno (memória conversacional)
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL,
    role             TEXT    NOT NULL,
    content          TEXT    NOT NULL,
    modelo_usado     TEXT    NOT NULL DEFAULT '',
    latencia_ms      INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);


-- Visitas e reuniões
CREATE TABLE IF NOT EXISTS appointments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id      INTEGER NOT NULL,
    property_id  INTEGER,
    tipo         TEXT    NOT NULL,
    data_hora    TEXT    NOT NULL,
    corretor     TEXT    NOT NULL DEFAULT '',
    observacoes  TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'agendado',
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (lead_id)     REFERENCES leads(id)      ON DELETE CASCADE,
    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_appointments_lead ON appointments(lead_id);


-- Tentativas de reengajamento
CREATE TABLE IF NOT EXISTS followups (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id          INTEGER NOT NULL,
    conversation_id  INTEGER NOT NULL,
    tentativa        INTEGER NOT NULL DEFAULT 1,
    mensagem         TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'pendente',
    motivo           TEXT    NOT NULL DEFAULT '',
    agendado_para    TEXT    NOT NULL,
    enviado_em       TEXT,
    FOREIGN KEY (lead_id)         REFERENCES leads(id)         ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_followups_lead   ON followups(lead_id);
CREATE INDEX IF NOT EXISTS idx_followups_status ON followups(status);


-- Log estruturado para observabilidade e métricas
CREATE TABLE IF NOT EXISTS events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo             TEXT    NOT NULL,
    lead_id          INTEGER,
    conversation_id  INTEGER,
    detalhes         TEXT    NOT NULL DEFAULT '{}',
    created_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_tipo    ON events(tipo);
CREATE INDEX IF NOT EXISTS idx_events_lead    ON events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
"""


# ============================================================
# CONEXÃO
# ============================================================

def get_db_path() -> Path:
    """Resolve o caminho do banco a partir da variável de ambiente."""
    return Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Fornece uma conexão configurada, com commit e fechamento automáticos.

    Em caso de exceção, executa rollback antes de propagar o erro,
    garantindo que operações parciais não fiquem gravadas.
    """
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row          # acesso por nome de coluna
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# BOOTSTRAP
# ============================================================

def create_schema(db_path: Path | None = None) -> None:
    """Cria todas as tabelas e índices, se ainda não existirem."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def _properties_carregados(conn: sqlite3.Connection) -> int:
    """Conta os imóveis já presentes na base."""
    return conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]


def load_seed_properties(
    db_path: Path | None = None,
    seed_path: Path = SEED_PROPERTIES,
    force: bool = False,
) -> int:
    """Carrega a base de imóveis do JSON versionado para o SQLite.

    Idempotente: sem force=True, não faz nada se a tabela já estiver
    populada. Retorna a quantidade de imóveis inseridos.
    """
    if not seed_path.exists():
        raise FileNotFoundError(
            f"Seed de imóveis não encontrado em {seed_path}. "
            "Execute: uv run python -m scripts.generate_properties"
        )

    with get_connection(db_path) as conn:
        if not force and _properties_carregados(conn) > 0:
            return 0

        if force:
            conn.execute("DELETE FROM properties")

        imoveis = json.loads(seed_path.read_text(encoding="utf-8"))

        registros = [
            (
                im["id"], im["codigo"], im["titulo"], im["tipo"], im["operacao"],
                im["zona"], im["bairro"], im["endereco_aproximado"],
                im["preco_venda"], im["preco_aluguel"], im["condominio"], im["iptu"],
                im["quartos"], im["suites"], im["banheiros"], im["vagas"],
                im["area_util"], im["andar"], im["ano_construcao"],
                int(im["mobiliado"]), int(im["aceita_pet"]),
                json.dumps(im["caracteristicas"], ensure_ascii=False),
                im["descricao"],
                im["rentabilidade_estimada"], im["potencial_valorizacao"],
                im["perfil_investimento"],
            )
            for im in imoveis
        ]

        conn.executemany(
            """
            INSERT INTO properties (
                id, codigo, titulo, tipo, operacao, zona, bairro,
                endereco_aproximado, preco_venda, preco_aluguel,
                condominio, iptu, quartos, suites, banheiros, vagas,
                area_util, andar, ano_construcao, mobiliado, aceita_pet,
                caracteristicas, descricao, rentabilidade_estimada,
                potencial_valorizacao, perfil_investimento
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            registros,
        )
        return len(registros)


def bootstrap(db_path: Path | None = None) -> dict[str, int]:
    """Prepara o banco para uso: cria o schema e carrega o seed.

    Idempotente — seguro para ser chamado a cada início da aplicação.
    É o mecanismo que garante que o sistema sempre encontre uma base
    de imóveis populada, mesmo após a reciclagem do container no
    Streamlit Cloud (filesystem efêmero).
    """
    create_schema(db_path)
    inseridos = load_seed_properties(db_path)

    with get_connection(db_path) as conn:
        total = _properties_carregados(conn)

    return {"imoveis_inseridos": inseridos, "imoveis_total": total}


def reset_database(db_path: Path | None = None) -> None:
    """Apaga o arquivo de banco. Usado em testes e no botão de reset."""
    path = db_path or get_db_path()
    if path.exists():
        path.unlink()