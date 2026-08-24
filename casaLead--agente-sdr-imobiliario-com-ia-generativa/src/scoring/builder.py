"""Construção do contexto externo necessário para o scoring do lead.

Camada impura: é o único ponto do módulo scoring/ que acessa banco de
dados — consulta a base de imóveis (via PropertyRepository) e o
histórico de mensagens (via ConversationRepository) para montar o
ContextoScoring que scoring.rules.calcular_score() consome.

Mantém rules.py livre de qualquer dependência de infraestrutura,
permitindo testá-lo isoladamente (ver tests/test_scoring_rules.py).
"""

from pathlib import Path

from src.core.enums import Intent, MessageRole, Operation
from src.core.models import Lead
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.property_repository import PropertyRepository
from src.scoring.context import ContextoScoring

# Abaixo deste número de caracteres, uma mensagem do lead é considerada
# monossilábica ("ok", "sim") e não conta como turno substantivo.
_MIN_CARACTERES_TURNO_SUBSTANTIVO = 4


def _orcamento_viavel(lead: Lead, imoveis: PropertyRepository) -> bool | None:
    """Verifica se existe, na base real, alguma opção compatível com o lead.

    Investimento: compara ticket_disponivel com o menor preco_venda de
    toda a base (o cenário de investimento não filtra por zona hoje).

    Compra/aluguel: exige zona e preco_max informados; busca imóveis na
    zona, dentro do teto declarado, na coluna de preço correta conforme
    a operação (venda ou aluguel).

    Retorna None quando não há dado suficiente do lead para verificar
    — essa distinção (None vs False) fica só no dado bruto; a regra de
    pontuação em rules.py trata as duas situações da mesma forma.
    """
    if lead.intent == Intent.INVESTIMENTO:
        if lead.ticket_disponivel is None:
            return None
        preco_min_base = imoveis.estatisticas().get("preco_min")
        if preco_min_base is None:
            return None
        return lead.ticket_disponivel >= preco_min_base

    if lead.zona_interesse is None or lead.preco_max is None:
        return None

    operacao = (
        Operation.ALUGUEL if lead.intent == Intent.ALUGUEL else Operation.VENDA
    )
    encontrados = imoveis.buscar(
        zona=lead.zona_interesse,
        operacao=operacao,
        preco_max=lead.preco_max,
        limite=1,
    )
    return len(encontrados) > 0


def _turnos_substantivos(
    conversation_id: int, conversas: ConversationRepository
) -> int:
    """Conta mensagens do lead com conteúdo não trivial na conversa."""
    mensagens = conversas.listar_mensagens(conversation_id)
    return sum(
        1
        for m in mensagens
        if m.role == MessageRole.LEAD
        and len(m.content.strip()) >= _MIN_CARACTERES_TURNO_SUBSTANTIVO
    )


def construir_contexto(
    lead: Lead,
    conversation_id: int,
    *,
    imoveis: PropertyRepository,
    conversas: ConversationRepository,
) -> ContextoScoring:
    """Monta o ContextoScoring consultando a base de imóveis e o histórico.

    Recebe os repositórios já instanciados (reuso das instâncias que o
    orquestrador já mantém) em vez de criar novas conexões a cada turno.
    """
    return ContextoScoring(
        orcamento_viavel=_orcamento_viavel(lead, imoveis),
        turnos_substantivos=_turnos_substantivos(conversation_id, conversas),
    )