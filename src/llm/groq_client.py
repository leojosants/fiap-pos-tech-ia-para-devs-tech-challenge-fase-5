"""Cliente da Groq API para o CasaLead.

Encapsula toda a comunicação com o provedor de LLM. Nenhum módulo acima
desta camada conhece a Groq — recebem apenas texto ou dados estruturados.

Princípio de projeto: o cliente nunca propaga falha de infraestrutura
para a conversa. Erro de rede, cota esgotada ou chave inválida resultam
em uma resposta sinalizada como indisponível, e o orquestrador decide o
que fazer — tipicamente, recorrer ao motor determinístico.
"""

import json
import logging
import time
from dataclasses import dataclass, field

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Resultado de uma chamada ao modelo."""

    conteudo: str
    sucesso: bool
    modelo: str = ""
    latencia_ms: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    erro: str = ""

    @property
    def total_tokens(self) -> int:
        return self.tokens_entrada + self.tokens_saida


@dataclass
class UsageStats:
    """Acumulador de uso, exibido no painel de observabilidade."""

    chamadas: int = 0
    falhas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencias: list[int] = field(default_factory=list)

    def registrar(self, resposta: LLMResponse) -> None:
        self.chamadas += 1
        if not resposta.sucesso:
            self.falhas += 1
            return
        self.tokens_entrada += resposta.tokens_entrada
        self.tokens_saida += resposta.tokens_saida
        self.latencias.append(resposta.latencia_ms)

    def resumo(self) -> dict:
        media = round(sum(self.latencias) / len(self.latencias)) if self.latencias else 0
        return {
            "chamadas": self.chamadas,
            "falhas": self.falhas,
            "taxa_sucesso": (
                round((self.chamadas - self.falhas) / self.chamadas * 100, 1)
                if self.chamadas
                else 0.0
            ),
            "tokens_entrada": self.tokens_entrada,
            "tokens_saida": self.tokens_saida,
            "latencia_media_ms": media,
        }


class GroqClient:
    """Cliente de inferência sobre a Groq API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = None
        self.stats = UsageStats()

        if not self._settings.modo_demo:
            self._client = self._criar_cliente()

    def _criar_cliente(self):
        """Instancia o SDK. Falha de import ou credencial não derruba a app."""
        try:
            from groq import Groq

            return Groq(
                api_key=self._settings.groq_api_key,
                timeout=self._settings.timeout_segundos,
            )
        except Exception as exc:
            logger.warning("Não foi possível inicializar o cliente Groq: %s", exc)
            return None

    @property
    def disponivel(self) -> bool:
        """Indica se há um cliente utilizável nesta execução."""
        return self._client is not None

    # --------------------------------------------------------
    # Chamada base
    # --------------------------------------------------------

    def _chamar(
        self,
        mensagens: list[dict],
        *,
        modelo: str,
        temperatura: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Executa a chamada com retry em falhas transitórias.

        Retenta apenas o número de vezes configurado em max_tentativas,
        com espera progressiva. Esgotadas as tentativas, devolve uma
        resposta marcada como insucesso — nunca levanta exceção.
        """
        if not self.disponivel:
            return LLMResponse(
                conteudo="",
                sucesso=False,
                erro="Cliente Groq indisponível (modo demonstrativo).",
            )

        kwargs = {
            "model": modelo,
            "messages": mensagens,
            "temperature": temperatura,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        ultimo_erro = ""

        for tentativa in range(1, self._settings.max_tentativas + 1):
            inicio = time.perf_counter()
            try:
                resposta = self._client.chat.completions.create(**kwargs)
                latencia = int((time.perf_counter() - inicio) * 1000)

                uso = getattr(resposta, "usage", None)
                resultado = LLMResponse(
                    conteudo=resposta.choices[0].message.content or "",
                    sucesso=True,
                    modelo=modelo,
                    latencia_ms=latencia,
                    tokens_entrada=getattr(uso, "prompt_tokens", 0) if uso else 0,
                    tokens_saida=getattr(uso, "completion_tokens", 0) if uso else 0,
                )
                self.stats.registrar(resultado)
                return resultado

            except Exception as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Falha na chamada ao modelo (tentativa %d/%d): %s",
                    tentativa,
                    self._settings.max_tentativas,
                    ultimo_erro,
                )
                if tentativa < self._settings.max_tentativas:
                    time.sleep(0.8 * tentativa)

        resultado = LLMResponse(conteudo="", sucesso=False, erro=ultimo_erro)
        self.stats.registrar(resultado)
        return resultado

    # --------------------------------------------------------
    # Interface pública
    # --------------------------------------------------------

    def conversar(
        self, prompt_sistema: str, historico: list[dict]
    ) -> LLMResponse:
        """Gera a próxima fala do agente.

        Usa o modelo rápido: a pessoa está esperando, e latência baixa
        é parte da experiência de atendimento.
        """
        mensagens = [{"role": "system", "content": prompt_sistema}, *historico]
        return self._chamar(
            mensagens,
            modelo=self._settings.model_fast,
            temperatura=self._settings.temperatura_conversa,
            max_tokens=self._settings.max_tokens_resposta,
        )

    def extrair_json(
        self,
        prompt_sistema: str,
        conteudo: str,
        *,
        usar_modelo_smart: bool = True,
    ) -> tuple[dict | None, LLMResponse]:
        """Executa uma extração estruturada e devolve o dado já parseado.

        Usa o modelo de maior capacidade por padrão e temperatura baixa:
        extrair informação não admite criatividade. Retorna (None, resposta)
        quando a chamada falha ou o retorno não é JSON válido.
        """
        modelo = (
            self._settings.model_smart
            if usar_modelo_smart
            else self._settings.model_fast
        )
        resposta = self._chamar(
            [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": conteudo},
            ],
            modelo=modelo,
            temperatura=self._settings.temperatura_extracao,
            max_tokens=800,
            json_mode=True,
        )

        if not resposta.sucesso:
            return None, resposta

        try:
            return json.loads(resposta.conteudo), resposta
        except json.JSONDecodeError as exc:
            logger.warning("Retorno do modelo não é JSON válido: %s", exc)
            resposta.sucesso = False
            resposta.erro = f"JSON inválido: {exc}"
            return None, resposta

    def resumir(self, prompt_sistema: str, conteudo: str) -> LLMResponse:
        """Gera texto analítico — usado no resumo para o corretor.

        Usa o modelo de maior capacidade: o resumo é gerado uma vez por
        lead e é o artefato que o corretor humano vai ler.
        """
        return self._chamar(
            [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": conteudo},
            ],
            modelo=self._settings.model_smart,
            temperatura=0.4,
            max_tokens=700,
        )

    def testar_conexao(self) -> tuple[bool, str]:
        """Verifica se a API responde. Usado no diagnóstico da interface."""
        if not self.disponivel:
            return False, self._settings.motivo_modo_demo or "Cliente não inicializado."

        resposta = self._chamar(
            [{"role": "user", "content": "Responda apenas: ok"}],
            modelo=self._settings.model_fast,
            temperatura=0.0,
            max_tokens=10,
        )
        if resposta.sucesso:
            return True, f"Conectado ({resposta.modelo}, {resposta.latencia_ms}ms)."
        return False, resposta.erro