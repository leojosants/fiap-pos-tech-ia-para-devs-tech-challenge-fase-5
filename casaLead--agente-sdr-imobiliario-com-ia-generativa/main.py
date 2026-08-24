"""CasaLead — Agente SDR Imobiliário com IA Generativa.

Ponto de entrada da aplicação Streamlit.
FIAP | Pós Tech em IA para Devs — Hackathon.
"""

import streamlit as st

from src.ui import page_chat

st.set_page_config(
    page_title="CasaLead — Agente SDR Imobiliário",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    page_chat.renderizar()


if __name__ == "__main__":
    main()