"""Testes do motor de scoring (regras explícitas, Etapa 5).

Não depende de banco nem de chave de API — Lead e ContextoScoring
são construídos diretamente em memória.
"""

from src.core.enums import Intent, LeadTemperature, Urgency, Zone
from src.core.models import Lead
from src.scoring.context import ContextoScoring
from src.scoring.rules import calcular_score


def test_lead_sem_nenhum_dado_fica_frio_com_score_zero():
    lead = Lead()
    contexto = ContextoScoring()

    resultado = calcular_score(lead, contexto)

    assert resultado.score == 0
    assert resultado.temperature == LeadTemperature.FRIO


def test_lead_compra_totalmente_qualificado_fica_quente():
    lead = Lead(
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=500_000,
        quartos_desejados=2,
        urgencia=Urgency.IMEDIATA,
        disponibilidade_reuniao="sábado de manhã",
    )
    contexto = ContextoScoring(orcamento_viavel=True, turnos_substantivos=6)

    resultado = calcular_score(lead, contexto)

    assert resultado.score == 100
    assert resultado.temperature == LeadTemperature.QUENTE
    assert resultado.detalhamento["completude"] == 30
    assert resultado.detalhamento["urgencia"] == 20


def test_lead_investimento_usa_slots_de_investimento_na_completude():
    from src.core.enums import InvestmentGoal, InvestorProfile

    lead = Lead(
        intent=Intent.INVESTIMENTO,
        perfil_investidor=InvestorProfile.MODERADO,
        ticket_disponivel=300_000,
        objetivo_investimento=InvestmentGoal.RENDA,
        expectativa_retorno=6.5,
        prazo_investimento="6 meses",
    )
    contexto = ContextoScoring()

    resultado = calcular_score(lead, contexto)

    # Todos os 5 slots de investimento preenchidos = completude 100%
    assert resultado.detalhamento["completude"] == 30


def test_orcamento_inviavel_nao_pontua_mesmo_com_dados_declarados():
    lead = Lead(
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=100_000,  # abaixo de qualquer opção real na base
    )
    contexto = ContextoScoring(orcamento_viavel=False)

    resultado = calcular_score(lead, contexto)

    assert resultado.detalhamento["orcamento"] == 0


def test_engajamento_satura_em_cinco_turnos_substantivos():
    lead = Lead()
    contexto_parcial = ContextoScoring(turnos_substantivos=2)
    contexto_maximo = ContextoScoring(turnos_substantivos=10)

    resultado_parcial = calcular_score(lead, contexto_parcial)
    resultado_maximo = calcular_score(lead, contexto_maximo)

    assert resultado_parcial.detalhamento["engajamento"] == 4  # 2/5 × 10
    assert resultado_maximo.detalhamento["engajamento"] == 10  # saturado


def test_cortes_de_temperatura_moderado_e_alto():
    # completude(30) + urgencia curto_prazo(15) + disponibilidade(20)
    # + intencao(5) = 70 → limite inferior de QUENTE
    lead_no_corte = Lead(
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=500_000,
        quartos_desejados=2,
        urgencia=Urgency.CURTO_PRAZO,
        disponibilidade_reuniao="qualquer dia",
    )
    resultado = calcular_score(lead_no_corte, ContextoScoring())
    assert resultado.score == 70
    assert resultado.temperature == LeadTemperature.QUENTE

    # Reduzindo urgência para médio prazo, cai para 63 → MORNO
    lead_morno = Lead(
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=500_000,
        quartos_desejados=2,
        urgencia=Urgency.MEDIO_PRAZO,
        disponibilidade_reuniao="qualquer dia",
    )
    resultado_morno = calcular_score(lead_morno, ContextoScoring())
    assert resultado_morno.score == 63
    assert resultado_morno.temperature == LeadTemperature.MORNO