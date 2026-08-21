"""Testes do orchestrator — _ultima_pergunta_agente(), usado para dar
contexto à extração por LLM (correção da resposta curta sem contexto).

Mesma técnica de test_orchestrator_scheduling.py: instância mínima via
__new__, evitando GroqClient/PropertyRanker/scoring reais — este método
só depende de self._conversas.
"""

import pytest

from src.agents.orchestrator import Orchestrator
from src.core.enums import MessageRole
from src.core.models import Conversation, Lead, Message
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema
from src.persistence.lead_repository import LeadRepository


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def conversas_repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


@pytest.fixture
def orchestrator_minimo(conversas_repo) -> Orchestrator:
    orch = Orchestrator.__new__(Orchestrator)
    orch._conversas = conversas_repo
    return orch


@pytest.fixture
def conversa_ativa(db_path, conversas_repo) -> int:
    lead = LeadRepository(db_path).criar(Lead(nome="Ana"))
    conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
    return conversa.id


class TestUltimaPerguntaAgente:

    def test_sem_nenhuma_mensagem_retorna_vazio(
        self, orchestrator_minimo, conversa_ativa
    ):
        assert orchestrator_minimo._ultima_pergunta_agente(conversa_ativa) == ""

    def test_so_mensagem_do_lead_sem_agente_retorna_vazio(
        self, orchestrator_minimo, conversas_repo, conversa_ativa
    ):
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.LEAD,
                content="oi",
            )
        )
        assert orchestrator_minimo._ultima_pergunta_agente(conversa_ativa) == ""

    def test_retorna_a_ultima_fala_do_agente(
        self, orchestrator_minimo, conversas_repo, conversa_ativa
    ):
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.AGENT,
                content="Oi! O que você procura?",
            )
        )
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.LEAD,
                content="apartamento na zona sul",
            )
        )
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.AGENT,
                content="Quantos quartos você precisa?",
            )
        )

        # a mensagem do lead que está prestes a ser qualificada ainda
        # não foi adicionada — mesmo ponto do fluxo real, chamado logo
        # após persistir a entrada
        ultima = orchestrator_minimo._ultima_pergunta_agente(conversa_ativa)
        assert ultima == "Quantos quartos você precisa?"

    def test_ignora_a_mensagem_do_lead_recem_persistida(
        self, orchestrator_minimo, conversas_repo, conversa_ativa
    ):
        """Simula o ponto exato do fluxo real: a mensagem do lead já foi
        persistida (passo [1]) antes de _ultima_pergunta_agente() rodar."""
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.AGENT,
                content="Quantos quartos você precisa?",
            )
        )
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.LEAD,
                content="2",
            )
        )

        ultima = orchestrator_minimo._ultima_pergunta_agente(conversa_ativa)
        assert ultima == "Quantos quartos você precisa?"

    def test_respeita_o_limite_de_mensagens_consultadas(
        self, orchestrator_minimo, conversas_repo, conversa_ativa
    ):
        """Só busca as últimas 5 mensagens — se a última fala do agente
        estiver mais distante que isso, retorna vazio em vez de uma
        pergunta desatualizada."""
        conversas_repo.adicionar_mensagem(
            Message(
                conversation_id=conversa_ativa, role=MessageRole.AGENT,
                content="Pergunta muito antiga",
            )
        )
        for i in range(6):
            conversas_repo.adicionar_mensagem(
                Message(
                    conversation_id=conversa_ativa, role=MessageRole.LEAD,
                    content=f"mensagem {i}",
                )
            )

        ultima = orchestrator_minimo._ultima_pergunta_agente(conversa_ativa)
        assert ultima == ""