"""Página do corretor — resumos, agenda e follow-up (Etapa 7).

Visão de trabalho para o corretor humano: leads com resumo já gerado,
compromissos agendados nos próximos dias, e o gatilho manual da
verificação de follow-up — que até esta etapa só existia como método
pronto no Orchestrator (executar_verificacao_followup), sem nenhum
botão ou rotina que o acionasse (pendência 37 de
docs/decisoes_tecnicas.md).
"""

import streamlit as st

from src.core.enums import AppointmentType

# Mesmo rótulo em português já usado em scheduling_agent.py e
# summarizer.py — duplicado aqui de propósito, não importado. Mesma
# decisão já registrada no projeto (item 35 de docs/decisoes_tecnicas.md):
# três entradas custam menos duplicadas do que acopladas a um símbolo
# privado (_TIPOS_LEGIVEIS) de outro módulo.
_TIPOS_LEGIVEIS = {
    AppointmentType.VISITA_IMOVEL: "Visita ao imóvel",
    AppointmentType.REUNIAO_ONLINE: "Reunião online",
    AppointmentType.REUNIAO_PRESENCIAL: "Reunião presencial",
}

# Threshold de demonstração: minutos, não horas — permite mostrar o
# ciclo completo de follow-up (inativo -> reengajado -> escalado) numa
# demonstração ao vivo, sem esperar 24h de verdade. Só aparece na tela
# quando o sistema já está em modo demonstrativo (sem chave de API ou
# DEMO_MODE=true) — resolve a pendência 36 de docs/decisoes_tecnicas.md
# ("sem atalho de DEMO_MODE para acelerar a demonstração").
_HORAS_PADRAO_PRODUCAO = 24.0
_HORAS_ATALHO_DEMO = 1 / 60  # 1 minuto


def _renderizar_verificacao_followup(orquestrador) -> None:
    st.subheader("Verificação de follow-up")
    st.caption(
        "Identifica leads sem atividade há mais que o período informado "
        "e decide reengajar (1ª/2ª tentativa) ou escalar para "
        "atendimento humano (a partir da 3ª)."
    )

    em_modo_demo = orquestrador.diagnostico().get("modo") == "demonstrativo"

    if em_modo_demo:
        atalho = st.checkbox(
            "Atalho de demonstração: tratar qualquer lead parado há "
            "mais de 1 minuto como inativo",
            value=False,
            help="Só aparece em modo demonstrativo. Evita esperar 24h "
                 "de verdade para mostrar o ciclo de follow-up ao vivo.",
        )
    else:
        atalho = False

    horas = (
        _HORAS_ATALHO_DEMO
        if atalho
        else st.number_input(
            "Considerar inativo após quantas horas sem atividade",
            min_value=0.01,
            value=_HORAS_PADRAO_PRODUCAO,
            step=1.0,
        )
    )

    if st.button("Verificar leads inativos agora", type="primary"):
        resultados = orquestrador.executar_verificacao_followup(horas=horas)
        _exibir_resultado_followup(resultados)


def _resumir_resultados(resultados: list) -> dict:
    """Conta envios e escaladas num lote de ResultadoFollowup.

    Função pura, sem nenhuma chamada a st.* — testável isoladamente,
    mesmo padrão de _serie() em page_dashboard.py e _escapar_cifrao()
    em page_chat.py.
    """
    return {
        "total": len(resultados),
        "enviados": sum(1 for r in resultados if r.houve_envio),
        "escalados": sum(1 for r in resultados if r.houve_escalada),
    }


def _exibir_resultado_followup(resultados: list) -> None:
    if not resultados:
        st.info("Nenhum lead inativo encontrado com esse critério.")
        return

    resumo = _resumir_resultados(resultados)

    st.success(
        f"{resumo['total']} lead(s) processado(s) — "
        f"{resumo['enviados']} reengajado(s), "
        f"{resumo['escalados']} escalado(s) para atendimento humano."
    )

    if resumo["escalados"]:
        st.warning(
            f"{resumo['escalados']} lead(s) escalado(s) — resumo gerado "
            f"automaticamente, disponível na seção abaixo."
        )


def _renderizar_agenda(orquestrador) -> None:
    st.subheader("Agenda — próximos 7 dias")

    agendamentos = orquestrador.agendamentos.listar_proximos(dias=7)

    if not agendamentos:
        st.caption("Nenhum compromisso agendado para os próximos 7 dias.")
        return

    for ap in agendamentos:
        lead = orquestrador.leads.buscar_por_id(ap.lead_id)
        nome_lead = lead.nome if lead and lead.nome else f"Lead #{ap.lead_id}"
        tipo_legivel = _TIPOS_LEGIVEIS.get(ap.tipo, str(ap.tipo))

        with st.container(border=True):
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"**{nome_lead}**")
                st.caption(tipo_legivel)
            with col2:
                st.markdown(f"🗓️ {ap.data_hora.strftime('%d/%m %H:%M')}")
                st.caption(str(ap.status).replace("_", " ").capitalize())

            if ap.property_id:
                imovel = orquestrador.imoveis.buscar_por_id(ap.property_id)
                if imovel:
                    st.caption(f"Imóvel: {imovel.titulo} (`{imovel.codigo}`)")


def _renderizar_resumos(orquestrador) -> None:
    st.subheader("Resumos para o corretor")
    st.caption(
        "Leads com resumo já gerado — automaticamente quando ficam "
        "quentes, quando um agendamento é confirmado, ou quando são "
        "escalados por follow-up."
    )

    leads = orquestrador.leads.listar(limite=500)
    com_resumo = [lead for lead in leads if lead.resumo_corretor.strip()]

    if not com_resumo:
        st.info("Nenhum resumo gerado ainda.")
        return

    for lead in com_resumo:
        nome = lead.nome if lead.nome else f"Lead #{lead.id}"
        titulo = f"{nome} — {lead.temperature} · score {lead.score}"

        with st.expander(titulo):
            col1, col2 = st.columns(2)
            col1.caption(f"Status: {str(lead.status).replace('_', ' ')}")
            col2.caption(f"Intenção: {lead.intent}")
            st.markdown(lead.resumo_corretor)


def renderizar(orquestrador) -> None:
    """Desenha a página do corretor.

    Mesmo princípio de page_chat.py e page_dashboard.py: recebe o
    orquestrador já montado, não conhece repositório nenhum diretamente.
    """
    st.title("🧑‍💼 Painel do corretor — CasaLead")
    st.caption("Resumos, agenda e follow-up de leads")

    _renderizar_verificacao_followup(orquestrador)
    st.divider()
    _renderizar_agenda(orquestrador)
    st.divider()
    _renderizar_resumos(orquestrador)