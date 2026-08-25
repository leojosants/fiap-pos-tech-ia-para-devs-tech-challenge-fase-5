"""Testes do agente de qualificação (src/agents/qualification_agent.py).

Complementa `test_qualification_agent_contexto.py`, que cobre apenas o
parâmetro `ultima_pergunta_agente`. Este arquivo cobre o restante do
módulo — a suíte principal referida como pendente naquele arquivo.

Usa um GroqClient falso (mesmo padrão de `test_qualification_agent_contexto.py`:
`_settings.modo_demo` controlável e `extrair_json()` programável) — sem
rede, sem chave de API real.

Escopo:

1. `_extrair_por_padroes`: a etapa 1 (regex), com a regra específica
   deste agente de que a intenção aceita correção explícita mesmo já
   tendo um valor — diferente de `DemoEngine.aplicar_ao_lead`, que
   nunca sobrescreve intent já definida.
2. `_normalizar_llm`: a barreira de sanitização contra alucinação —
   valores fora dos conjuntos válidos, abaixo de pisos de
   plausibilidade, ou de campos já preenchidos são descartados.
3. `_consolidar`: a verificação cruzada — quando os dois métodos
   divergem em campo numérico, o valor dos padrões sempre prevalece
   (e a divergência fica registrada para auditoria), pela razão
   documentada no módulo: um erro de ordem de grandeza no orçamento
   compromete toda a recomendação.
4. `qualificar()`: a decisão de quando chamar o LLM (custo/latência) e
   a aplicação final ao objeto `Lead`.
5. `eventos_do_resultado()`: tradução para o log de observabilidade.
"""

from types import SimpleNamespace

from src.agents.qualification_agent import QualificationAgent, ResultadoQualificacao
from src.core.enums import (
    EventType,
    Intent,
    InvestmentGoal,
    InvestorProfile,
    LeadStatus,
    PropertyType,
    Urgency,
    Zone,
)
from src.core.models import Lead


class _ClienteFalso:
    """Substitui o GroqClient: registra o conteúdo recebido por
    extrair_json(), sem tocar rede. Mesmo padrão de
    test_qualification_agent_contexto.py."""

    def __init__(self, *, modo_demo: bool = False, dados_llm: dict | None = None):
        self._settings = SimpleNamespace(modo_demo=modo_demo)
        self._dados_llm = dados_llm if dados_llm is not None else {}
        self.conteudos_recebidos: list[str] = []
        self.chamadas = 0

    def extrair_json(self, prompt_sistema: str, conteudo: str):
        self.chamadas += 1
        self.conteudos_recebidos.append(conteudo)
        resposta = SimpleNamespace(
            conteudo=str(self._dados_llm), sucesso=True, erro="",
            latencia_ms=42, modelo="modelo-falso",
        )
        return (dict(self._dados_llm) if self._dados_llm else None), resposta


# ============================================================
# ETAPA 1 — extração por padrões
# ============================================================


class TestExtrairPorPadroes:

    def test_captura_nome_quando_lead_sem_nome(self):
        lead = Lead()
        capturado = QualificationAgent._extrair_por_padroes("meu nome é Marcos", lead)
        assert capturado["nome"] == "Marcos"

    def test_nao_sobrescreve_nome_ja_preenchido(self):
        lead = Lead(nome="Ana")
        capturado = QualificationAgent._extrair_por_padroes("meu nome é Marcos", lead)
        assert "nome" not in capturado

    def test_intent_aceita_correcao_mesmo_ja_tendo_um_valor(self):
        # Diferente de DemoEngine.aplicar_ao_lead: aqui a intenção pode
        # ser corrigida se o lead disser algo diferente do que já foi
        # identificado — "na verdade quero alugar" depois de "comprar".
        lead = Lead(intent=Intent.COMPRA)
        capturado = QualificationAgent._extrair_por_padroes(
            "na verdade quero alugar", lead
        )
        assert capturado["intent"] is Intent.ALUGUEL

    def test_intent_igual_a_atual_nao_e_capturada_de_novo(self):
        lead = Lead(intent=Intent.COMPRA)
        capturado = QualificationAgent._extrair_por_padroes(
            "quero comprar um apartamento", lead
        )
        assert "intent" not in capturado

    def test_fluxo_investimento_captura_ticket(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        capturado = QualificationAgent._extrair_por_padroes("tenho 500 mil", lead)
        assert capturado["ticket_disponivel"] == 500_000.0

    def test_fluxo_moradia_captura_preco_zona_bairro_quartos(self):
        lead = Lead(intent=Intent.COMPRA)
        capturado = QualificationAgent._extrair_por_padroes(
            "quero algo na zona sul, moema, até 800 mil, 3 quartos", lead
        )
        assert capturado["preco_max"] == 800_000.0
        assert capturado["zona_interesse"] is Zone.SUL
        assert capturado["bairros_interesse"] == ["Moema"]
        assert capturado["quartos_desejados"] == 3

    def test_urgencia_e_disponibilidade_capturadas(self):
        lead = Lead()
        capturado = QualificationAgent._extrair_por_padroes(
            "sem pressa, posso conversar amanhã de manhã", lead
        )
        assert capturado["urgencia"] is Urgency.SEM_PRESSA
        assert "amanhã de manhã" in capturado["disponibilidade_reuniao"]


# ============================================================
# ETAPA 2 — normalização do retorno do LLM
# ============================================================


class TestNormalizarLlmNome:

    def test_aceita_nome_valido(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm({"nome": "Marcos"}, lead)
        assert mapa["nome"] == "Marcos"

    def test_rejeita_nome_na_lista_de_exclusao(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm({"nome": "investidor"}, lead)
        assert "nome" not in mapa

    def test_rejeita_nome_curto_demais(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm({"nome": "Jo"}, lead)
        assert "nome" not in mapa

    def test_nao_sobrescreve_nome_ja_preenchido(self):
        lead = Lead(nome="Ana")
        mapa = QualificationAgent._normalizar_llm({"nome": "Marcos"}, lead)
        assert "nome" not in mapa


class TestNormalizarLlmIntent:

    def test_aceita_intent_quando_indefinida(self):
        lead = Lead(intent=Intent.INDEFINIDA)
        mapa = QualificationAgent._normalizar_llm({"intent": "compra"}, lead)
        assert mapa["intent"] is Intent.COMPRA

    def test_nao_sobrescreve_intent_ja_definida(self):
        # Diferente de _extrair_por_padroes: a normalização do LLM não
        # tem a regra de correção explícita — só preenche o vazio.
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"intent": "aluguel"}, lead)
        assert "intent" not in mapa

    def test_valor_invalido_e_descartado_silenciosamente(self):
        lead = Lead(intent=Intent.INDEFINIDA)
        mapa = QualificationAgent._normalizar_llm({"intent": "categoria_inexistente"}, lead)
        assert "intent" not in mapa


class TestNormalizarLlmInvestimento:

    def test_ticket_acima_do_piso_e_aceito(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        mapa = QualificationAgent._normalizar_llm({"ticket": 500_000}, lead)
        assert mapa["ticket_disponivel"] == 500_000.0

    def test_ticket_abaixo_do_piso_e_rejeitado(self):
        # Piso de R$ 10.000 — abaixo disso, mais provável ser erro de
        # extração do que um investimento real.
        lead = Lead(intent=Intent.INVESTIMENTO)
        mapa = QualificationAgent._normalizar_llm({"ticket": 5_000}, lead)
        assert "ticket_disponivel" not in mapa

    def test_perfil_investidor_aceito_quando_nao_informado(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        mapa = QualificationAgent._normalizar_llm(
            {"perfil_investidor": "moderado"}, lead
        )
        assert mapa["perfil_investidor"] is InvestorProfile.MODERADO

    def test_perfil_investidor_nao_sobrescreve_ja_informado(self):
        lead = Lead(intent=Intent.INVESTIMENTO, perfil_investidor=InvestorProfile.ARROJADO)
        mapa = QualificationAgent._normalizar_llm(
            {"perfil_investidor": "conservador"}, lead
        )
        assert "perfil_investidor" not in mapa

    def test_objetivo_investimento_aceito(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        mapa = QualificationAgent._normalizar_llm(
            {"objetivo_investimento": "renda"}, lead
        )
        assert mapa["objetivo_investimento"] is InvestmentGoal.RENDA

    def test_expectativa_retorno_e_prazo_investimento(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        mapa = QualificationAgent._normalizar_llm(
            {"expectativa_retorno": 7.5, "prazo_investimento": "6 meses"}, lead
        )
        assert mapa["expectativa_retorno"] == 7.5
        assert mapa["prazo_investimento"] == "6 meses"


class TestNormalizarLlmMoradia:

    def test_preco_max_acima_do_piso_e_aceito(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"preco_max": 500_000}, lead)
        assert mapa["preco_max"] == 500_000.0

    def test_preco_max_abaixo_do_piso_e_rejeitado(self):
        # Piso de R$ 500 — nenhum imóvel real custa menos que isso.
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"preco_max": 100}, lead)
        assert "preco_max" not in mapa

    def test_zona_invalida_e_descartada_silenciosamente(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"zona": "nordeste"}, lead)
        assert "zona_interesse" not in mapa

    def test_zona_valida_e_aceita(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"zona": "oeste"}, lead)
        assert mapa["zona_interesse"] is Zone.OESTE

    def test_bairros_e_convertido_para_lista_de_strings(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"bairros": ["Moema", "Itaim"]}, lead)
        assert mapa["bairros_interesse"] == ["Moema", "Itaim"]

    def test_tipo_imovel_aceito_quando_ainda_nao_definido(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"tipo_imovel": "studio"}, lead)
        assert mapa["tipo_imovel"] is PropertyType.STUDIO

    def test_quartos_e_vagas_desejadas(self):
        lead = Lead(intent=Intent.COMPRA)
        mapa = QualificationAgent._normalizar_llm({"quartos": 3, "vagas": 2}, lead)
        assert mapa["quartos_desejados"] == 3
        assert mapa["vagas_desejadas"] == 2


class TestNormalizarLlmPreferenciasUrgenciaDisponibilidade:

    def test_preferencias_normaliza_espacos_internos(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm(
            {"preferencias": ["  aceita   pet  ", "vaga extra"]}, lead
        )
        assert mapa["preferencias"] == ["aceita pet", "vaga extra"]

    def test_preferencias_vazias_nao_geram_chave(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm({"preferencias": []}, lead)
        assert "preferencias" not in mapa

    def test_urgencia_valida_e_aceita(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm({"urgencia": "imediata"}, lead)
        assert mapa["urgencia"] is Urgency.IMEDIATA

    def test_disponibilidade_aceita_quando_ainda_vazia(self):
        lead = Lead()
        mapa = QualificationAgent._normalizar_llm(
            {"disponibilidade": "sábado de manhã"}, lead
        )
        assert mapa["disponibilidade_reuniao"] == "sábado de manhã"


# ============================================================
# ETAPA 3 — consolidação com verificação cruzada
# ============================================================


class TestConsolidar:

    def test_campo_so_em_padroes_vai_para_o_consolidado(self):
        consolidado, divergencias = QualificationAgent._consolidar(
            {"zona_interesse": Zone.SUL}, {}
        )
        assert consolidado["zona_interesse"] is Zone.SUL
        assert divergencias == []

    def test_campo_so_no_llm_e_preservado(self):
        consolidado, divergencias = QualificationAgent._consolidar(
            {}, {"tipo_imovel": PropertyType.STUDIO}
        )
        assert consolidado["tipo_imovel"] is PropertyType.STUDIO
        assert divergencias == []

    def test_valores_numericos_proximos_nao_geram_divergencia(self):
        # 505.000 vs 500.000 — diferença de 1%, abaixo da tolerância de 5%.
        consolidado, divergencias = QualificationAgent._consolidar(
            {"preco_max": 505_000}, {"preco_max": 500_000}
        )
        assert divergencias == []
        assert consolidado["preco_max"] == 505_000  # padrões sempre prevalece

    def test_valores_numericos_distantes_geram_divergencia(self):
        # 850.000 vs 85.000 — exatamente o caso de erro de ordem de
        # grandeza citado no docstring do módulo.
        consolidado, divergencias = QualificationAgent._consolidar(
            {"preco_max": 850_000}, {"preco_max": 85_000}
        )
        assert len(divergencias) == 1
        assert "preco_max" in divergencias[0]
        assert consolidado["preco_max"] == 850_000  # padrões prevalece mesmo assim

    def test_campo_nao_numerico_nao_e_verificado_por_divergencia(self):
        # zona_interesse não está em campos_numericos — mesmo com
        # valores diferentes entre padrões e LLM, não gera divergência
        # registrada (mas o valor de padrões ainda prevalece).
        consolidado, divergencias = QualificationAgent._consolidar(
            {"zona_interesse": Zone.SUL}, {"zona_interesse": Zone.NORTE}
        )
        assert divergencias == []
        assert consolidado["zona_interesse"] is Zone.SUL

    def test_referencia_minima_evita_divisao_por_zero(self):
        # valor_padrao=0: referencia=max(0, 1.0)=1.0, evita ZeroDivisionError.
        consolidado, divergencias = QualificationAgent._consolidar(
            {"quartos_desejados": 0}, {"quartos_desejados": 5}
        )
        assert len(divergencias) == 1
        assert consolidado["quartos_desejados"] == 0


# ============================================================
# INTERFACE PÚBLICA — qualificar()
# ============================================================


class TestQualificar:

    def test_padroes_cobrem_tudo_nao_chama_llm(self):
        cliente = _ClienteFalso()
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(
            intent=Intent.COMPRA, urgencia=Urgency.IMEDIATA,
            disponibilidade_reuniao="sábado",
        )

        resultado = agente.qualificar(
            lead, "zona sul, até 800 mil, 3 quartos"
        )

        assert resultado.usou_llm is False
        assert cliente.chamadas == 0

    def test_modo_demo_nunca_chama_llm_mesmo_com_padroes_incompletos(self):
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(intent=Intent.COMPRA)  # nada preenchido, padrões não cobrem tudo

        agente.qualificar(lead, "olá")

        assert cliente.chamadas == 0

    def test_padroes_incompletos_e_sem_modo_demo_chama_llm(self):
        cliente = _ClienteFalso(dados_llm={"quartos": 2})
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(
            intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=500_000.0,
            urgencia=Urgency.IMEDIATA, disponibilidade_reuniao="sábado",
        )  # só falta quartos_desejados

        resultado = agente.qualificar(lead, "2")

        assert cliente.chamadas == 1
        assert resultado.usou_llm is True
        assert lead.quartos_desejados == 2

    def test_forcar_llm_chama_mesmo_com_padroes_completos(self):
        cliente = _ClienteFalso(dados_llm={})
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(
            intent=Intent.COMPRA, urgencia=Urgency.IMEDIATA,
            disponibilidade_reuniao="sábado",
        )

        agente.qualificar(
            lead, "zona sul, até 800 mil, 3 quartos", forcar_llm=True
        )

        assert cliente.chamadas == 1

    def test_resultado_sem_nenhuma_captura_houve_captura_false(self):
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=500_000.0)

        resultado = agente.qualificar(lead, "olá, tudo bem?")

        assert resultado.houve_captura is False

    def test_resultado_com_captura_houve_captura_true(self):
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)
        lead = Lead()

        resultado = agente.qualificar(lead, "quero comprar um apartamento")

        assert resultado.houve_captura is True
        assert resultado.intent_identificada is Intent.COMPRA

    def test_intent_identificada_e_aplicada_ao_lead(self):
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)
        lead = Lead()

        agente.qualificar(lead, "quero comprar um apartamento")

        assert lead.intent is Intent.COMPRA

    def test_slots_consolidados_sao_aplicados_ao_lead(self):
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)
        lead = Lead(intent=Intent.COMPRA)

        agente.qualificar(lead, "zona sul, até 800 mil")

        assert lead.zona_interesse is Zone.SUL
        assert lead.preco_max == 800_000.0


# ============================================================
# EVENTOS
# ============================================================


class TestEventosDoResultado:

    def test_sem_nenhuma_captura_lista_vazia(self):
        agente = QualificationAgent(cliente=_ClienteFalso())
        resultado = ResultadoQualificacao()

        assert agente.eventos_do_resultado(resultado, lead_id=1) == []

    def test_intent_identificada_gera_evento_com_via_padroes(self):
        agente = QualificationAgent(cliente=_ClienteFalso())
        resultado = ResultadoQualificacao(
            intent_identificada=Intent.COMPRA, usou_llm=False
        )

        eventos = agente.eventos_do_resultado(resultado, lead_id=1)

        tipos = [tipo for tipo, _ in eventos]
        assert EventType.INTENCAO_IDENTIFICADA in tipos
        detalhes = next(d for t, d in eventos if t is EventType.INTENCAO_IDENTIFICADA)
        assert detalhes["via"] == "padroes"

    def test_intent_identificada_via_llm_e_registrada(self):
        agente = QualificationAgent(cliente=_ClienteFalso())
        resultado = ResultadoQualificacao(
            intent_identificada=Intent.INVESTIMENTO, usou_llm=True
        )

        eventos = agente.eventos_do_resultado(resultado, lead_id=1)

        detalhes = next(d for t, d in eventos if t is EventType.INTENCAO_IDENTIFICADA)
        assert detalhes["via"] == "llm"

    def test_um_evento_slot_preenchido_por_slot_atualizado(self):
        agente = QualificationAgent(cliente=_ClienteFalso())
        resultado = ResultadoQualificacao(
            slots_atualizados={"zona_interesse": Zone.SUL, "preco_max": 500_000.0}
        )

        eventos = agente.eventos_do_resultado(resultado, lead_id=1)

        slot_events = [d for t, d in eventos if t is EventType.SLOT_PREENCHIDO]
        assert len(slot_events) == 2
        assert {e["slot"] for e in slot_events} == {"zona_interesse", "preco_max"}