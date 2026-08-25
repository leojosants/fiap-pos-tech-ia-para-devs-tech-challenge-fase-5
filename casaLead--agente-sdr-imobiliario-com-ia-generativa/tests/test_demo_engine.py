"""Testes do motor conversacional determinístico (src/llm/demo_engine.py).

Módulo 100% puro (regex + estado em memória) — sem banco, sem chave de
API, sem chamada de rede. Escopo:

1. **Detectores por padrão** (`detectar_intencao`, `detectar_zona`,
   `detectar_bairros`, `detectar_valor`, `detectar_quartos`,
   `detectar_urgencia`, `detectar_disponibilidade`, `detectar_nome`):
   cada um testado isoladamente, incluindo os casos de não-detecção
   documentados no próprio código como decisões deliberadas (ex.:
   `detectar_nome` prefere não capturar nada a capturar uma saudação
   por engano).
2. **`detectar_bairros` — teste de regressão**: cobre o bug de
   digitação corrigido nesta mesma etapa (`docs/decisoes_tecnicas.md`)
   — a chave `"vila olímpica"` (com C, errada) foi substituída por
   `"vila olímpia"` (grafia correta do bairro). Sem este teste, uma
   reversão futura do fix passaria despercebida.
3. **Funções auxiliares de formatação** (`_formatar_moeda`,
   `_montar_reconhecimento`): moeda no padrão brasileiro e a montagem
   da frase de reconhecimento a partir do que foi capturado no turno.
4. **`DemoEngine`**: `aplicar_ao_lead()` — captura condicionada ao
   estado atual do lead (não sobrescreve o que já foi preenchido, e
   alterna entre o fluxo de moradia e o de investimento conforme a
   intenção) — e `responder()` — a máquina de estados completa:
   pergunta de intenção, a saída de emergência após três tentativas
   sem resposta explícita, a pergunta do próximo slot pendente, e o
   encerramento quando não há mais nada a perguntar. Os cenários de
   `responder()` usam `DemoEngine(seed=1)` para determinismo — a saída
   exata foi conferida rodando o motor antes de escrever a asserção,
   não adivinhada.
"""

from src.core.enums import Intent, Urgency, Zone
from src.core.models import Lead
from src.llm.demo_engine import (
    DemoEngine,
    _ENCERRAMENTO,
    _formatar_moeda,
    _montar_reconhecimento,
    _PERGUNTA_INTENCAO,
    _PERGUNTAS,
    detectar_bairros,
    detectar_disponibilidade,
    detectar_intencao,
    detectar_nome,
    detectar_quartos,
    detectar_urgencia,
    detectar_valor,
    detectar_zona,
)


# ============================================================
# DETECTORES
# ============================================================


class TestDetectarIntencao:

    def test_compra_por_verbo_declarativo(self):
        assert detectar_intencao("quero comprar um apartamento") is Intent.COMPRA

    def test_aluguel_por_verbo_declarativo(self):
        assert detectar_intencao("quero alugar um apartamento") is Intent.ALUGUEL

    def test_investimento_por_verbo_declarativo(self):
        assert detectar_intencao("quero investir em imóveis") is Intent.INVESTIMENTO

    def test_financiamento_conta_como_compra(self):
        assert detectar_intencao("quero financiar um apartamento") is Intent.COMPRA

    def test_renda_conta_como_investimento(self):
        assert detectar_intencao("quero renda extra com imóveis") is Intent.INVESTIMENTO

    def test_sem_nenhum_padrao_e_indefinida(self):
        assert detectar_intencao("Gostaria de saber mais sobre a região") is Intent.INDEFINIDA

    def test_declarada_tem_precedencia_sobre_mencionada(self):
        # "aluguel" aparece antes, mas só como menção contextual
        # ("moro de aluguel"); "comprar" é precedido por "quero" —
        # verbo declarativo — e vence mesmo vindo depois no texto.
        texto = "moro de aluguel mas quero comprar um imóvel próprio"
        assert detectar_intencao(texto) is Intent.COMPRA

    def test_sem_declaracao_vence_a_ultima_mencao(self):
        # Nenhuma das duas menções tem verbo declarativo por perto —
        # a que aparece por último no texto decide.
        texto = "o aluguel está caro e o mercado de investimento está bom"
        assert detectar_intencao(texto) is Intent.INVESTIMENTO


class TestDetectarZona:

    def test_por_nome_da_zona(self):
        assert detectar_zona("moro na zona sul") is Zone.SUL

    def test_por_nome_de_bairro(self):
        assert detectar_zona("quero algo em pinheiros") is Zone.OESTE

    def test_zona_centro(self):
        assert detectar_zona("gosto do centro da cidade") is Zone.CENTRO

    def test_zona_norte(self):
        assert detectar_zona("prefiro zona norte") is Zone.NORTE

    def test_sem_mencao_retorna_none(self):
        assert detectar_zona("não sei ainda") is None


class TestDetectarBairros:

    def test_reconhece_multiplos_bairros(self):
        assert detectar_bairros("moema e pinheiros") == ["Moema", "Pinheiros"]

    def test_deduplica_variantes_com_e_sem_acento(self):
        assert detectar_bairros("saude e saúde") == ["Saúde"]

    def test_sem_bairro_conhecido_retorna_vazio(self):
        assert detectar_bairros("não conheço nada por aqui") == []

    def test_regressao_vila_olimpia_grafia_correta(self):
        # Bug corrigido nesta etapa: a chave do dicionário tinha um "c"
        # a mais ("vila olímpica"), então a grafia correta do bairro
        # nunca era reconhecida. Ver docs/decisoes_tecnicas.md.
        assert detectar_bairros("Estou de olho em Vila Olímpia") == ["Vila Olímpia"]

    def test_vila_olimpia_sem_acento_tambem_e_reconhecida(self):
        assert detectar_bairros("Estou de olho em Vila Olimpia") == ["Vila Olímpia"]


class TestDetectarValor:

    def test_valor_com_cifrao_e_separador_de_milhar(self):
        assert detectar_valor("R$ 850.000") == 850_000.0

    def test_valor_em_mil(self):
        assert detectar_valor("850 mil") == 850_000.0

    def test_valor_em_milhao_com_decimal(self):
        assert detectar_valor("1,2 milhão") == 1_200_000.0

    def test_valor_em_milhoes_plural(self):
        assert detectar_valor("2 milhões") == 2_000_000.0

    def test_numero_puro_de_quatro_digitos_ou_mais(self):
        assert detectar_valor("tenho 850000 disponível") == 850_000.0

    def test_numero_pequeno_nao_e_interpretado_como_valor(self):
        # "3" sozinho não tem dígitos suficientes nem separador de
        # milhar — não deve ser confundido com valor monetário.
        assert detectar_valor("tenho 3 quartos") is None

    def test_sem_nenhum_numero_retorna_none(self):
        assert detectar_valor("sem número nenhum aqui") is None


class TestDetectarQuartos:

    def test_numero_digito_seguido_de_quartos(self):
        assert detectar_quartos("preciso de 3 quartos") == 3

    def test_numero_digito_seguido_de_dormitorios(self):
        assert detectar_quartos("quero 2 dormitórios") == 2

    def test_abreviacao_q(self):
        assert detectar_quartos("3q") == 3

    def test_numero_por_extenso(self):
        assert detectar_quartos("quero dois quartos") == 2

    def test_numero_por_extenso_acentuado(self):
        assert detectar_quartos("três dormitórios") == 3

    def test_sem_mencao_retorna_none(self):
        assert detectar_quartos("sem menção a cômodos") is None


class TestDetectarUrgencia:

    def test_imediata(self):
        assert detectar_urgencia("preciso urgente") == "imediata"

    def test_curto_prazo(self):
        assert detectar_urgencia("nos próximos 2 meses") == "curto_prazo"

    def test_medio_prazo(self):
        assert detectar_urgencia("em até um ano") == "medio_prazo"

    def test_sem_pressa(self):
        assert detectar_urgencia("sem pressa, só olhando") == "sem_pressa"

    def test_sem_mencao_retorna_none(self):
        assert detectar_urgencia("nada específico por enquanto") is None


class TestDetectarDisponibilidade:

    def test_dia_e_contexto_na_mesma_frase(self):
        resultado = detectar_disponibilidade("Posso conversar amanhã de manhã")
        assert resultado == "Posso conversar amanhã de manhã"

    def test_tempo_sem_contexto_de_agendamento_e_ignorado(self):
        # "hoje" aparece, mas sem verbo/expressão de agendamento por
        # perto — não é disponibilidade, é só uma frase com a palavra
        # "hoje". Caso documentado no docstring da função.
        assert detectar_disponibilidade("hoje moramos num studio") == ""

    def test_pega_a_frase_certa_entre_varias(self):
        texto = "Bom dia. Posso amanhã de manhã, seria ótimo"
        resultado = detectar_disponibilidade(texto)
        assert "amanhã de manhã" in resultado
        assert "Bom dia" not in resultado

    def test_frase_muito_longa_e_descartada(self):
        frase_longa = (
            "Posso conversar " + "sobre isso e aquilo e outras coisas " * 4 + "amanhã de manhã"
        )
        assert len(frase_longa) > 120
        assert detectar_disponibilidade(frase_longa) == ""


class TestDetectarNome:

    def test_meu_nome_e(self):
        assert detectar_nome("meu nome é Marcos") == "Marcos"

    def test_sou(self):
        assert detectar_nome("sou o Carlos") == "Carlos"

    def test_me_chamo(self):
        assert detectar_nome("me chamo Ana") == "Ana"

    def test_capitaliza_entrada_em_minusculas(self):
        assert detectar_nome("meu nome é marcos") == "Marcos"

    def test_nao_captura_perfil_de_investidor(self):
        # "sou investidor" não deve virar o nome "Investidor" — está
        # na lista de exclusão _NAO_SAO_NOMES.
        assert detectar_nome("sou investidor") == ""

    def test_sem_construcao_de_apresentacao_retorna_vazio(self):
        assert detectar_nome("oi tudo bem") == ""


# ============================================================
# FORMATAÇÃO
# ============================================================


class TestFormatarMoeda:

    def test_abaixo_de_um_milhao_usa_separador_de_milhar(self):
        assert _formatar_moeda(850_000) == "R$ 850.000"

    def test_milhao_com_casa_decimal_significativa(self):
        assert _formatar_moeda(1_500_000) == "R$ 1.5 milhão"

    def test_milhao_redondo_omite_a_casa_decimal(self):
        assert _formatar_moeda(2_000_000) == "R$ 2 milhão"


class TestMontarReconhecimento:

    def test_sem_capturados_usa_frase_generica(self, ):
        import random
        rng = random.Random(42)
        assert _montar_reconhecimento({}, rng) in [
            "Entendi.", "Certo.", "Anotado.",
        ]

    def test_chave_conhecida_usa_o_modelo_certo(self):
        import random
        rng = random.Random(1)
        resultado = _montar_reconhecimento({"zona": "zona sul"}, rng)
        assert "zona sul" in resultado

    def test_chave_desconhecida_cai_no_generico(self):
        import random
        rng = random.Random(1)
        resultado = _montar_reconhecimento({"chave_inexistente": "valor"}, rng)
        assert resultado in ["Entendi.", "Certo.", "Anotado."]


# ============================================================
# DEMO ENGINE — aplicar_ao_lead
# ============================================================


class TestAplicarAoLeadNome:

    def test_captura_nome_quando_lead_ainda_nao_tem(self):
        lead = Lead()
        capturados = DemoEngine().aplicar_ao_lead(lead, "meu nome é Marcos")
        assert lead.nome == "Marcos"
        assert capturados["nome"] == "Marcos"

    def test_nao_sobrescreve_nome_ja_preenchido(self):
        lead = Lead(nome="Ana")
        capturados = DemoEngine().aplicar_ao_lead(lead, "meu nome é Marcos")
        assert lead.nome == "Ana"
        assert "nome" not in capturados


class TestAplicarAoLeadIntent:

    def test_captura_intent_quando_indefinida(self):
        lead = Lead()
        DemoEngine().aplicar_ao_lead(lead, "quero comprar um apartamento")
        assert lead.intent is Intent.COMPRA

    def test_nao_sobrescreve_intent_ja_definida(self):
        lead = Lead(intent=Intent.ALUGUEL)
        DemoEngine().aplicar_ao_lead(lead, "quero comprar um apartamento")
        assert lead.intent is Intent.ALUGUEL


class TestAplicarAoLeadFluxoInvestimento:

    def test_captura_ticket_disponivel(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        capturados = DemoEngine().aplicar_ao_lead(lead, "tenho 500 mil disponíveis")
        assert lead.ticket_disponivel == 500_000.0
        assert capturados["valor"] == "R$ 500.000"

    def test_nao_captura_campos_do_fluxo_de_moradia(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        DemoEngine().aplicar_ao_lead(
            lead, "tenho 500 mil na zona sul, preciso de 3 quartos"
        )
        assert lead.zona_interesse is None
        assert lead.preco_max is None
        assert lead.quartos_desejados is None


class TestAplicarAoLeadFluxoMoradia:

    def test_captura_zona_bairro_preco_e_quartos(self):
        lead = Lead(intent=Intent.COMPRA)
        DemoEngine().aplicar_ao_lead(
            lead, "quero algo na zona sul, moema, até 800 mil, 3 quartos"
        )
        assert lead.zona_interesse is Zone.SUL
        assert lead.bairros_interesse == ["Moema"]
        assert lead.preco_max == 800_000.0
        assert lead.quartos_desejados == 3

    def test_nao_sobrescreve_preco_ja_preenchido(self):
        lead = Lead(intent=Intent.COMPRA, preco_max=500_000.0)
        DemoEngine().aplicar_ao_lead(lead, "na verdade tenho até 900 mil")
        assert lead.preco_max == 500_000.0


class TestAplicarAoLeadUrgenciaEDisponibilidade:

    def test_captura_urgencia_quando_nao_informada(self):
        lead = Lead()
        DemoEngine().aplicar_ao_lead(lead, "sem pressa, só olhando")
        assert lead.urgencia is Urgency.SEM_PRESSA

    def test_nao_sobrescreve_urgencia_ja_definida(self):
        lead = Lead(urgencia=Urgency.IMEDIATA)
        DemoEngine().aplicar_ao_lead(lead, "sem pressa, só olhando")
        assert lead.urgencia is Urgency.IMEDIATA

    def test_nao_sobrescreve_disponibilidade_ja_capturada(self):
        lead = Lead(disponibilidade_reuniao="sábado de manhã")
        DemoEngine().aplicar_ao_lead(lead, "posso amanhã à tarde")
        assert lead.disponibilidade_reuniao == "sábado de manhã"


# ============================================================
# DEMO ENGINE — responder (determinístico via seed)
# ============================================================


class TestResponderPerguntaDeIntencao:

    def test_lead_indefinido_recebe_pergunta_de_intencao(self):
        engine = DemoEngine(seed=1)
        lead = Lead()
        resposta = engine.responder(lead, "olá, quero saber mais")

        assert lead.intent is Intent.INDEFINIDA
        assert resposta == (
            "Entendi. Você está procurando um imóvel para morar ou para investir?"
        )
        assert resposta.split(". ", 1)[1] in _PERGUNTA_INTENCAO


class TestResponderSaidaDeEmergencia:

    def test_apos_tres_tentativas_com_sinais_de_moradia_infere_compra(self):
        # zona + quartos já preenchidos = 2 sinais de moradia — na
        # terceira tentativa sem intenção explícita, o motor assume
        # Intent.COMPRA em vez de insistir pela quarta vez.
        engine = DemoEngine(seed=1)
        lead = Lead(zona_interesse=Zone.SUL, quartos_desejados=2)

        r1 = engine.responder(lead, "oi")
        assert lead.intent is Intent.INDEFINIDA  # ainda indefinida após r1
        r2 = engine.responder(lead, "oi")
        assert lead.intent is Intent.INDEFINIDA  # ainda indefinida após r2

        assert r1.split(". ", 1)[1] in _PERGUNTA_INTENCAO
        assert r2.split(". ", 1)[1] in _PERGUNTA_INTENCAO

    def test_na_terceira_tentativa_intent_vira_compra_e_pergunta_muda(self):
        engine = DemoEngine(seed=1)
        lead = Lead(zona_interesse=Zone.SUL, quartos_desejados=2)
        engine.responder(lead, "oi")
        engine.responder(lead, "oi")
        r3 = engine.responder(lead, "oi")

        assert lead.intent is Intent.COMPRA
        assert r3.split(". ", 1)[1] in _PERGUNTAS["preco_max"]

    def test_menos_de_dois_sinais_nao_dispara_a_inferencia(self):
        # Só um sinal de moradia (zona) — mesmo após três tentativas,
        # o motor não deve inferir a intenção, pois exige ao menos 2.
        engine = DemoEngine(seed=1)
        lead = Lead(zona_interesse=Zone.SUL)

        engine.responder(lead, "oi")
        engine.responder(lead, "oi")
        engine.responder(lead, "oi")

        assert lead.intent is Intent.INDEFINIDA


class TestResponderPerguntaDeSlotPendente:

    def test_pergunta_o_primeiro_slot_pendente_na_ordem_da_tupla(self):
        # zona_interesse já preenchida — o primeiro pendente na ordem
        # de SLOTS_COMPRA é preco_max, não quartos_desejados.
        engine = DemoEngine(seed=1)
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL)

        resposta = engine.responder(lead, "ok")

        assert any(p in resposta for p in _PERGUNTAS["preco_max"])

    def test_reconhecimento_precede_a_pergunta(self):
        engine = DemoEngine(seed=1)
        lead = Lead(intent=Intent.COMPRA)

        resposta = engine.responder(lead, "quero algo na zona sul")

        assert resposta == "Anotei: zona sul. Qual valor você tem em mente para o imóvel?"


class TestResponderEncerramento:

    def test_todos_os_slots_preenchidos_retorna_encerramento(self):
        engine = DemoEngine(seed=1)
        lead = Lead(
            intent=Intent.COMPRA,
            zona_interesse=Zone.SUL,
            preco_max=500_000.0,
            quartos_desejados=2,
            urgencia=Urgency.IMEDIATA,
            disponibilidade_reuniao="sábado de manhã",
        )

        assert engine.responder(lead, "ok") == _ENCERRAMENTO