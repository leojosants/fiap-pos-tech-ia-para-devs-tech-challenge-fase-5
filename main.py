"""CasaLead — Agente SDR Imobiliário com IA Generativa.

Ponto de entrada da aplicação Streamlit.
FIAP | Pós Tech em IA para Devs — Hackathon.
"""

import streamlit as st

st.set_page_config(
    page_title="CasaLead — Agente SDR Imobiliário",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Renderiza a aplicação."""
    st.title("🏠 CasaLead")
    st.caption("Agente SDR Imobiliário com IA Generativa")

    st.success("Ambiente configurado com sucesso — Etapa 0 concluída.")

    st.markdown(
        """
        **Próximas etapas:**

        1. Base simulada de imóveis + camada de persistência
        2. Motor conversacional (Groq + modo demonstrativo)
        3. Identificação de intenção e qualificação
        4. Recomendação de imóveis (RAG)
        5. Classificação e priorização de leads
        6. Agendamento, follow-up e resumo para o corretor
        7. Dashboard e observabilidade
        8. Testes, documentação e deploy
        """
    )


if __name__ == "__main__":
    main()
