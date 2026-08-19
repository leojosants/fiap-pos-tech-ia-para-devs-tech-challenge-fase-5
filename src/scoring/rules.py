"""Regras de pontuação e classificação de temperatura do lead.

Módulo puro: não acessa banco, não chama LLM, não depende de estado
externo além dos parâmetros recebidos. Recebe Lead + ContextoScoring
e devolve um resultado determinístico — o mesmo par de entradas
sempre produz a mesma saída.

Decisão de usar regras explícitas em vez de um classificador treinado
está registrada em docs/decisoes_tecnicas.md (seção Etapa 5): não há
dados reais de conversão disponíveis, e um modelo treinado em rótulos
sintéticos gerados pelas próprias regras não agregaria poder preditivo.
"""

from dataclasses import dataclass

from src.core.enums import Intent, LeadTemperature, Urgency
from src.core.models import Lead
from src.scoring.context import ContextoScoring

# --- Pesos máximos por sinal (somam 100) ---
PESO_COMPLETUDE = 30
PESO_URGENCIA = 20
PESO_DISPONIBILIDADE = 20
PESO_ORCAMENTO = 15
PESO_ENGAJAMENTO = 10
PESO_INTENCAO = 5

# --- Escala de urgência dentro do peso máximo (20 pontos) ---
_PONTOS_URGENCIA: dict[Urgency, int] = {
    Urgency.IMEDIATA: 20,
    Urgency.CURTO_PRAZO: 15,
    Urgency.MEDIO_PRAZO: 8,
    Urgency.SEM_PRESSA: 3,
    Urgency.NAO_INFORMADA: 0,
}

# --- Nº de turnos substantivos para engajamento máximo ---
_TURNOS_PARA_ENGAJAMENTO_MAXIMO = 5

# --- Cortes de temperatura ---
_CORTE_QUENTE = 70
_CORTE_MORNO = 40


@dataclass
class ResultadoScoring:
    """Resultado do cálculo, com o detalhamento por sinal.

    O detalhamento é o que permite ao corretor (e à banca) auditar
    por que um lead recebeu determinado score — não é uma caixa-preta.
    """

    score: int
    temperature: LeadTemperature
    detalhamento: dict[str, int]


def _pontos_completude(lead: Lead) -> int:
    """Sinal 1 — completude da qualificação (peso 30).

    Reusa Lead.completude(), já implementado no domínio, que calcula
    o percentual de slots preenchidos considerando o conjunto correto
    de campos por intenção (compra/aluguel vs. investimento).
    """
    return round(lead.completude() * PESO_COMPLETUDE)


def _pontos_urgencia(lead: Lead) -> int:
    """Sinal 2 — urgência declarada (peso 20, escala graduada)."""
    return _PONTOS_URGENCIA.get(lead.urgencia, 0)


def _pontos_disponibilidade(lead: Lead) -> int:
    """Sinal 3 — disponibilidade para reunião/visita (peso 20, binário).

    disponibilidade_reuniao é texto livre (extração híbrida regex+LLM),
    sem categoria estruturada no domínio. Simplificação consciente:
    pontuação cheia se o campo foi preenchido, zero se vazio — não
    diferencia grau de disponibilidade.
    """
    return PESO_DISPONIBILIDADE if lead.disponibilidade_reuniao.strip() else 0


def _pontos_orcamento(contexto: ContextoScoring) -> int:
    """Sinal 4 — orçamento/ticket coerente com o mercado (peso 15, binário).

    orcamento_viavel é calculado fora deste módulo (builder.py), que
    consulta a base real de imóveis. None (dado insuficiente) e False
    (declarado, mas inviável) pontuam igual — a distinção fica só no
    dado bruto, não na pontuação.
    """
    return PESO_ORCAMENTO if contexto.orcamento_viavel else 0


def _pontos_engajamento(contexto: ContextoScoring) -> int:
    """Sinal 5 — engajamento na conversa (peso 10, proporcional).

    Cresce linearmente até _TURNOS_PARA_ENGAJAMENTO_MAXIMO turnos
    substantivos, depois satura em PESO_ENGAJAMENTO.
    """
    proporcao = min(
        contexto.turnos_substantivos / _TURNOS_PARA_ENGAJAMENTO_MAXIMO, 1.0
    )
    return round(proporcao * PESO_ENGAJAMENTO)


def _pontos_intencao(lead: Lead) -> int:
    """Sinal 6 — intenção identificada (peso 5, binário).

    Simplificação: o domínio não registra se a intenção precisou de
    confirmação explícita (isso existiu só como fluxo de conversa na
    Etapa 3, não como dado persistido). Pontuamos apenas se a
    intenção já foi identificada (diferente de INDEFINIDA).
    """
    return PESO_INTENCAO if lead.intent != Intent.INDEFINIDA else 0


def _classificar_temperatura(score: int) -> LeadTemperature:
    """Converte o score numérico na faixa de temperatura correspondente."""
    if score >= _CORTE_QUENTE:
        return LeadTemperature.QUENTE
    if score >= _CORTE_MORNO:
        return LeadTemperature.MORNO
    return LeadTemperature.FRIO


def calcular_score(lead: Lead, contexto: ContextoScoring) -> ResultadoScoring:
    """Calcula o score (0-100) e a temperatura de um lead.

    Função pura e determinística: o mesmo par (lead, contexto) sempre
    produz o mesmo resultado. Não acessa banco, não chama LLM.

    Args:
        lead: estado atual do lead, com os slots já qualificados.
        contexto: dados externos (mercado, engajamento) já calculados
            por scoring.builder.construir_contexto().

    Returns:
        ResultadoScoring com o score total, a temperatura e o
        detalhamento por sinal.
    """
    detalhamento = {
        "completude": _pontos_completude(lead),
        "urgencia": _pontos_urgencia(lead),
        "disponibilidade": _pontos_disponibilidade(lead),
        "orcamento": _pontos_orcamento(contexto),
        "engajamento": _pontos_engajamento(contexto),
        "intencao": _pontos_intencao(lead),
    }
    score = sum(detalhamento.values())
    temperature = _classificar_temperatura(score)
    return ResultadoScoring(
        score=score, temperature=temperature, detalhamento=detalhamento
    )