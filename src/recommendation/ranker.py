"""Ranqueamento de imóveis para recomendação ao lead.

Combina duas fases complementares:

    1. Filtro estruturado (SQL) — critérios não-negociáveis: zona, faixa
       de preço, quantidade de quartos. Define o universo de candidatos.
    2. Ordenação semântica (TF-IDF) — preferências subjetivas do lead
       sobre esse universo restrito.

A ordem importa: um imóvel semanticamente ideal mas fora do orçamento não
é uma recomendação, é um desperdício da atenção do lead. Por isso o filtro
objetivo vem primeiro.

O módulo também decide QUANDO recomendar: exibir imóveis cedo demais, com
critérios insuficientes, produz sugestões genéricas que reduzem a
credibilidade do agente.
"""

import logging
from dataclasses import dataclass, field

from src.core.enums import Intent, InvestmentGoal, Operation
from src.core.models import Lead, Property
from src.persistence.property_repository import PropertyRepository
from src.recommendation.retriever import PropertyRetriever, ResultadoBusca

logger = logging.getLogger(__name__)

# Mínimo de critérios estruturados para que a recomendação seja útil
_CRITERIOS_MINIMOS = 2

# Preferências que se traduzem em atributos estruturais, e não em
# correspondência textual. "Espaço para escritório" significa, na prática,
# um cômodo a mais — filtro, não busca semântica.
_PREFERENCIAS_ESTRUTURAIS = {
    "quarto_extra": (
        "escritorio", "escritório", "home office", "homeoffice",
        "trabalho em casa", "trabalhar em casa", "coworking",
    ),
    "pet": ("pet", "cachorro", "gato", "animal", "cão", "cao"),
    "vaga": ("vaga", "garagem", "carro", "estacionamento"),
    "mobiliado": ("mobiliado", "mobiliada", "equipado"),
}


@dataclass
class Recomendacao:
    """Imóvel recomendado, com a justificativa da seleção."""

    imovel: Property
    score_final: float
    score_semantico: float = 0.0
    termos_relevantes: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)

    @property
    def percentual(self) -> int:
        return round(self.score_final * 100)


@dataclass
class ResultadoRecomendacao:
    """Retorno completo de uma tentativa de recomendação."""

    recomendacoes: list[Recomendacao] = field(default_factory=list)
    total_candidatos: int = 0
    criterios_usados: dict = field(default_factory=dict)
    motivo_ausencia: str = ""

    @property
    def tem_resultados(self) -> bool:
        return bool(self.recomendacoes)


class PropertyRanker:
    """Seleciona e ordena imóveis adequados ao perfil do lead."""

    def __init__(
        self,
        repositorio: PropertyRepository | None = None,
        retriever: PropertyRetriever | None = None,
    ) -> None:
        self._repo = repositorio or PropertyRepository()
        self._retriever = retriever or PropertyRetriever(self._repo.listar_todos())

    # --------------------------------------------------------
    # Decisão: há critérios suficientes?
    # --------------------------------------------------------

    @staticmethod
    def pode_recomendar(lead: Lead) -> tuple[bool, str]:
        """Avalia se o lead forneceu critérios suficientes.

        Exige ao menos dois critérios estruturados. Com apenas um, a
        recomendação seria genérica demais — sugerir qualquer imóvel da
        zona sul, sem faixa de preço, não ajuda o lead nem demonstra
        competência do agente.
        """
        if lead.intent == Intent.INVESTIMENTO:
            if lead.ticket_disponivel is not None:
                return True, ""
            return False, "Aguardando o valor disponível para investimento."

        criterios = sum(
            (
                lead.zona_interesse is not None or bool(lead.bairros_interesse),
                lead.preco_max is not None,
                lead.quartos_desejados is not None,
            )
        )

        if criterios >= _CRITERIOS_MINIMOS:
            return True, ""
        return False, "Aguardando mais informações para sugerir imóveis."

    # --------------------------------------------------------
    # Tradução de preferências
    # --------------------------------------------------------

    @staticmethod
    def _preferencias_estruturais(lead: Lead) -> set[str]:
        """Identifica preferências que devem virar filtro, não busca.

        Percorre as preferências declaradas procurando termos que
        correspondam a atributos estruturados do imóvel.
        """
        texto = " ".join(lead.preferencias).lower()
        encontradas: set[str] = set()

        for chave, termos in _PREFERENCIAS_ESTRUTURAIS.items():
            if any(t in texto for t in termos):
                encontradas.add(chave)

        return encontradas

    @staticmethod
    def _consulta_semantica(lead: Lead) -> str:
        """Monta o texto de consulta a partir do que o lead expressou.

        Usa apenas as preferências subjetivas — os critérios estruturados
        já foram aplicados no filtro e não devem influenciar a ordenação
        semântica.
        """
        partes = list(lead.preferencias)

        if lead.bairros_interesse:
            partes.extend(lead.bairros_interesse)

        return " ".join(partes)

    # --------------------------------------------------------
    # Recomendação
    # --------------------------------------------------------

    def recomendar(
        self, lead: Lead, *, limite: int = 3
    ) -> ResultadoRecomendacao:
        """Seleciona os imóveis mais adequados ao perfil do lead."""
        pode, motivo = self.pode_recomendar(lead)
        if not pode:
            return ResultadoRecomendacao(motivo_ausencia=motivo)

        if lead.intent == Intent.INVESTIMENTO:
            return self._recomendar_investimento(lead, limite)

        return self._recomendar_moradia(lead, limite)

    # --------------------------------------------------------

    def _recomendar_moradia(
        self, lead: Lead, limite: int
    ) -> ResultadoRecomendacao:
        """Recomendação para compra ou aluguel."""
        estruturais = self._preferencias_estruturais(lead)

        # Um cômodo a mais quando o lead precisa de espaço de trabalho
        quartos_min = lead.quartos_desejados
        if quartos_min is not None and "quarto_extra" in estruturais:
            quartos_min += 1

        operacao = (
            Operation.ALUGUEL if lead.intent == Intent.ALUGUEL else Operation.VENDA
        )

        candidatos = self._repo.buscar(
            zona=lead.zona_interesse,
            bairros=lead.bairros_interesse or None,
            tipo=lead.tipo_imovel,
            operacao=operacao,
            preco_max=lead.preco_max,
            quartos_min=quartos_min,
            vagas_min=1 if "vaga" in estruturais else None,
            aceita_pet=True if "pet" in estruturais else None,
            mobiliado=True if "mobiliado" in estruturais else None,
            limite=40,
        )

        # Preferências são desejáveis, não obrigatórias. Se restringirem
        # demais o resultado, repetimos a busca sem elas — os motivos
        # exibidos ao lead indicam quais imóveis atendem cada preferência.
        if len(candidatos) < 3 and estruturais:
            candidatos_amplos = self._repo.buscar(
                zona=lead.zona_interesse,
                bairros=lead.bairros_interesse or None,
                tipo=lead.tipo_imovel,
                operacao=operacao,
                preco_max=lead.preco_max,
                quartos_min=lead.quartos_desejados,
                limite=40,
            )
            if len(candidatos_amplos) > len(candidatos):
                candidatos = candidatos_amplos
                criterios_preferencias_relaxadas = True
            else:
                criterios_preferencias_relaxadas = False
        else:
            criterios_preferencias_relaxadas = False

        criterios = {
            "zona": str(lead.zona_interesse) if lead.zona_interesse else None,
            "operacao": str(operacao),
            "preco_max": lead.preco_max,
            "quartos_min": quartos_min,
            "filtros_extras": sorted(estruturais),
            "preferencias_relaxadas": criterios_preferencias_relaxadas,
        }

        if not candidatos:
            candidatos = self._relaxar_filtros(lead, operacao, quartos_min)
            criterios["filtros_relaxados"] = True

        if not candidatos:
            return ResultadoRecomendacao(
                criterios_usados=criterios,
                motivo_ausencia=(
                    "Nenhum imóvel disponível com esses critérios no momento."
                ),
            )

        return self._ordenar(lead, candidatos, criterios, limite, estruturais)

    def _relaxar_filtros(
        self, lead: Lead, operacao: Operation, quartos_min: int | None
    ) -> list[Property]:
        """Repete a busca afrouxando critérios de forma progressiva.

        Aplica níveis crescentes de flexibilização até obter candidatos.
        A ordem reflete a hierarquia de negociabilidade: quartos cedem
        antes de preço, que cede antes da região. No último nível, a
        exigência de quartos é abandonada por completo — recomendar algo
        próximo é mais útil ao lead do que não recomendar nada, e os
        motivos exibidos sinalizam o que não foi atendido.
        """
        # (fator de preço, redução de quartos — None abandona o critério,
        #  manter a zona de interesse)
        niveis = [
            (1.15, 0, True),
            (1.15, 1, True),
            (1.40, 1, True),
            (1.40, 2, True),
            (1.40, 1, False),
            (1.60, None, False),
        ]

        for fator, reducao, manter_zona in niveis:
            if reducao is None or quartos_min is None:
                quartos_filtro = None
            else:
                quartos_filtro = max(1, quartos_min - reducao)

            candidatos = self._repo.buscar(
                zona=lead.zona_interesse if manter_zona else None,
                operacao=operacao,
                preco_max=lead.preco_max * fator if lead.preco_max else None,
                quartos_min=quartos_filtro,
                limite=40,
            )

            if candidatos:
                logger.info(
                    "Filtros relaxados: preço ×%.2f, quartos_min=%s, zona=%s",
                    fator,
                    quartos_filtro if quartos_filtro is not None else "livre",
                    "mantida" if manter_zona else "ampliada",
                )
                return candidatos

        return []
    # --------------------------------------------------------

    def _recomendar_investimento(
        self, lead: Lead, limite: int
    ) -> ResultadoRecomendacao:
        """Recomendação sob a ótica do investidor.

        Ordena por rentabilidade ou valorização conforme o objetivo
        declarado, e filtra por rentabilidade mínima quando o lead
        expressou uma expectativa de retorno.
        """
        ordenar_por = (
            "valorizacao"
            if lead.objetivo_investimento == InvestmentGoal.VALORIZACAO
            else "rentabilidade"
        )

        candidatos = self._repo.buscar_para_investimento(
            ticket_max=lead.ticket_disponivel,
            perfil=lead.perfil_investidor,
            rentabilidade_min=lead.expectativa_retorno,
            ordenar_por=ordenar_por,
            limite=limite,
        )

        criterios = {
            "ticket_max": lead.ticket_disponivel,
            "perfil": str(lead.perfil_investidor),
            "rentabilidade_min": lead.expectativa_retorno,
            "ordenado_por": ordenar_por,
        }

        if not candidatos:
            # A expectativa de retorno costuma ser o critério mais
            # restritivo; relaxá-la preserva a recomendação.
            candidatos = self._repo.buscar_para_investimento(
                ticket_max=lead.ticket_disponivel,
                ordenar_por=ordenar_por,
                limite=limite,
            )
            criterios["filtros_relaxados"] = True

        recomendacoes = [
            Recomendacao(
                imovel=im,
                score_final=1.0,
                motivos=self._motivos_investimento(im, lead),
            )
            for im in candidatos
        ]

        return ResultadoRecomendacao(
            recomendacoes=recomendacoes,
            total_candidatos=len(candidatos),
            criterios_usados=criterios,
        )

    # --------------------------------------------------------
    # Ordenação
    # --------------------------------------------------------

    def _ordenar(
        self,
        lead: Lead,
        candidatos: list[Property],
        criterios: dict,
        limite: int,
        estruturais: set[str],
    ) -> ResultadoRecomendacao:
        """Ordena os candidatos por aderência semântica ao pedido do lead.

        Sem preferências declaradas, mantém a ordem do filtro estruturado
        — não há sinal para reordenar.
        """
        consulta = self._consulta_semantica(lead)

        if not consulta.strip():
            recomendacoes = [
                Recomendacao(
                    imovel=im,
                    score_final=1.0,
                    motivos=self._motivos_estruturais(im, lead, estruturais),
                )
                for im in candidatos[:limite]
            ]
            return ResultadoRecomendacao(
                recomendacoes=recomendacoes,
                total_candidatos=len(candidatos),
                criterios_usados=criterios,
            )

        resultados: list[ResultadoBusca] = self._retriever.buscar(
            consulta, candidatos=candidatos, limite=limite
        )

        # Sem correspondência semântica suficiente, os candidatos do
        # filtro estruturado continuam válidos como recomendação.
        if not resultados:
            recomendacoes = [
                Recomendacao(
                    imovel=im,
                    score_final=0.5,
                    motivos=self._motivos_estruturais(im, lead, estruturais),
                )
                for im in candidatos[:limite]
            ]
            return ResultadoRecomendacao(
                recomendacoes=recomendacoes,
                total_candidatos=len(candidatos),
                criterios_usados=criterios,
            )

        recomendacoes = [
            Recomendacao(
                imovel=r.imovel,
                score_final=r.score,
                score_semantico=r.score,
                termos_relevantes=r.termos_relevantes,
                motivos=self._motivos_estruturais(r.imovel, lead, estruturais),
            )
            for r in resultados
        ]

        return ResultadoRecomendacao(
            recomendacoes=recomendacoes,
            total_candidatos=len(candidatos),
            criterios_usados=criterios,
        )

    # --------------------------------------------------------
    # Justificativas
    # --------------------------------------------------------

    @staticmethod
    def _motivos_estruturais(
        imovel: Property, lead: Lead, estruturais: set[str]
    ) -> list[str]:
        """Descreve, em linguagem natural, por que o imóvel foi selecionado."""
        motivos: list[str] = []

        if lead.zona_interesse and imovel.zona == lead.zona_interesse:
            motivos.append(f"Fica em {imovel.bairro}, na região que você procura")

        if lead.preco_max and imovel.preco_venda:
            folga = lead.preco_max - imovel.preco_venda
            if folga > lead.preco_max * 0.1:
                motivos.append("Está confortavelmente dentro do seu orçamento")
            elif folga >= 0:
                motivos.append("Cabe no seu orçamento")

        if lead.quartos_desejados and imovel.quartos > lead.quartos_desejados:
            diferenca = imovel.quartos - lead.quartos_desejados
            motivos.append(
                f"Tem {imovel.quartos} quartos — "
                f"{diferenca} a mais do que você pediu"
            )

        if lead.quartos_desejados and imovel.quartos < lead.quartos_desejados:
            palavra = "quarto" if imovel.quartos == 1 else "quartos"
            if imovel.quartos == 0:
                motivos.append("⚠️ É um studio, sem quarto separado")
            else:
                motivos.append(
                    f"⚠️ Tem {imovel.quartos} {palavra} — menos do que você pediu"
                )

        if "pet" in estruturais:
            if imovel.aceita_pet:
                motivos.append("Aceita animais de estimação")
            else:
                motivos.append("⚠️ Não aceita animais")

        if "vaga" in estruturais and imovel.vagas:
            motivos.append(f"Tem {imovel.vagas} vaga(s) de garagem")

        return motivos

    @staticmethod
    def _motivos_investimento(imovel: Property, lead: Lead) -> list[str]:
        """Justificativas sob a ótica do investidor."""
        motivos = [
            f"Rentabilidade estimada de {imovel.rentabilidade_estimada}% ao ano",
            f"Potencial de valorização de {imovel.potencial_valorizacao}% ao ano",
        ]

        if lead.expectativa_retorno and imovel.rentabilidade_estimada >= lead.expectativa_retorno:
            motivos.append("Atende à sua expectativa de retorno")

        if imovel.perfil_investimento == lead.perfil_investidor:
            motivos.append(f"Compatível com o perfil {imovel.perfil_investimento}")

        return motivos

    # --------------------------------------------------------
    # Formatação para o prompt
    # --------------------------------------------------------

    @staticmethod
    def formatar_para_prompt(resultado: ResultadoRecomendacao) -> str:
        """Descreve as recomendações para inclusão no prompt do agente.

        Formato compacto e factual: o agente deve mencionar estes imóveis
        sem inventar características ou alterar valores.
        """
        if not resultado.tem_resultados:
            return ""

        linhas = []
        for rec in resultado.recomendacoes:
            im = rec.imovel
            preco = (
                f"R$ {im.preco_venda:,.0f}".replace(",", ".")
                if im.preco_venda
                else f"R$ {im.preco_aluguel:,.0f}/mês".replace(",", ".")
            )
            linhas.append(
                f"- {im.codigo}: {im.titulo}, {im.area_util:.0f}m², "
                f"{im.quartos} quartos, {im.vagas} vaga(s), {preco}. "
                f"{', '.join(im.caracteristicas[:3])}."
            )

        return "\n".join(linhas)