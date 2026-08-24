"""Painel de qualificação exibido na barra lateral.

Torna visível o estado interno do agente: quais informações já foram
coletadas, quais faltam e por qual caminho a resposta foi produzida.

Além do valor para o usuário, cumpre um papel de demonstração: evidencia
que a qualificação é um processo estruturado e auditável, e não uma caixa
preta.
"""

import streamlit as st

from src.core.enums import Intent, LeadTemperature
from src.core.models import Lead

_ROTULOS = {
    "zona_interesse": "Região",
    "preco_max": "Orçamento",
    "quartos_desejados": "Quartos",
    "urgencia": "Prazo",
    "disponibilidade_reuniao": "Disponibilidade",
    "perfil_investidor": "Perfil investidor",
    "ticket_disponivel": "Ticket",
    "objetivo_investimento": "Objetivo",
    "expectativa_retorno": "Retorno esperado",
    "prazo_investimento": "Prazo",
}

_ROTULO_INTENCAO = {
    Intent.COMPRA: "Compra",
    Intent.ALUGUEL: "Aluguel",
    Intent.INVESTIMENTO: "Investimento",
    Intent.INDEFINIDA: "A identificar",
}

_CORES_TEMPERATURA = {
    LeadTemperature.QUENTE: "🔥",
    LeadTemperature.MORNO: "🟡",
    LeadTemperature.FRIO: "🔵",
}


def _formatar(valor: object, slot: str = "") -> str:
    """Apresenta o valor de um slot de forma legível na interface."""
    if slot == "expectativa_retorno" and isinstance(valor, (int, float)):
        return f"{valor:.1f}% ao ano"
    if isinstance(valor, float):
        return f"R$ {valor:,.0f}".replace(",", ".")
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)
    return str(valor).replace("_", " ").capitalize()


def renderizar(lead: Lead, ultimo_turno=None) -> None:
    """Desenha o painel de qualificação na barra lateral."""
    st.subheader("Qualificação")

    if lead.nome:
        st.caption(f"Lead: **{lead.nome}**")

    st.caption(f"Intenção: **{_ROTULO_INTENCAO[lead.intent]}**")

    completude = lead.completude()
    st.progress(completude, text=f"{round(completude * 100)}% concluído")

    st.divider()

    for slot, preenchido in lead.slots_status().items():
        rotulo = _ROTULOS.get(slot, slot)
        if preenchido:
            st.markdown(f"✅ **{rotulo}:** {_formatar(getattr(lead, slot), slot)}")
        else:
            st.markdown(f"⬜ {rotulo}")

    if lead.preferencias:
        st.divider()
        st.caption("Preferências mencionadas")
        st.markdown(" · ".join(f"`{p}`" for p in lead.preferencias))

    if completude >= 1.0 and lead.intent != Intent.INDEFINIDA:
        st.divider()
        st.success("Lead qualificado")
    elif completude >= 1.0:
        st.divider()
        st.warning("Aguardando definição da intenção")


def renderizar_diagnostico(diagnostico: dict, ultimo_turno=None) -> None:
    """Desenha o painel de observabilidade na barra lateral."""
    st.subheader("Sistema")

    modo = diagnostico.get("modo")
    if modo == "llm":
        st.caption(f"Modo: **IA generativa** · `{diagnostico['modelo_conversa']}`")
    else:
        st.caption("Modo: **demonstrativo** (motor determinístico)")

    uso = diagnostico.get("uso_llm", {})
    if uso.get("chamadas"):
        col1, col2 = st.columns(2)
        col1.metric("Chamadas", uso["chamadas"])
        col2.metric("Latência média", f"{uso['latencia_media_ms']}ms")

        if uso.get("falhas"):
            st.warning(f"{uso['falhas']} falha(s) — houve degradação para o modo demonstrativo.")

    if ultimo_turno is not None and ultimo_turno.divergencias:
        with st.expander("Divergências de extração"):
            for d in ultimo_turno.divergencias:
                st.caption(d)