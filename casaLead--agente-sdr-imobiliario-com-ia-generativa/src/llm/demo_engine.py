"""Motor conversacional determinístico do CasaLead.

Conduz a qualificação sem depender de LLM, usando detecção por padrões
e um banco de perguntas por slot. É acionado automaticamente quando não
há chave de API disponível ou quando a chamada ao modelo falha.

Papel no sistema:
    1. Garantir que a aplicação permaneça funcional e demonstrável em
       qualquer circunstância (sem chave, sem rede, sem cota).
    2. Servir de linha de base para comparação: a diferença de qualidade
       entre este motor e o modo LLM evidencia o valor da IA generativa.

Limitação intencional: este motor não compreende linguagem natural.
Reconhece padrões conhecidos e ignora o resto. Não é, nem pretende ser,
substituto do LLM.
"""

import random
import re

from src.core.enums import Intent, Urgency, Zone
from src.core.models import Lead

# ============================================================
# DETECÇÃO POR PADRÕES
# ============================================================

_PADROES_INTENCAO = {
    Intent.INVESTIMENTO: (
        r"\binvest|\brenda\b|\brentabilidade\b|\brentab|\bretorno\b|"
        r"\bvaloriza|\bpatrim[oô]nio\b|\bcarteira\b|\bticket\b"
    ),
    Intent.ALUGUEL: r"\balug|\blocar\b|\bloca[çc][ãa]o\b|\bmorar de alug",
    Intent.COMPRA: r"\bcompr|\badquirir\b|\bfinanciar\b|\bfinanciamento\b|\bmeu pr[óo]prio\b",
}

_PADROES_ZONA = {
    Zone.SUL: r"zona sul|\bsul\b|moema|vila ol[íi]mpia|sa[úu]de|brooklin|itaim",
    Zone.OESTE: r"zona oeste|\boeste\b|pinheiros|butant[ãa]|perdizes|lapa",
    Zone.CENTRO: r"\bcentro\b|bela vista|santa cec[íi]lia|consola[çc][ãa]o|rep[úu]blica",
    Zone.NORTE: r"zona norte|\bnorte\b|santana|tucuruvi|casa verde|ja[çc]an[ãa]",
}

_BAIRROS_CONHECIDOS = {
    "moema": "Moema",
    "vila olímpia": "Vila Olímpia",
    "vila olimpia": "Vila Olímpia",
    "saúde": "Saúde",
    "saude": "Saúde",
    "pinheiros": "Pinheiros",
    "butantã": "Butantã",
    "butanta": "Butantã",
    "bela vista": "Bela Vista",
    "santa cecília": "Santa Cecília",
    "santa cecilia": "Santa Cecília",
    "santana": "Santana",
    "tucuruvi": "Tucuruvi",
}

_PADROES_URGENCIA = {
    "imediata": r"urgente|o quanto antes|imediat|com pressa|j[áa] preciso|este m[êe]s",
    "curto_prazo": r"pr[óo]ximos? (?:2|3|dois|tr[êe]s) meses|至|logo|em breve|at[ée] 3 meses",
    "medio_prazo": r"seis meses|6 meses|at[ée] um ano|1 ano|pr[óo]ximo ano",
    "sem_pressa": r"sem pressa|s[óo] pesquisando|s[óo] olhando|sem prazo|n[ãa]o tenho pressa",
}


_VERBOS_DECLARATIVOS = re.compile(
    r"(quer[oe]mos?|procur[oa]\w*|pens[oa]\w*|gostar[íi]amos?|gostaria|"
    r"pretend\w+|estamos?|estou|vou|vamos|preciso|precisamos)"
)


def detectar_intencao(texto: str) -> Intent:
    """Identifica a intenção do lead por correspondência de padrões.

    Ocorrências precedidas de verbo declarativo ("queremos comprar") têm
    precedência sobre menções contextuais ("contrato de aluguel vence"),
    pois indicam o que o lead deseja, não a situação em que se encontra.
    Sem declaração explícita, vence a última ocorrência no texto.
    """
    t = texto.lower()
    declaradas: list[tuple[int, Intent]] = []
    mencionadas: list[tuple[int, Intent]] = []

    for intent, padrao in _PADROES_INTENCAO.items():
        for m in re.finditer(padrao, t):
            contexto = t[max(0, m.start() - 25):m.start()]
            if _VERBOS_DECLARATIVOS.search(contexto):
                declaradas.append((m.start(), intent))
            else:
                mencionadas.append((m.start(), intent))

    if declaradas:
        return max(declaradas, key=lambda x: x[0])[1]
    if mencionadas:
        return max(mencionadas, key=lambda x: x[0])[1]
    return Intent.INDEFINIDA


def detectar_zona(texto: str) -> Zone | None:
    """Identifica a zona mencionada, incluindo por nome de bairro."""
    t = texto.lower()
    for zona, padrao in _PADROES_ZONA.items():
        if re.search(padrao, t):
            return zona
    return None


def detectar_bairros(texto: str) -> list[str]:
    """Extrai bairros conhecidos citados no texto."""
    t = texto.lower()
    encontrados = [nome for chave, nome in _BAIRROS_CONHECIDOS.items() if chave in t]
    return sorted(set(encontrados))


def detectar_valor(texto: str) -> float | None:
    """Extrai um valor monetário das formas usuais em português.

    Reconhece: 'R$ 850.000', '850 mil', '1,2 milhão', '850000'.
    """
    t = texto.lower().replace("r$", " ").strip()

    # "1,2 milhão" / "2 milhões"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:milh[õoã]?[oaeõ]?[se]?s?|mi\b)", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000

    # "850 mil" / "1.5 mil"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mil\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000

    # "850.000" / "850000" / "3.500"
    m = re.search(r"\b(\d{1,3}(?:\.\d{3})+|\d{4,})\b", t)
    if m:
        return float(m.group(1).replace(".", ""))

    return None


def detectar_quartos(texto: str) -> int | None:
    """Extrai a quantidade de quartos mencionada."""
    t = texto.lower()

    m = re.search(r"(\d+)\s*(?:quartos?|dorm|q\b)", t)
    if m:
        return int(m.group(1))

    escrito = {
        "um": 1, "uma": 1, "dois": 2, "duas": 2,
        "três": 3, "tres": 3, "quatro": 4, "cinco": 5,
    }
    for palavra, numero in escrito.items():
        if re.search(rf"\b{palavra}\s*(?:quartos?|dorm)", t):
            return numero

    return None


def detectar_urgencia(texto: str) -> str | None:
    """Identifica o prazo declarado pelo lead."""
    t = texto.lower()
    for valor, padrao in _PADROES_URGENCIA.items():
        if re.search(padrao, t):
            return valor
    return None

# Termos que indicam disponibilidade só quando acompanhados de contexto
# de agendamento. "Hoje moramos num studio" menciona tempo, mas não é
# disponibilidade; "posso hoje à tarde" é.
_PADRAO_DIA_HORARIO = (
    r"(segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo|"
    r"amanh[ãa]|hoje|fim de semana|manh[ãa]|tarde|noite|"
    r"\d{1,2}\s*h\b|\d{1,2}:\d{2})"
)

_CONTEXTO_DISPONIBILIDADE = (
    r"(posso|pode|podemos|dispon[íi]vel|disponibilidade|livre|"
    r"marcar|agendar|visitar|visita|conversar|reuni[ãa]o|"
    r"melhor (dia|hor[áa]rio)|que tal|prefiro|consigo|encaixa)"
)


def detectar_disponibilidade(texto: str) -> str:
    """Captura menção a dia ou horário de disponibilidade.

    Exige que o termo temporal apareça junto de um verbo ou expressão de
    agendamento na mesma frase. Sem isso, "hoje moramos num studio" seria
    interpretado como disponibilidade — a palavra é a mesma, o uso não.
    """
    for frase in re.split(r"[.!?\n]", texto):
        tem_tempo = re.search(_PADRAO_DIA_HORARIO, frase, re.IGNORECASE)
        tem_contexto = re.search(_CONTEXTO_DISPONIBILIDADE, frase, re.IGNORECASE)
        if tem_tempo and tem_contexto:
            trecho = frase.strip()
            if len(trecho) <= 120:
                return trecho
    return ""


_NAO_SAO_NOMES = {
    # Saudações e conectivos
    "oi", "ola", "olá", "bom", "boa", "eu", "sim", "nao", "não",
    "quero", "procuro", "preciso", "estou", "tenho", "gostaria",
    "meu", "minha", "obrigado", "obrigada", "certo", "ok", "legal",
    # Perfis de investidor — aparecem em "sou conservador"
    "conservador", "conservadora", "moderado", "moderada",
    "arrojado", "arrojada",
    # Papéis e estados — aparecem em "sou investidor", "sou casado"
    "investidor", "investidora", "corretor", "corretora",
    "interessado", "interessada", "comprador", "compradora",
    "casado", "casada", "solteiro", "solteira",
    "aposentado", "aposentada", "cliente", "pessoa", "alguem", "alguém",
}


def detectar_nome(texto: str) -> str:
    """Extrai o nome apenas em construções de apresentação explícita.

    Deliberadamente conservador: prefere não capturar nome nenhum a
    capturar uma saudação por engano. Chamar o lead de 'Oi' é pior do
    que não usar o nome dele.
    """
    padroes = [
        r"meu nome (?:é|e|eh)\s+([A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+)",
        r"(?:sou|me chamo)\s+(?:[oa]\s+)?([A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+)",
    ]
    for padrao in padroes:
        m = re.search(padrao, texto.strip(), re.IGNORECASE)
        if m:
            candidato = m.group(1)
            if candidato.lower() not in _NAO_SAO_NOMES and len(candidato) >= 3:
                return candidato.capitalize()
    return ""


# ============================================================
# RECONHECIMENTO — a parte (a) da mensagem
# ============================================================

_RECONHECIMENTOS = {
    "zona": ["Anotei: {valor}.", "Certo, {valor}.", "Perfeito, {valor}."],
    "valor": ["Anotei, até {valor}.", "Certo, {valor}.", "Ok, orçamento de {valor}."],
    "quartos": ["{valor} quartos, anotado.", "Certo, {valor} quartos."],
    "nome": ["Prazer, {valor}!", "Legal, {valor}."],
    "generico": ["Entendi.", "Certo.", "Anotado."],
}


def _formatar_moeda(valor: float) -> str:
    """Formata um valor monetário no padrão brasileiro."""
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f} milhão".replace(".0 ", " ")
    return f"R$ {valor:,.0f}".replace(",", ".")


def _montar_reconhecimento(capturados: dict, rng: random.Random) -> str:
    """Constrói a frase que ecoa o que foi entendido na última mensagem."""
    if not capturados:
        return rng.choice(_RECONHECIMENTOS["generico"])

    chave, valor = next(iter(capturados.items()))
    modelos = _RECONHECIMENTOS.get(chave, _RECONHECIMENTOS["generico"])
    return rng.choice(modelos).format(valor=valor)


# ============================================================
# PERGUNTAS POR SLOT — a parte (b) da mensagem
# ============================================================

_PERGUNTAS = {
    "zona_interesse": [
        "Em qual região da cidade você está procurando?",
        "Tem alguma região ou bairro em mente?",
    ],
    "preco_max": [
        "Qual valor você tem em mente para o imóvel?",
        "Até quanto você pretende investir na compra?",
    ],
    "quartos_desejados": [
        "De quantos quartos você precisa?",
        "Quantos quartos seriam ideais para você?",
    ],
    "urgencia": [
        "Para quando você pretende se mudar?",
        "Você tem algum prazo em mente?",
    ],
    "disponibilidade_reuniao": [
        "Qual seria o melhor dia e horário para você conversar com um corretor?",
        "Você teria disponibilidade para uma visita nesta semana?",
    ],
    "perfil_investidor": [
        "Você já investe em imóveis ou seria a primeira vez?",
        "Como você descreveria seu perfil de investidor?",
    ],
    "ticket_disponivel": [
        "Qual valor você pretende destinar a esse investimento?",
        "Quanto você tem disponível para investir?",
    ],
    "objetivo_investimento": [
        "Seu foco é renda mensal com aluguel ou valorização do imóvel?",
        "Qual é o objetivo principal desse investimento?",
    ],
    "expectativa_retorno": [
        "Que retorno anual você consideraria atrativo?",
        "Você tem alguma expectativa de rentabilidade?",
    ],
    "prazo_investimento": [
        "Em quanto tempo você pretende realizar esse investimento?",
        "Qual prazo você tem em mente?",
    ],
}

_PERGUNTA_INTENCAO = [
    "Você está procurando um imóvel para morar ou para investir?",
    "Me conta: a ideia é comprar, alugar ou investir?",
]

_ENCERRAMENTO = (
    "Perfeito, tenho tudo que preciso! Já deixei suas informações "
    "registradas com a nossa equipe. Obrigada!"
)


# ============================================================
# MOTOR
# ============================================================

class DemoEngine:
    """Conduz a qualificação sem LLM, por detecção de padrões.

    Aplica a mesma estrutura de duas partes do modo LLM — reconhecimento
    seguido de pergunta — porém com frases pré-definidas.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._tentativas_intencao = 0

    def aplicar_ao_lead(self, lead: Lead, texto: str) -> dict:
        """Extrai informações da mensagem e atualiza o lead.

        Retorna os itens capturados neste turno, usados para compor o
        reconhecimento e para registrar eventos de observabilidade.
        """
        capturados: dict[str, str] = {}

        if not lead.nome:
            nome = detectar_nome(texto)
            if nome:
                lead.nome = nome
                capturados["nome"] = nome

        if lead.intent == Intent.INDEFINIDA:
            intent = detectar_intencao(texto)
            if intent != Intent.INDEFINIDA:
                lead.intent = intent

        if lead.intent == Intent.INVESTIMENTO:
            if lead.ticket_disponivel is None:
                valor = detectar_valor(texto)
                if valor:
                    lead.ticket_disponivel = valor
                    capturados["valor"] = _formatar_moeda(valor)
        else:
            if lead.zona_interesse is None:
                zona = detectar_zona(texto)
                if zona:
                    lead.zona_interesse = zona
                    capturados["zona"] = f"zona {zona.value}"

            if not lead.bairros_interesse:
                bairros = detectar_bairros(texto)
                if bairros:
                    lead.bairros_interesse = bairros

            if lead.preco_max is None:
                valor = detectar_valor(texto)
                if valor:
                    lead.preco_max = valor
                    capturados["valor"] = _formatar_moeda(valor)

            if lead.quartos_desejados is None:
                quartos = detectar_quartos(texto)
                if quartos:
                    lead.quartos_desejados = quartos
                    capturados["quartos"] = str(quartos)

        if lead.urgencia == Urgency.NAO_INFORMADA:
            urgencia = detectar_urgencia(texto)
            if urgencia:
                lead.urgencia = Urgency(urgencia)

        if not lead.disponibilidade_reuniao:
            disponibilidade = detectar_disponibilidade(texto)
            if disponibilidade:
                lead.disponibilidade_reuniao = disponibilidade

        return capturados

    def responder(self, lead: Lead, texto: str) -> str:
        """Gera a próxima fala do agente.

        Segue a mesma estrutura do modo LLM: reconhece o que foi dito e
        faz uma única pergunta.
        """
        capturados = self.aplicar_ao_lead(lead, texto)
        reconhecimento = _montar_reconhecimento(capturados, self._rng)

        if lead.intent == Intent.INDEFINIDA:
            self._tentativas_intencao += 1

            # Saída de emergência: após duas perguntas sem resposta
            # explícita, assume compra a partir dos sinais já coletados.
            # Insistir seria pior que inferir — o lead já demonstrou o
            # que procura, ainda que sem usar o verbo esperado.
            if self._tentativas_intencao > 2 and self._tem_sinais_de_moradia(lead):
                lead.intent = Intent.COMPRA
            else:
                return f"{reconhecimento} {self._rng.choice(_PERGUNTA_INTENCAO)}"

        pendentes = [s for s, ok in lead.slots_status().items() if not ok]
        if not pendentes:
            return _ENCERRAMENTO

        pergunta = self._rng.choice(_PERGUNTAS[pendentes[0]])
        return f"{reconhecimento} {pergunta}"

    @staticmethod
    def _tem_sinais_de_moradia(lead: Lead) -> bool:
        """Indica se o lead já forneceu dados típicos de compra ou aluguel.

        Região, quantidade de quartos ou faixa de preço informados, sem
        menção a renda ou rentabilidade, caracterizam busca por moradia.
        """
        sinais = (
            lead.zona_interesse is not None,
            lead.quartos_desejados is not None,
            lead.preco_max is not None,
        )
        return sum(sinais) >= 2