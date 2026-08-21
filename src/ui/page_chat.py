"""Página de atendimento conversacional.

Interface pela qual o lead conversa com o agente. Delega todo o
processamento ao orquestrador — nenhuma regra de negócio reside aqui.
"""

import streamlit as st

from src.ui import state
from src.ui.components import qualification_panel
from src.core.enums import Intent
from src.ui.components import property_card, qualification_panel

_AVATAR_AGENTE = "🏠"
_AVATAR_LEAD = "👤"

_SUGESTOES = [
    "Estou procurando apartamento na zona sul",
    "Quero investir em imóveis para renda",
    "Preciso alugar algo perto do metrô",
]


def _escapar_cifrao(texto: str) -> str:
    """Escapa o caractere '$' antes de renderizar como markdown.

    Sem isso, duas ou mais ocorrências de '$' na mesma mensagem —
    comum quando a Sofia menciona um valor em R$ mais de uma vez —
    acionam a renderização de fórmula LaTeX do Streamlit, escondendo
    parte do texto entre elas. Mesmo bug já documentado e corrigido em
    property_card.py (ver _moeda_md, e o item 21 de
    docs/decisoes_tecnicas.md) — aqui aplicado à bolha de chat, que
    ainda não tinha recebido essa correção. Só afeta a renderização;
    o texto armazenado (histórico, banco) permanece o original.
    """
    return texto.replace("$", "\\$")


def _renderizar_sidebar(orquestrador) -> None:
    """Barra lateral com a qualificação e o diagnóstico do sistema."""
    with st.sidebar:
        if state.atendimento_iniciado():
            lead_id, _ = state.get_ids()
            lead = orquestrador._leads.buscar_por_id(lead_id)
            if lead:
                qualification_panel.renderizar(lead, state.get_ultimo_turno())

        st.divider()
        qualification_panel.renderizar_diagnostico(
            orquestrador.diagnostico(), state.get_ultimo_turno()
        )

        st.divider()
        if st.button("Novo atendimento", use_container_width=True):
            state.reiniciar_atendimento()
            st.rerun()


def _processar_entrada(orquestrador, texto: str) -> None:
    """Envia a mensagem ao orquestrador e registra a resposta."""
    lead_id, conversa_id = state.get_ids()

    state.adicionar_mensagem("user", texto)

    with st.chat_message("assistant", avatar=_AVATAR_AGENTE):
        with st.spinner("Sofia está digitando..."):
            resultado = orquestrador.processar_mensagem(
                lead_id, conversa_id, texto
            )
        st.markdown(_escapar_cifrao(resultado.resposta))

        if resultado.recomendacao and resultado.recomendacao.tem_resultados:
            property_card.renderizar(
                resultado.recomendacao,
                modo_investimento=resultado.lead.intent == Intent.INVESTIMENTO,
            )

    state.adicionar_mensagem("assistant", resultado.resposta)
    state.set_ultimo_turno(resultado)


def renderizar() -> None:
    """Desenha a página de atendimento."""
    orquestrador = state.get_orquestrador()

    if not state.atendimento_iniciado():
        state.iniciar_atendimento()

    _renderizar_sidebar(orquestrador)

    st.title("🏠 CasaLead")
    st.caption("Atendimento inteligente · Agente SDR Imobiliário")

    for mensagem in state.get_mensagens():
        avatar = _AVATAR_AGENTE if mensagem["role"] == "assistant" else _AVATAR_LEAD
        with st.chat_message(mensagem["role"], avatar=avatar):
            st.markdown(_escapar_cifrao(mensagem["content"]))

    # Os cards da última recomendação permanecem visíveis abaixo do
    # histórico. Redesenhá-los em cada turno passado exigiria armazenar
    # o estado de todos os turnos; manter apenas o mais recente é
    # suficiente, pois os critérios evoluem e recomendações antigas
    # perderiam validade.
    ultimo = state.get_ultimo_turno()
    if ultimo and ultimo.recomendacao and ultimo.recomendacao.tem_resultados:
        property_card.renderizar(
            ultimo.recomendacao,
            modo_investimento=ultimo.lead.intent == Intent.INVESTIMENTO,
        )

    if len(state.get_mensagens()) == 1:
        st.caption("Sugestões para começar:")
        colunas = st.columns(len(_SUGESTOES))
        for coluna, sugestao in zip(colunas, _SUGESTOES):
            if coluna.button(sugestao, use_container_width=True):
                _processar_entrada(orquestrador, sugestao)
                st.rerun()

    entrada = st.chat_input("Escreva sua mensagem...")
    if entrada:
        _processar_entrada(orquestrador, entrada)
        st.rerun()