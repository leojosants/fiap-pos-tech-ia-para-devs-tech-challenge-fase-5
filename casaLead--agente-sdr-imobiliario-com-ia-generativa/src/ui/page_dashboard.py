"""Página de dashboard — funil de leads e observabilidade (Etapa 7).

Painel de acompanhamento agregado: funil de leads por status,
temperatura e intenção; eventos do sistema; agenda e follow-ups; uso do
LLM. Não processa nenhuma lógica de negócio — só consulta
src.observability.metrics (que por sua vez só lê os repositórios já
existentes) e desenha.

Ainda não está ligada à navegação em main.py — isso é um passo
posterior do plano da Etapa 7. Este módulo é standalone e testável
isoladamente até lá.
"""

# pandas não está listado em pyproject.toml como dependência direta do
# projeto porque já é dependência obrigatória do streamlit (não
# opcional — o streamlit não funciona sem ele, é usado internamente
# por praticamente todo componente de dado/gráfico). Importamos aqui
# só o que o streamlit já garante que existe, sem adicionar peso novo
# ao ambiente.
import pandas as pd
import streamlit as st

from src.core.enums import (
    AppointmentStatus,
    EventType,
    FollowupStatus,
    Intent,
    LeadStatus,
    LeadTemperature,
)
from src.observability import metrics

_ROTULO_STATUS = {
    LeadStatus.NOVO: "Novo",
    LeadStatus.EM_QUALIFICACAO: "Em qualificação",
    LeadStatus.QUALIFICADO: "Qualificado",
    LeadStatus.AGENDADO: "Agendado",
    LeadStatus.ENCAMINHADO: "Encaminhado",
    LeadStatus.INATIVO: "Inativo",
    LeadStatus.PERDIDO: "Perdido",
}

_ROTULO_TEMPERATURA = {
    LeadTemperature.QUENTE: "🔥 Quente",
    LeadTemperature.MORNO: "🟡 Morno",
    LeadTemperature.FRIO: "🔵 Frio",
}

_ROTULO_INTENCAO = {
    Intent.COMPRA: "Compra",
    Intent.ALUGUEL: "Aluguel",
    Intent.INVESTIMENTO: "Investimento",
    Intent.INDEFINIDA: "Indefinida",
}

_ROTULO_EVENTOS = {
    EventType.LEAD_CRIADO: "Lead criado",
    EventType.CONVERSA_INICIADA: "Conversa iniciada",
    EventType.MENSAGEM_RECEBIDA: "Mensagem recebida",
    EventType.MENSAGEM_ENVIADA: "Mensagem enviada",
    EventType.INTENCAO_IDENTIFICADA: "Intenção identificada",
    EventType.SLOT_PREENCHIDO: "Slot preenchido",
    EventType.IMOVEIS_RECOMENDADOS: "Imóveis recomendados",
    EventType.LEAD_CLASSIFICADO: "Lead classificado",
    EventType.AGENDAMENTO_CRIADO: "Agendamento criado",
    EventType.FOLLOWUP_ENVIADO: "Follow-up enviado",
    EventType.RESUMO_GERADO: "Resumo gerado",
    EventType.LEAD_ESCALADO: "Lead escalado",
    EventType.ERRO_LLM: "Erro de LLM",
}

_ROTULO_AGENDAMENTO = {
    AppointmentStatus.AGENDADO: "Agendado",
    AppointmentStatus.CONFIRMADO: "Confirmado",
    AppointmentStatus.REALIZADO: "Realizado",
    AppointmentStatus.CANCELADO: "Cancelado",
}

_ROTULO_FOLLOWUP = {
    FollowupStatus.PENDENTE: "Pendente",
    FollowupStatus.ENVIADO: "Enviado",
    FollowupStatus.RESPONDIDO: "Respondido",
    FollowupStatus.SEM_RESPOSTA: "Sem resposta",
}


def _serie(contagens: dict[str, int], rotulos: dict) -> pd.Series:
    """Converte uma contagem por valor de enum numa Series legível.

    As chaves de `contagens` vêm como string simples (resultado de
    str(enum) em metrics.py e nos repositórios). Como o projeto usa
    StrEnum em todo o domínio, um StrEnum é igual e tem o mesmo hash
    que sua string equivalente — por isso `rotulos.get(chave, ...)`
    funciona mesmo com `rotulos` indexado pelos membros do enum, sem
    conversão explícita.

    Se uma chave não tiver rótulo mapeado (dado inesperado no banco),
    cai no valor bruto em vez de quebrar a página — melhor mostrar um
    rótulo feio do que derrubar o dashboard.

    Função pura, sem nenhuma chamada a st.* — testável isoladamente.
    """
    dados = {rotulos.get(chave, chave): valor for chave, valor in contagens.items()}
    return pd.Series(dados, name="quantidade")


def _renderizar_funil(funil: dict) -> None:
    st.subheader("Funil de leads")

    col1, col2, col3 = st.columns(3)
    col1.metric("Leads com interação", funil["total"])
    col2.metric("Score médio", funil["score_medio"])
    col3.metric("Ocultos (sem interação)", funil["leads_vazios_ocultos"])

    if funil["total"] == 0:
        st.info("Nenhum lead com interação registrada ainda.")
        return

    col_status, col_temp = st.columns(2)
    with col_status:
        st.caption("Por status")
        st.bar_chart(_serie(funil["por_status"], _ROTULO_STATUS))
    with col_temp:
        st.caption("Por temperatura")
        st.bar_chart(_serie(funil["por_temperatura"], _ROTULO_TEMPERATURA))

    st.caption("Por intenção")
    st.bar_chart(_serie(funil["por_intencao"], _ROTULO_INTENCAO))


def _renderizar_eventos(eventos: dict) -> None:
    st.subheader("Eventos do sistema")

    if not eventos:
        st.info("Nenhum evento registrado ainda.")
        return

    st.bar_chart(_serie(eventos, _ROTULO_EVENTOS))


def _renderizar_agenda_e_followups(agendamentos: dict, followups: dict) -> None:
    st.subheader("Agenda e follow-up")

    col1, col2 = st.columns(2)

    with col1:
        st.caption(f"Agendamentos — total: {agendamentos['total']}")
        if agendamentos["por_status"]:
            st.bar_chart(_serie(agendamentos["por_status"], _ROTULO_AGENDAMENTO))
        else:
            st.caption("Nenhum agendamento ainda.")

    with col2:
        st.caption(f"Follow-ups — total: {followups['total']}")
        if followups["por_status"]:
            st.bar_chart(_serie(followups["por_status"], _ROTULO_FOLLOWUP))
        else:
            st.caption("Nenhum follow-up ainda.")


def _renderizar_uso_llm(uso: dict) -> None:
    st.subheader("Uso do modelo de linguagem")
    st.caption(
        "Contagem da sessão atual do servidor — não é um histórico "
        "persistido; reinicia quando o processo Streamlit reinicia."
    )

    if not uso.get("chamadas"):
        st.caption("Nenhuma chamada ao LLM nesta sessão (modo demonstrativo, "
                   "ou ainda sem uso).")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Chamadas", uso["chamadas"])
    col2.metric("Taxa de sucesso", f"{uso['taxa_sucesso']}%")
    col3.metric("Latência média", f"{uso['latencia_media_ms']}ms")
    col4.metric("Tokens (entrada+saída)", uso["tokens_entrada"] + uso["tokens_saida"])

    if uso["falhas"]:
        st.warning(f"{uso['falhas']} falha(s) registrada(s) nesta sessão.")


def renderizar(orquestrador) -> None:
    """Desenha a página de dashboard.

    Recebe o orquestrador (não o instancia) — mesmo princípio de
    page_chat.py: a página não conhece repositório nenhum diretamente,
    só o objeto que já foi montado por src.ui.state.
    """
    st.title("📊 Dashboard — CasaLead")
    st.caption("Funil de leads, eventos e uso do sistema")

    incluir_vazios = st.checkbox(
        "Incluir leads sem interação "
        "(criados ao abrir a conversa, sem nenhuma mensagem)",
        value=False,
    )

    dados = metrics.coletar(
        leads_repo=orquestrador.leads,
        conversas_repo=orquestrador.conversas,
        agendamentos_repo=orquestrador.agendamentos,
        followups_repo=orquestrador.followups,
        cliente=orquestrador.cliente,
        apenas_com_interacao=not incluir_vazios,
    )

    _renderizar_funil(dados["funil"])
    st.divider()
    _renderizar_eventos(dados["eventos"])
    st.divider()
    _renderizar_agenda_e_followups(dados["agendamentos"], dados["followups"])
    st.divider()
    _renderizar_uso_llm(dados["uso_llm"])