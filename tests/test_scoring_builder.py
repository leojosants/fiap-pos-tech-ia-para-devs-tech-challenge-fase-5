"""Teste de integração do builder de scoring (Etapa 5).

Usa um banco SQLite temporário (tmp_path do pytest), isolado do banco
de desenvolvimento em data/runtime/. Cada teste recebe um arquivo novo.
"""

from pathlib import Path

import pytest

from src.core.enums import Intent, MessageRole, Zone
from src.core.models import Conversation, Lead, Message
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import bootstrap
from src.persistence.lead_repository import LeadRepository
from src.persistence.property_repository import PropertyRepository
from src.scoring.builder import construir_contexto


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    caminho = tmp_path / "teste_scoring.db"
    bootstrap(caminho)
    return caminho


def test_orcamento_viavel_true_quando_ha_imovel_na_zona_e_teto(db_path):
    imoveis = PropertyRepository(db_path)
    conversas = ConversationRepository(db_path)

    lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=10_000_000)

    # conversation_id=1 é seguro aqui: _turnos_substantivos só faz um
    # SELECT filtrado por conversation_id, sem exigir que a conversa
    # exista — não há INSERT nesse teste, então a FK não entra em jogo.
    contexto = construir_contexto(
        lead, conversation_id=1, imoveis=imoveis, conversas=conversas
    )

    assert contexto.orcamento_viavel is True


def test_turnos_substantivos_ignora_mensagens_curtas(db_path):
    leads = LeadRepository(db_path)
    conversas = ConversationRepository(db_path)

    # Lead real precisa existir antes da conversa, por causa da FK
    # conversations.lead_id -> leads.id (PRAGMA foreign_keys = ON).
    lead = leads.criar(Lead())
    conversa = conversas.criar_conversa(Conversation(lead_id=lead.id))

    conversas.adicionar_mensagem(
        Message(conversation_id=conversa.id, role=MessageRole.LEAD, content="Ok")
    )
    conversas.adicionar_mensagem(
        Message(
            conversation_id=conversa.id,
            role=MessageRole.LEAD,
            content="Procuro apartamento na zona sul",
        )
    )

    contexto = construir_contexto(
        lead, conversa.id, imoveis=PropertyRepository(db_path), conversas=conversas
    )

    assert contexto.turnos_substantivos == 1