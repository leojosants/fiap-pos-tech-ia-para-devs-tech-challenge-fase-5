"""CasaLead — Agente SDR Imobiliário com IA Generativa.

Ponto de entrada da aplicação Streamlit.
FIAP | Pós Tech em IA para Devs — Hackathon.

Navegação multipágina nativa (st.navigation/st.Page, Streamlit >= 1.36):
Atendimento (chat), Dashboard e Corretor. As três páginas compartilham
o mesmo Orchestrator da sessão (src.ui.state), então dados criados numa
página (ex.: um lead qualificado no chat) aparecem imediatamente nas
outras, sem recarregar nada.
"""

import streamlit as st

from src.ui import page_broker, page_chat, page_dashboard, state

st.set_page_config(
    page_title="CasaLead — Agente SDR Imobiliário",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _pagina_chat() -> None:
    page_chat.renderizar()


def _pagina_dashboard() -> None:
    """Wrapper sem argumentos — st.Page exige isso.

    page_dashboard.renderizar() recebe o orquestrador por injeção
    (decisão documentada no próprio módulo); esta função só faz a
    ponte entre a navegação (que não passa argumento nenhum) e a
    página (que espera o orquestrador já pronto).
    """
    page_dashboard.renderizar(state.get_orquestrador())


def _pagina_corretor() -> None:
    page_broker.renderizar(state.get_orquestrador())


def main() -> None:
    paginas = st.navigation(
        [
            st.Page(_pagina_chat, title="Atendimento", icon="💬", default=True),
            st.Page(_pagina_dashboard, title="Dashboard", icon="📊"),
            st.Page(_pagina_corretor, title="Corretor", icon="🧑‍💼"),
        ]
    )
    paginas.run()


if __name__ == "__main__":
    main()