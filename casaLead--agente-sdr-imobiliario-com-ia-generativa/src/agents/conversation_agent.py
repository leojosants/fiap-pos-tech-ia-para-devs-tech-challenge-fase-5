import re

"""Agente de conversação.

Responsabilidade única: produzir a próxima fala do agente, dado o estado
do lead e o histórico da conversa.

Opera em dois modos, com degradação automática entre eles:

    LLM           — resposta gerada pelo modelo, com linguagem natural
    determinístico — resposta montada a partir de frases pré-definidas

A troca de modo é transparente para quem chama: o método sempre devolve
uma resposta utilizável, e informa por qual caminho ela foi produzida.
"""

import logging
from dataclasses import dataclass

from src.core.models import Lead
from src.llm.demo_engine import DemoEngine
from src.llm.groq_client import GroqClient
from src.llm.prompts import SAUDACAO_INICIAL, montar_prompt_sistema

logger = logging.getLogger(__name__)

# Uma fala legítima da Sofia nunca é tão curta quanto isto — mesmo um
# "Oi! Tudo bem?" tem mais que isso. Observado em produção (deploy do
# Streamlit Cloud): uma resposta chegou como "Ent" — 3 caracteres,
# marcada como sucesso pela API, sem erro nenhum — e foi exibida
# quebrada ao lead. Causa raiz não identificada (não reproduzida em
# nova tentativa; não é o bug de $ duplicado nem a lógica de remover
# aspas, ambos descartados por inspeção de código). Esta guarda não
# resolve a causa raiz, mas garante que esse tipo de resposta nunca
# mais chegue ao usuário: é tratada como falha, acionando o mesmo
# fallback determinístico já usado para erro de API — ver
# docs/decisoes_tecnicas.md.
_TAMANHO_MINIMO_RESPOSTA_PLAUSIVEL = 15


@dataclass
class RespostaAgente:
    """Fala produzida pelo agente, com metadados de rastreabilidade."""

    texto: str
    origem: str              # "llm" | "deterministico" | "fallback"
    modelo: str = ""
    latencia_ms: int = 0
    tokens: int = 0
    erro: str = ""

    @property
    def usou_llm(self) -> bool:
        return self.origem == "llm"

    @property
    def houve_degradacao(self) -> bool:
        """Indica que o LLM estava previsto mas falhou."""
        return self.origem == "fallback"


class ConversationAgent:
    """Produz a fala do agente a cada turno."""

    def __init__(
        self,
        cliente: GroqClient | None = None,
        motor_demo: DemoEngine | None = None,
    ) -> None:
        self._cliente = cliente or GroqClient()
        self._demo = motor_demo or DemoEngine()

    # --------------------------------------------------------
    # Interface pública
    # --------------------------------------------------------

    @staticmethod
    def saudacao() -> str:
        """Mensagem de abertura da conversa.

        É determinística por decisão de projeto: a apresentação da marca
        não deve variar entre atendimentos, e não exige julgamento do
        modelo.
        """
        return SAUDACAO_INICIAL

    def responder(
        self,
        lead: Lead,
        texto_do_lead: str,
        historico: list[dict],
        *,
        imoveis_contexto: str = "",
        agendamento_contexto: str = "",
    ) -> RespostaAgente:
        """Gera a próxima fala do agente.

        Quando o LLM está disponível, é usado. Se a chamada falhar por
        qualquer motivo, o motor determinístico assume — a conversa
        continua, com qualidade menor, mas sem interrupção.

        O parâmetro imoveis_contexto recebe as recomendações já
        selecionadas pelo módulo de busca; o agente apenas as apresenta,
        nunca as escolhe. agendamento_contexto segue o mesmo princípio
        para compromissos: só chega aqui já pronto pelo scheduling_agent.

        Nenhum dos dois contextos é repassado ao motor determinístico —
        mesma decisão já tomada para imoveis_contexto: o modo demo
        responde por padrões fixos, sem capacidade de incorporar dados
        variáveis em linguagem natural.
        """
        if self._cliente.disponivel:
            resposta = self._responder_com_llm(
                lead, historico, imoveis_contexto, agendamento_contexto
            )
            if resposta is not None:
                return resposta

            logger.warning(
                "Falha na geração via LLM; recorrendo ao motor determinístico."
            )
            return self._responder_deterministico(
                lead, texto_do_lead, origem="fallback"
            )

        return self._responder_deterministico(
            lead, texto_do_lead, origem="deterministico"
        )

    # --------------------------------------------------------
    # Modos de geração
    # --------------------------------------------------------

    def _responder_com_llm(
        self,
        lead: Lead,
        historico: list[dict],
        imoveis_contexto: str,
        agendamento_contexto: str,
    ) -> RespostaAgente | None:
        """Gera a resposta pelo modelo. Devolve None se a chamada falhar."""
        prompt = montar_prompt_sistema(lead, imoveis_contexto, agendamento_contexto)
        resposta = self._cliente.conversar(prompt, historico)

        if not resposta.sucesso or not resposta.conteudo.strip():
            return None

        texto = self._higienizar(resposta.conteudo)

        if len(texto) < _TAMANHO_MINIMO_RESPOSTA_PLAUSIVEL:
            logger.warning(
                "Resposta do LLM implausivelmente curta (%d caracteres): "
                "%r — tratando como falha e recorrendo ao motor "
                "determinístico.",
                len(texto), texto,
            )
            return None

        return RespostaAgente(
            texto=texto,
            origem="llm",
            modelo=resposta.modelo,
            latencia_ms=resposta.latencia_ms,
            tokens=resposta.total_tokens,
        )

    def _responder_deterministico(
        self, lead: Lead, texto_do_lead: str, *, origem: str
    ) -> RespostaAgente:
        """Gera a resposta pelo motor de padrões.

        Observação: o motor determinístico também extrai informações do
        texto ao responder. Isso é redundante com o QualificationAgent,
        mas inofensivo — ambos só preenchem slots ainda vazios.
        """
        texto = self._demo.responder(lead, texto_do_lead)
        return RespostaAgente(texto=texto, origem=origem)

    # --------------------------------------------------------
    # Pós-processamento
    # --------------------------------------------------------

    @staticmethod
    def _higienizar(texto: str) -> str:
        """Remove artefatos comuns da saída do modelo.

        Modelos ocasionalmente devolvem a fala envolta em aspas, com
        prefixo de papel ou dentro de bloco de código. Nenhum desses
        elementos deve chegar ao lead.
        """
        limpo = texto.strip()

        if limpo.startswith("```"):
            linhas = [l for l in limpo.splitlines() if not l.startswith("```")]
            limpo = "\n".join(linhas).strip()

        for prefixo in ("Sofia:", "sofia:", "Agente:", "Assistente:"):
            if limpo.startswith(prefixo):
                limpo = limpo[len(prefixo):].strip()

        if len(limpo) > 1 and limpo[0] == '"' and limpo[-1] == '"':
            limpo = limpo[1:-1].strip()

        # Correção de concordância: a persona é feminina, e o modelo
        # ocasionalmente reverte para a forma masculina mais frequente.
        limpo = re.sub(r"\bObrigado\b", "Obrigada", limpo)
        limpo = re.sub(r"\bobrigado\b", "obrigada", limpo)

        return " ".join(limpo.split())