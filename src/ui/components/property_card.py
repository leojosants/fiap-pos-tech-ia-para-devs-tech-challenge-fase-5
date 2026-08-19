"""Card de exibição de imóvel recomendado.

Apresenta os dados estruturados do imóvel — código, preço, área,
quartos, vagas — em formato visual, complementando a menção textual
feita pelo agente na conversa.

A separação entre a fala do agente e o card é deliberada: a conversa
mantém a naturalidade do atendimento, enquanto o card entrega a
informação objetiva que não se absorve bem em prosa.
"""

import streamlit as st

from src.core.enums import PropertyType
from src.recommendation.ranker import Recomendacao, ResultadoRecomendacao

_ICONES_TIPO = {
    PropertyType.APARTAMENTO: "🏢",
    PropertyType.CASA: "🏡",
    PropertyType.STUDIO: "🏠",
    PropertyType.SALA_COMERCIAL: "🏬",
}


def _moeda(valor: float | None) -> str:
    """Formata um valor no padrão monetário brasileiro."""
    if valor is None:
        return "—"
    return f"R$ {valor:,.0f}".replace(",", ".")


def _renderizar_card(rec: Recomendacao, indice: int) -> None:
    """Desenha um único card de imóvel."""
    im = rec.imovel
    icone = _ICONES_TIPO.get(im.tipo, "🏠")

    with st.container(border=True):
        cabecalho, valor = st.columns([3, 2])

        with cabecalho:
            st.markdown(f"**{icone} {im.titulo}**")
            st.caption(f"`{im.codigo}` · {im.endereco_aproximado}")

        with valor:
            if im.preco_venda:
                st.markdown(f"### {_moeda(im.preco_venda)}")
                if im.preco_aluguel:
                    st.caption(f"ou {_moeda(im.preco_aluguel)}/mês de aluguel")
            elif im.preco_aluguel:
                st.markdown(f"### {_moeda(im.preco_aluguel)}/mês")
                if im.custo_mensal_total:
                    st.caption(f"{_moeda(im.custo_mensal_total)}/mês com encargos")

        # Atributos físicos
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Área", f"{im.area_util:.0f}m²")
        c2.metric("Quartos", im.quartos if im.quartos else "Studio")
        c3.metric("Vagas", im.vagas)
        c4.metric("Banheiros", im.banheiros)

        # Justificativa da recomendação
        if rec.motivos:
            for motivo in rec.motivos:
                if motivo.startswith("⚠️"):
                    st.caption(f":orange[{motivo}]")
                else:
                    st.caption(f"✓ {motivo}")

        # Características e detalhes adicionais
        with st.expander("Ver detalhes"):
            st.write(im.descricao)

            if im.caracteristicas:
                st.markdown(
                    "**Características:** "
                    + " · ".join(f"`{c}`" for c in im.caracteristicas)
                )

            detalhes = st.columns(3)
            detalhes[0].caption(f"Condomínio: {_moeda(im.condominio)}")
            detalhes[1].caption(f"IPTU: {_moeda(im.iptu)}/ano")
            detalhes[2].caption(f"Construção: {im.ano_construcao}")

            if im.preco_m2:
                st.caption(f"Preço por m²: {_moeda(im.preco_m2)}")

            if rec.termos_relevantes:
                st.caption(
                    "Correspondeu a: "
                    + ", ".join(f"*{t}*" for t in rec.termos_relevantes[:4])
                )


def _renderizar_card_investimento(rec: Recomendacao, indice: int) -> None:
    """Card orientado ao investidor.

    Destaca indicadores financeiros em vez de atributos de moradia:
    quem investe avalia retorno e liquidez, não quantidade de quartos.
    """
    im = rec.imovel

    with st.container(border=True):
        cabecalho, valor = st.columns([3, 2])

        with cabecalho:
            st.markdown(f"**📈 {im.titulo}**")
            st.caption(f"`{im.codigo}` · {im.bairro}")

        with valor:
            st.markdown(f"### {_moeda(im.preco_venda)}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Rentabilidade", f"{im.rentabilidade_estimada:.2f}%", "ao ano")
        c2.metric("Valorização", f"{im.potencial_valorizacao:.1f}%", "ao ano")
        c3.metric("Aluguel estimado", _moeda(im.preco_aluguel))

        st.caption(f"Perfil: **{im.perfil_investimento}** · {im.area_util:.0f}m²")

        if rec.motivos:
            for motivo in rec.motivos:
                st.caption(f"✓ {motivo}")

        with st.expander("Ver detalhes"):
            st.write(im.descricao)
            if im.preco_m2:
                st.caption(f"Preço por m²: {_moeda(im.preco_m2)}")
            st.caption(f"Condomínio: {_moeda(im.condominio)} · IPTU: {_moeda(im.iptu)}/ano")


def renderizar(
    resultado: ResultadoRecomendacao, *, modo_investimento: bool = False
) -> None:
    """Exibe o conjunto de imóveis recomendados.

    O cabeçalho é renderizado pela interface, e não gerado pelo agente:
    garante que o lead sempre entenda o que são os cards, mesmo quando o
    modelo não menciona a recomendação em sua resposta. Mesmo princípio
    aplicado à saudação — o que pode ser determinístico não depende do
    comportamento probabilístico do modelo.

    Sinaliza também quando os critérios do lead precisaram ser
    flexibilizados: apresentar opções aproximadas sem avisar
    comprometeria a confiança.
    """
    if not resultado.tem_resultados:
        return

    quantidade = len(resultado.recomendacoes)
    plural = "imóveis que combinam" if quantidade > 1 else "imóvel que combina"
    st.markdown(f"**🔍 {quantidade} {plural} com o que você procura**")

    criterios = resultado.criterios_usados
    if criterios.get("filtros_relaxados"):
        st.info(
            "Não encontrei imóveis com todos os critérios exatos. "
            "Estas são as opções mais próximas do que você procura."
        )
    elif criterios.get("preferencias_relaxadas"):
        st.info(
            "Ampliei um pouco a busca para mostrar mais opções — "
            "veja abaixo quais atendem suas preferências."
        )

    renderizador = (
        _renderizar_card_investimento if modo_investimento else _renderizar_card
    )

    for indice, rec in enumerate(resultado.recomendacoes):
        renderizador(rec, indice)

    if resultado.total_candidatos > len(resultado.recomendacoes):
        st.caption(
            f"Mostrando {len(resultado.recomendacoes)} de "
            f"{resultado.total_candidatos} imóveis compatíveis."
        )