"""Gerenciamento de estado da interface Streamlit.

O Streamlit reexecuta o script inteiro a cada interação do usuário.
Objetos criados no corpo do script são descartados e recriados a cada
rerun — comportamento inadequado para o orquestrador, que carrega
cliente HTTP e conexões, e para os identificadores da sessão de
atendimento.

Este módulo concentra o que precisa sobreviver entre reruns, em um
único ponto, evitando que chaves de session_state se espalhem pela
interface.
"""

import streamlit as st

from src.agents.orchestrator import Orchestrator
from src.persistence.database import bootstrap

_CHAVE_ORQUESTRADOR = "casalead_orquestrador"
_CHAVE_LEAD = "casalead_lead_id"
_CHAVE_CONVERSA = "casalead_conversa_id"
_CHAVE_MENSAGENS = "casalead_mensagens"
_CHAVE_ULTIMO_TURNO = "casalead_ultimo_turno"


@st.cache_resource
def _bootstrap_unico() -> dict:
    """Prepara o banco uma única vez por processo.

    O decorador cache_resource garante execução única mesmo com múltiplos
    reruns e múltiplas sessões — é o que permite chamar o bootstrap a
    cada carregamento sem custo repetido.
    """
    return bootstrap()


def get_orquestrador() -> Orchestrator:
    """Devolve o orquestrador da sessão, criando-o na primeira chamada."""
    _bootstrap_unico()

    if _CHAVE_ORQUESTRADOR not in st.session_state:
        st.session_state[_CHAVE_ORQUESTRADOR] = Orchestrator()

    return st.session_state[_CHAVE_ORQUESTRADOR]


def atendimento_iniciado() -> bool:
    """Indica se já existe uma conversa em andamento nesta sessão."""
    return _CHAVE_LEAD in st.session_state


def iniciar_atendimento() -> None:
    """Abre um novo atendimento e registra a saudação."""
    orq = get_orquestrador()
    lead, conversa, saudacao = orq.iniciar_atendimento(canal="web")

    st.session_state[_CHAVE_LEAD] = lead.id
    st.session_state[_CHAVE_CONVERSA] = conversa.id
    st.session_state[_CHAVE_MENSAGENS] = [
        {"role": "assistant", "content": saudacao}
    ]
    st.session_state[_CHAVE_ULTIMO_TURNO] = None


def reiniciar_atendimento() -> None:
    """Descarta a sessão atual e começa um atendimento novo.

    Os dados do atendimento anterior permanecem no banco — o dashboard
    continua exibindo aquele lead.
    """
    for chave in (
        _CHAVE_LEAD,
        _CHAVE_CONVERSA,
        _CHAVE_MENSAGENS,
        _CHAVE_ULTIMO_TURNO,
    ):
        st.session_state.pop(chave, None)


def get_ids() -> tuple[int, int]:
    """Identificadores do lead e da conversa em andamento."""
    return st.session_state[_CHAVE_LEAD], st.session_state[_CHAVE_CONVERSA]


def get_mensagens() -> list[dict]:
    """Histórico exibido na tela."""
    return st.session_state.get(_CHAVE_MENSAGENS, [])


def adicionar_mensagem(role: str, content: str) -> None:
    st.session_state[_CHAVE_MENSAGENS].append(
        {"role": role, "content": content}
    )


def set_ultimo_turno(resultado) -> None:
    st.session_state[_CHAVE_ULTIMO_TURNO] = resultado


def get_ultimo_turno():
    return st.session_state.get(_CHAVE_ULTIMO_TURNO)