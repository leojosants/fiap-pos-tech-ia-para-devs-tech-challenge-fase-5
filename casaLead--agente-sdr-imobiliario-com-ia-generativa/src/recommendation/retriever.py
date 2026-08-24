"""Busca semântica sobre a base de imóveis.

Complementa o filtro estruturado do PropertyRepository. Critérios como
zona, preço e quantidade de quartos são resolvidos em SQL; preferências
subjetivas — "arejado", "perto de um parque", "espaço para escritório" —
não têm coluna correspondente e exigem correspondência textual.

Estratégia: TF-IDF com similaridade de cosseno sobre a representação
textual de cada imóvel. A escolha por TF-IDF, em vez de embeddings
densos, considera três fatores: compatibilidade com o ambiente de deploy
(sem dependência de PyTorch), explicabilidade (é possível mostrar quais
termos casaram e com que peso) e adequação à escala da base.

Limitação conhecida: TF-IDF não reconhece sinônimos. Mitigado por um
dicionário de expansão de termos do domínio imobiliário.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.core.models import Property

logger = logging.getLogger(__name__)


# ============================================================
# NORMALIZAÇÃO E EXPANSÃO DE VOCABULÁRIO
# ============================================================

# Palavras sem poder discriminante em português. A lista é curta e
# específica: o TfidfVectorizer não traz stopwords em português, e uma
# lista genérica removeria termos úteis ao domínio.
_STOPWORDS_PT = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da",
    "dos", "das", "em", "no", "na", "nos", "nas", "por", "para", "pra",
    "com", "sem", "e", "ou", "que", "se", "ao", "aos", "à", "às", "é",
    "ser", "ter", "tem", "muito", "mais", "menos", "meu", "minha",
    "seu", "sua", "eu", "voce", "nos", "gostaria", "queria", "quero",
    "procuro", "preciso", "estou", "seria", "algo", "lugar", "imovel",
    "apartamento", "casa",
}

# Sinônimos e expressões equivalentes no domínio imobiliário. Cada termo
# à esquerda é substituído pelos termos à direita antes da indexação e
# da consulta, aproximando o vocabulário do lead do vocabulário da base.
_EXPANSAO_TERMOS = {
    "arejado": "arejado ensolarado ventilado vista livre andar alto",
    "ensolarado": "ensolarado arejado claro luminoso",
    "claro": "claro ensolarado luminoso",
    "espacoso": "espacoso amplo grande area",
    "amplo": "amplo espacoso grande",
    "parque": "parque area verde praca natureza",
    "verde": "verde parque area verde arborizado",
    "metro": "metro estacao transporte publico proximo metro",
    "transporte": "transporte metro onibus estacao",
    "pet": "pet cachorro gato animal pet friendly aceita pet",
    "cachorro": "cachorro pet animal pet friendly",
    "gato": "gato pet animal pet friendly",
    "escritorio": "escritorio home office coworking",
    "homeoffice": "home office escritorio coworking",
    "academia": "academia fitness ginastica",
    "piscina": "piscina lazer area comum",
    "lazer": "lazer piscina academia playground salao festas",
    "crianca": "crianca playground familia area verde",
    "familia": "familia playground crianca amplo",
    "seguranca": "seguranca portaria 24h segurança portaria",
    "portaria": "portaria seguranca 24h",
    "silencioso": "silencioso tranquilo sossegado",
    "tranquilo": "tranquilo silencioso sossegado",
    "novo": "novo reformado moderno",
    "reformado": "reformado novo moderno",
    "mobiliado": "mobiliado equipado armarios planejados",
    "vista": "vista livre panoramica andar alto",
    "garagem": "garagem vaga estacionamento",
    "vaga": "vaga garagem estacionamento",
    "churrasqueira": "churrasqueira area gourmet lazer",
    "investir": "investimento renda rentabilidade valorizacao",
    "renda": "renda aluguel rentabilidade investimento",
}


def normalizar(texto: str) -> str:
    """Reduz o texto a uma forma canônica para indexação e consulta.

    Remove acentuação, converte para minúsculas e descarta pontuação.
    A remoção de acentos é essencial: leads digitam "saude" e "butanta"
    tanto quanto "saúde" e "butantã".
    """
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def expandir(texto: str) -> str:
    """Acrescenta sinônimos do domínio aos termos reconhecidos.

    Aplicado tanto na indexação quanto na consulta: se o lead escreve
    "arejado" e a descrição diz "ensolarado", ambos passam a conter os
    dois termos, e a similaridade deixa de ser zero.
    """
    palavras = normalizar(texto).split()
    expandido = list(palavras)

    for palavra in palavras:
        if palavra in _EXPANSAO_TERMOS:
            expandido.extend(_EXPANSAO_TERMOS[palavra].split())

    return " ".join(expandido)


# ============================================================
# RESULTADO
# ============================================================

@dataclass
class ResultadoBusca:
    """Imóvel recuperado, com a evidência da correspondência."""

    imovel: Property
    score: float
    termos_relevantes: list[str]

    @property
    def percentual(self) -> int:
        """Score em escala percentual, para exibição."""
        return round(self.score * 100)


# ============================================================
# ÍNDICE
# ============================================================

class PropertyRetriever:
    """Índice TF-IDF sobre a base de imóveis."""

    def __init__(self, imoveis: list[Property]) -> None:
        self._imoveis = imoveis
        self._vectorizer: TfidfVectorizer | None = None
        self._matriz = None
        self._construir_indice()

    def _construir_indice(self) -> None:
        """Indexa a base.

        Usa n-gramas de 1 e 2 palavras: expressões como "area verde" e
        "andar alto" carregam significado que os termos isolados perdem.
        """
        if not self._imoveis:
            logger.warning("Base vazia — índice não construído.")
            return

        documentos = [expandir(im.texto_para_busca()) for im in self._imoveis]

        self._vectorizer = TfidfVectorizer(
            stop_words=list(_STOPWORDS_PT),
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,   # amortece a repetição excessiva de um termo
        )
        self._matriz = self._vectorizer.fit_transform(documentos)

        logger.info(
            "Índice construído: %d imóveis, %d termos.",
            len(self._imoveis),
            len(self._vectorizer.vocabulary_),
        )

    @property
    def disponivel(self) -> bool:
        return self._matriz is not None

    @property
    def tamanho_vocabulario(self) -> int:
        return len(self._vectorizer.vocabulary_) if self._vectorizer else 0

    # --------------------------------------------------------
    # Busca
    # --------------------------------------------------------

    def buscar(
        self,
        consulta: str,
        *,
        candidatos: list[Property] | None = None,
        limite: int = 5,
        score_minimo: float = 0.08,
    ) -> list[ResultadoBusca]:
        """Recupera imóveis semanticamente próximos da consulta.

        Quando candidatos é informado, a busca ocorre apenas sobre esse
        subconjunto — permitindo que o filtro estruturado (zona, preço,
        quartos) restrinja o espaço antes da avaliação semântica.
        """
        if not self.disponivel or not consulta.strip():
            return []

        vetor_consulta = self._vectorizer.transform([expandir(consulta)])
        similaridades = cosine_similarity(vetor_consulta, self._matriz)[0]

        ids_permitidos = (
            {im.id for im in candidatos} if candidatos is not None else None
        )

        resultados: list[ResultadoBusca] = []
        for indice, score in enumerate(similaridades):
            imovel = self._imoveis[indice]

            if ids_permitidos is not None and imovel.id not in ids_permitidos:
                continue
            if score < score_minimo:
                continue

            resultados.append(
                ResultadoBusca(
                    imovel=imovel,
                    score=float(score),
                    termos_relevantes=self._termos_em_comum(
                        vetor_consulta, indice
                    ),
                )
            )

        resultados.sort(key=lambda r: r.score, reverse=True)
        return resultados[:limite]

    def _termos_em_comum(self, vetor_consulta, indice_imovel: int) -> list[str]:
        """Identifica os termos que mais contribuíram para a similaridade.

        Torna a recomendação explicável: em vez de um score opaco, é
        possível mostrar por que aquele imóvel foi selecionado.
        """
        nomes = self._vectorizer.get_feature_names_out()
        pesos_consulta = vetor_consulta.toarray()[0]
        pesos_imovel = self._matriz[indice_imovel].toarray()[0]

        contribuicoes = [
            (nomes[i], pesos_consulta[i] * pesos_imovel[i])
            for i in range(len(nomes))
            if pesos_consulta[i] > 0 and pesos_imovel[i] > 0
        ]
        contribuicoes.sort(key=lambda x: x[1], reverse=True)

        return [termo for termo, _ in contribuicoes[:5]]

    def explicar(self, consulta: str) -> dict:
        """Diagnóstico da consulta — usado em testes e no painel técnico."""
        return {
            "consulta_original": consulta,
            "consulta_expandida": expandir(consulta),
            "vocabulario_indexado": self.tamanho_vocabulario,
            "imoveis_indexados": len(self._imoveis),
        }