"""Testes do repositório de conversas, mensagens e eventos
(src/persistence/conversation_repository.py).

Cada teste roda contra um banco SQLite temporário isolado (`tmp_path`),
com o schema criado e um lead já persistido (via `LeadRepository`, já
coberto em `test_lead_repository.py`) — necessário porque
`conversations` tem FK obrigatória para `leads`.

Escopo:

1. Conversas: criação, busca, a consulta de continuidade
   (`conversa_ativa_do_lead` — base do requisito "continuidade da
   conversa" da Seção 4), listagem por lead e mudança de status
   (incluindo o efeito colateral de `ended_at` só em status terminais).
2. Mensagens: gravação, o efeito colateral de atualizar
   `last_activity_at` da conversa a cada mensagem (do qual depende o
   follow-up), leitura com e sem limite, e a tradução de papéis para o
   formato da API de chat (`historico_para_llm`).
3. Eventos: gravação com detalhes arbitrários serializados em JSON,
   filtros de listagem e a agregação usada no painel de métricas.
"""

from datetime import datetime, timedelta

import pytest

from src.core.enums import ConversationStatus, EventType, MessageRole
from src.core.models import Conversation, Lead, Message
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema, get_connection
from src.persistence.lead_repository import LeadRepository


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "conversas.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def lead_id(db_path) -> int:
    return LeadRepository(db_path).criar(Lead()).id


@pytest.fixture
def repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


# ============================================================
# CONVERSAS
# ============================================================


class TestCriarConversa:

    def test_atribui_id(self, repo, lead_id):
        conversa = repo.criar_conversa(Conversation(lead_id=lead_id))
        assert conversa.id is not None

    def test_define_started_at_e_last_activity_at(self, repo, lead_id):
        conversa = repo.criar_conversa(Conversation(lead_id=lead_id))
        assert conversa.started_at is not None
        assert conversa.last_activity_at is not None

    def test_conversa_criada_e_recuperavel(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id, canal="whatsapp"))
        recuperada = repo.buscar_conversa(criada.id)

        assert recuperada is not None
        assert recuperada.lead_id == lead_id
        assert recuperada.canal == "whatsapp"
        assert recuperada.status is ConversationStatus.ATIVA
        assert recuperada.ended_at is None


class TestBuscarConversa:

    def test_id_inexistente_retorna_none(self, repo):
        assert repo.buscar_conversa(9999) is None


class TestConversaAtivaDoLead:

    def test_sem_nenhuma_conversa_retorna_none(self, repo, lead_id):
        assert repo.conversa_ativa_do_lead(lead_id) is None

    def test_conversa_ativa_e_encontrada(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        encontrada = repo.conversa_ativa_do_lead(lead_id)

        assert encontrada is not None
        assert encontrada.id == criada.id

    def test_conversa_aguardando_lead_tambem_e_encontrada(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.AGUARDANDO_LEAD)

        encontrada = repo.conversa_ativa_do_lead(lead_id)

        assert encontrada is not None
        assert encontrada.status is ConversationStatus.AGUARDANDO_LEAD

    def test_conversa_encerrada_nao_e_encontrada(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.ENCERRADA)

        assert repo.conversa_ativa_do_lead(lead_id) is None

    def test_nao_mistura_conversas_de_leads_diferentes(self, repo, db_path):
        outro_lead_id = LeadRepository(db_path).criar(Lead()).id
        repo.criar_conversa(Conversation(lead_id=outro_lead_id))

        lead_sem_conversa_id = LeadRepository(db_path).criar(Lead()).id
        assert repo.conversa_ativa_do_lead(lead_sem_conversa_id) is None


class TestListarConversasDoLead:

    def test_ordem_cronologica(self, repo, lead_id):
        primeira = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(primeira.id, ConversationStatus.ENCERRADA)
        segunda = repo.criar_conversa(Conversation(lead_id=lead_id))

        resultado = repo.listar_conversas_do_lead(lead_id)

        assert [c.id for c in resultado] == [primeira.id, segunda.id]

    def test_nao_mistura_leads_diferentes(self, repo, db_path, lead_id):
        outro_lead_id = LeadRepository(db_path).criar(Lead()).id
        repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.criar_conversa(Conversation(lead_id=outro_lead_id))

        assert len(repo.listar_conversas_do_lead(lead_id)) == 1


class TestAtualizarStatusConversa:

    def test_muda_o_status(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.ESCALADA)

        assert repo.buscar_conversa(criada.id).status is ConversationStatus.ESCALADA

    def test_status_encerrada_define_ended_at(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.ENCERRADA)

        assert repo.buscar_conversa(criada.id).ended_at is not None

    def test_status_escalada_tambem_define_ended_at(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.ESCALADA)

        assert repo.buscar_conversa(criada.id).ended_at is not None

    def test_status_nao_terminal_nao_define_ended_at(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))
        repo.atualizar_status_conversa(criada.id, ConversationStatus.AGUARDANDO_LEAD)

        assert repo.buscar_conversa(criada.id).ended_at is None


class TestRegistrarAtividade:

    def test_atualiza_last_activity_at(self, repo, lead_id):
        criada = repo.criar_conversa(Conversation(lead_id=lead_id))

        # Força um valor antigo para garantir que a chamada realmente
        # move o carimbo para frente, não só "não muda por acaso".
        with get_connection(repo._db_path) as conn:
            conn.execute(
                "UPDATE conversations SET last_activity_at = ? WHERE id = ?",
                ((datetime.now() - timedelta(hours=5)).isoformat(), criada.id),
            )

        repo.registrar_atividade(criada.id)

        atualizada = repo.buscar_conversa(criada.id)
        assert atualizada.last_activity_at > datetime.now() - timedelta(minutes=1)


# ============================================================
# MENSAGENS
# ============================================================


@pytest.fixture
def conversa_id(repo, lead_id) -> int:
    return repo.criar_conversa(Conversation(lead_id=lead_id)).id


class TestAdicionarMensagem:

    def test_atribui_id_e_created_at(self, repo, conversa_id):
        mensagem = repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="Oi")
        )
        assert mensagem.id is not None
        assert mensagem.created_at is not None

    def test_grava_todos_os_campos(self, repo, conversa_id):
        repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_id,
                role=MessageRole.AGENT,
                content="Como posso ajudar?",
                modelo_usado="llama-3.3-70b",
                latencia_ms=850,
            )
        )
        recuperada = repo.listar_mensagens(conversa_id)[0]

        assert recuperada.role is MessageRole.AGENT
        assert recuperada.content == "Como posso ajudar?"
        assert recuperada.modelo_usado == "llama-3.3-70b"
        assert recuperada.latencia_ms == 850

    def test_atualiza_last_activity_at_da_conversa(self, repo, conversa_id):
        with get_connection(repo._db_path) as conn:
            conn.execute(
                "UPDATE conversations SET last_activity_at = ? WHERE id = ?",
                ((datetime.now() - timedelta(hours=5)).isoformat(), conversa_id),
            )

        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="Oi")
        )

        conversa = repo.buscar_conversa(conversa_id)
        assert conversa.last_activity_at > datetime.now() - timedelta(minutes=1)


class TestListarMensagens:

    def test_ordem_cronologica(self, repo, conversa_id):
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="1")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.AGENT, content="2")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="3")
        )

        resultado = repo.listar_mensagens(conversa_id)

        assert [m.content for m in resultado] == ["1", "2", "3"]

    def test_com_limite_retorna_as_mais_recentes_ainda_em_ordem_cronologica(
        self, repo, conversa_id
    ):
        for texto in ["1", "2", "3", "4", "5"]:
            repo.adicionar_mensagem(
                Message(conversation_id=conversa_id, role=MessageRole.LEAD, content=texto)
            )

        resultado = repo.listar_mensagens(conversa_id, limite=2)

        assert [m.content for m in resultado] == ["4", "5"]

    def test_nao_mistura_conversas_diferentes(self, repo, lead_id):
        outra_conversa = repo.criar_conversa(Conversation(lead_id=lead_id))
        conversa_a = repo.criar_conversa(Conversation(lead_id=lead_id))

        repo.adicionar_mensagem(
            Message(conversation_id=conversa_a.id, role=MessageRole.LEAD, content="A")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=outra_conversa.id, role=MessageRole.LEAD, content="B")
        )

        assert len(repo.listar_mensagens(conversa_a.id)) == 1


class TestHistoricoParaLlm:

    def test_mapeia_lead_para_user_e_agent_para_assistant(self, repo, conversa_id):
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="Oi")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.AGENT, content="Olá!")
        )

        historico = repo.historico_para_llm(conversa_id)

        assert historico == [
            {"role": "user", "content": "Oi"},
            {"role": "assistant", "content": "Olá!"},
        ]

    def test_descarta_mensagens_de_sistema(self, repo, conversa_id):
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.SYSTEM, content="prompt")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="Oi")
        )

        historico = repo.historico_para_llm(conversa_id)

        assert len(historico) == 1
        assert historico[0]["role"] == "user"

    def test_respeita_o_limite(self, repo, conversa_id):
        for texto in ["1", "2", "3"]:
            repo.adicionar_mensagem(
                Message(conversation_id=conversa_id, role=MessageRole.LEAD, content=texto)
            )

        assert len(repo.historico_para_llm(conversa_id, limite=2)) == 2


class TestContarMensagens:

    def test_zero_sem_mensagens(self, repo, conversa_id):
        assert repo.contar_mensagens(conversa_id) == 0

    def test_reflete_quantidade(self, repo, conversa_id):
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.LEAD, content="Oi")
        )
        repo.adicionar_mensagem(
            Message(conversation_id=conversa_id, role=MessageRole.AGENT, content="Olá")
        )
        assert repo.contar_mensagens(conversa_id) == 2


# ============================================================
# EVENTOS
# ============================================================


class TestRegistrarEvento:

    def test_atribui_id_e_created_at(self, repo):
        evento = repo.registrar_evento(EventType.LEAD_CRIADO)
        assert evento.id is not None
        assert evento.created_at is not None

    def test_detalhes_arbitrarios_sobrevivem_ao_round_trip(self, repo, lead_id):
        repo.registrar_evento(
            EventType.INTENCAO_IDENTIFICADA,
            lead_id=lead_id,
            intent="compra",
            confianca=0.92,
        )

        recuperado = repo.listar_eventos(lead_id=lead_id)[0]

        assert recuperado.detalhes == {"intent": "compra", "confianca": 0.92}

    def test_lead_id_e_conversation_id_sao_opcionais(self, repo):
        evento = repo.registrar_evento(EventType.ERRO_LLM)
        assert evento.lead_id is None
        assert evento.conversation_id is None


class TestListarEventos:

    def test_filtra_por_lead_id(self, repo, db_path):
        lead_a = LeadRepository(db_path).criar(Lead()).id
        lead_b = LeadRepository(db_path).criar(Lead()).id
        repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_a)
        repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_b)

        resultado = repo.listar_eventos(lead_id=lead_a)

        assert len(resultado) == 1
        assert resultado[0].lead_id == lead_a

    def test_filtra_por_tipo(self, repo, lead_id):
        repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_id)
        repo.registrar_evento(EventType.LEAD_ESCALADO, lead_id=lead_id)

        resultado = repo.listar_eventos(tipo=EventType.LEAD_ESCALADO)

        assert len(resultado) == 1
        assert resultado[0].tipo is EventType.LEAD_ESCALADO

    def test_ordem_mais_recente_primeiro(self, repo, lead_id):
        primeiro = repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_id)
        segundo = repo.registrar_evento(EventType.LEAD_CLASSIFICADO, lead_id=lead_id)

        resultado = repo.listar_eventos(lead_id=lead_id)

        assert [e.id for e in resultado] == [segundo.id, primeiro.id]

    def test_respeita_o_limite(self, repo, lead_id):
        for _ in range(5):
            repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_id)

        assert len(repo.listar_eventos(lead_id=lead_id, limite=2)) == 2


class TestMetricasDeEventos:

    def test_sem_eventos_devolve_dicionario_vazio(self, repo):
        assert repo.metricas_de_eventos() == {}

    def test_conta_por_tipo(self, repo, lead_id):
        repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_id)
        repo.registrar_evento(EventType.LEAD_CRIADO, lead_id=lead_id)
        repo.registrar_evento(EventType.LEAD_ESCALADO, lead_id=lead_id)

        resultado = repo.metricas_de_eventos()

        assert resultado["lead_criado"] == 2
        assert resultado["lead_escalado"] == 1