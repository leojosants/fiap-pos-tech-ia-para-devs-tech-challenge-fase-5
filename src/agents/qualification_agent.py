"""Agente de qualificação.

Extrai intenção e informações de qualificação das mensagens do lead,
combinando duas estratégias complementares:

    1. Detecção por padrões (regex) — rápida, gratuita e confiável em
       valores numéricos e termos conhecidos.
    2. Modelo de linguagem — compreende formulações abertas que os
       padrões não alcançam.

Quando ambas divergem sobre um valor numérico, a detecção por padrões
prevalece: um erro de ordem de grandeza no orçamento (850000 lido como
85000) compromete toda a recomendação subsequente, e o texto original
é evidência mais forte que a inferência do modelo.
"""

import logging
from dataclasses import dataclass, field

from src.core.enums import (
    EventType,
    Intent,
    InvestmentGoal,
    InvestorProfile,
    PropertyType,
    Urgency,
    Zone,
)
from src.core.models import Lead
from src.llm import demo_engine as det
from src.llm.groq_client import GroqClient
from src.llm.prompts import PROMPT_EXTRACAO

logger = logging.getLogger(__name__)

# Tolerância relativa para considerar dois valores numéricos equivalentes
_TOLERANCIA_DIVERGENCIA = 0.05


@dataclass
class ResultadoQualificacao:
    """Registro do que foi extraído em um turno."""

    slots_atualizados: dict = field(default_factory=dict)
    intent_identificada: Intent | None = None
    usou_llm: bool = False
    divergencias: list[str] = field(default_factory=list)
    latencia_ms: int = 0

    @property
    def houve_captura(self) -> bool:
        return bool(self.slots_atualizados) or self.intent_identificada is not None


class QualificationAgent:
    """Extrai e consolida as informações de qualificação do lead."""

    def __init__(self, cliente: GroqClient | None = None) -> None:
        self._cliente = cliente or GroqClient()

    # --------------------------------------------------------
    # Etapa 1 — detecção por padrões
    # --------------------------------------------------------

    @staticmethod
    def _extrair_por_padroes(texto: str, lead: Lead) -> dict:
        """Extrai o que os padrões conhecidos alcançam.

        Só considera slots ainda não preenchidos: informação já coletada
        não deve ser sobrescrita por menção incidental em outra mensagem.
        """
        capturado: dict = {}

        if not lead.nome:
            nome = det.detectar_nome(texto)
            if nome:
                capturado["nome"] = nome

        # A intenção é o único slot que aceita correção explícita: se o
        # lead disser "na verdade quero alugar", a declaração direta
        # prevalece sobre a inferência anterior.
        intent = det.detectar_intencao(texto)
        if intent != Intent.INDEFINIDA and intent != lead.intent:
            capturado["intent"] = intent

        valor = det.detectar_valor(texto)
        intent_efetiva = capturado.get("intent", lead.intent)

        if intent_efetiva == Intent.INVESTIMENTO:
            if valor and lead.ticket_disponivel is None:
                capturado["ticket_disponivel"] = valor
        else:
            if valor and lead.preco_max is None:
                capturado["preco_max"] = valor

            if lead.zona_interesse is None:
                zona = det.detectar_zona(texto)
                if zona:
                    capturado["zona_interesse"] = zona

            if not lead.bairros_interesse:
                bairros = det.detectar_bairros(texto)
                if bairros:
                    capturado["bairros_interesse"] = bairros

            if lead.quartos_desejados is None:
                quartos = det.detectar_quartos(texto)
                if quartos:
                    capturado["quartos_desejados"] = quartos

        if lead.urgencia == Urgency.NAO_INFORMADA:
            urgencia = det.detectar_urgencia(texto)
            if urgencia:
                capturado["urgencia"] = Urgency(urgencia)

        if not lead.disponibilidade_reuniao:
            disponibilidade = det.detectar_disponibilidade(texto)
            if disponibilidade:
                capturado["disponibilidade_reuniao"] = disponibilidade

        return capturado

    # --------------------------------------------------------
    # Etapa 2 — extração por modelo
    # --------------------------------------------------------

    def _extrair_por_llm(
        self, texto: str, ultima_pergunta_agente: str = ""
    ) -> tuple[dict, int]:
        """Solicita ao modelo a extração estruturada. Falha não propaga.

        Quando `ultima_pergunta_agente` é informada, ela é incluída como
        contexto adicional — não para o modelo extrair dados dela, mas
        para desambiguar respostas curtas do lead. Sem isso, uma resposta
        como "2" a "quantos quartos você precisa?" chega ao modelo como
        uma string isolada, sem relação visível com nenhum campo — e a
        própria regra do prompt de "nunca deduzir" faz o modelo, com
        razão, devolver null. Ver docs/decisoes_tecnicas.md, seção 6d.
        """
        conteudo = texto
        if ultima_pergunta_agente:
            conteudo = (
                f"PERGUNTA ANTERIOR (feita pela assistente): "
                f"{ultima_pergunta_agente}\n"
                f"RESPOSTA DA PESSOA: {texto}"
            )

        dados, resposta = self._cliente.extrair_json(PROMPT_EXTRACAO, conteudo)
        if not dados:
            logger.info("Extração via LLM indisponível: %s", resposta.erro)
            return {}, resposta.latencia_ms
        return dados, resposta.latencia_ms

    @staticmethod
    def _normalizar_llm(dados: dict, lead: Lead) -> dict:
        """Converte o JSON do modelo em slots do domínio.

        Valores fora dos conjuntos válidos são descartados silenciosamente
        — é a barreira contra alucinação de categorias inexistentes.
        """
        def _enum(valor, classe):
            try:
                return classe(valor) if valor else None
            except ValueError:
                logger.info("Valor inválido descartado: %r para %s", valor, classe.__name__)
                return None

        mapa: dict = {}

        if not lead.nome and dados.get("nome"):
            candidato = str(dados["nome"]).strip()
            if candidato.lower() not in det._NAO_SAO_NOMES and len(candidato) >= 3:
                mapa["nome"] = candidato

        if lead.intent == Intent.INDEFINIDA:
            intent = _enum(dados.get("intent"), Intent)
            if intent:
                mapa["intent"] = intent

        intent_efetiva = mapa.get("intent", lead.intent)

        if intent_efetiva == Intent.INVESTIMENTO:
            if lead.ticket_disponivel is None and dados.get("ticket"):
                valor = float(dados["ticket"])
                if valor >= 10_000:
                    mapa["ticket_disponivel"] = valor
            if lead.perfil_investidor == InvestorProfile.NAO_INFORMADO:
                perfil = _enum(dados.get("perfil_investidor"), InvestorProfile)
                if perfil:
                    mapa["perfil_investidor"] = perfil
            if lead.objetivo_investimento == InvestmentGoal.NAO_INFORMADO:
                objetivo = _enum(dados.get("objetivo_investimento"), InvestmentGoal)
                if objetivo:
                    mapa["objetivo_investimento"] = objetivo
            if lead.expectativa_retorno is None and dados.get("expectativa_retorno"):
                mapa["expectativa_retorno"] = float(dados["expectativa_retorno"])
            if not lead.prazo_investimento and dados.get("prazo_investimento"):
                mapa["prazo_investimento"] = str(dados["prazo_investimento"])
        else:
            if lead.preco_max is None and dados.get("preco_max"):
                valor = float(dados["preco_max"])
                # Piso de plausibilidade: nenhum imóvel em São Paulo custa
                # menos de R$ 500 (aluguel) — valores abaixo disso indicam
                # extração equivocada ou entrada não-séria.
                if valor >= 500:
                    mapa["preco_max"] = valor
            if lead.zona_interesse is None:
                zona = _enum(dados.get("zona"), Zone)
                if zona:
                    mapa["zona_interesse"] = zona
            if not lead.bairros_interesse and dados.get("bairros"):
                mapa["bairros_interesse"] = [str(b) for b in dados["bairros"]]
            if lead.tipo_imovel is None:
                tipo = _enum(dados.get("tipo_imovel"), PropertyType)
                if tipo:
                    mapa["tipo_imovel"] = tipo
            if lead.quartos_desejados is None and dados.get("quartos"):
                mapa["quartos_desejados"] = int(dados["quartos"])
            if lead.vagas_desejadas is None and dados.get("vagas"):
                mapa["vagas_desejadas"] = int(dados["vagas"])

        if not lead.preferencias and dados.get("preferencias"):
            mapa["preferencias"] = [
                " ".join(str(p).split()) for p in dados["preferencias"] if str(p).strip()
            ]

        if lead.urgencia == Urgency.NAO_INFORMADA:
            urgencia = _enum(dados.get("urgencia"), Urgency)
            if urgencia:
                mapa["urgencia"] = urgencia

        if not lead.disponibilidade_reuniao and dados.get("disponibilidade"):
            mapa["disponibilidade_reuniao"] = str(dados["disponibilidade"])

        return mapa

    # --------------------------------------------------------
    # Etapa 3 — verificação cruzada
    # --------------------------------------------------------

    @staticmethod
    def _consolidar(
        por_padroes: dict, por_llm: dict
    ) -> tuple[dict, list[str]]:
        """Combina as duas extrações, priorizando padrões em números.

        Retorna o mapa consolidado e a lista de divergências detectadas,
        registradas para auditoria.
        """
        campos_numericos = {
            "preco_max", "ticket_disponivel", "quartos_desejados",
            "vagas_desejadas", "expectativa_retorno",
        }

        consolidado = dict(por_llm)
        divergencias: list[str] = []

        for campo, valor_padrao in por_padroes.items():
            valor_llm = por_llm.get(campo)

            if campo in campos_numericos and valor_llm is not None:
                referencia = max(abs(float(valor_padrao)), 1.0)
                if abs(float(valor_padrao) - float(valor_llm)) / referencia > _TOLERANCIA_DIVERGENCIA:
                    divergencias.append(
                        f"{campo}: padrões={valor_padrao} vs modelo={valor_llm} "
                        f"— prevalece o valor detectado no texto"
                    )

            consolidado[campo] = valor_padrao

        return consolidado, divergencias

    # --------------------------------------------------------
    # Interface pública
    # --------------------------------------------------------

    def qualificar(
        self,
        lead: Lead,
        texto: str,
        *,
        forcar_llm: bool = False,
        ultima_pergunta_agente: str = "",
    ) -> ResultadoQualificacao:
        """Processa uma mensagem e atualiza o lead com o que foi extraído.

        A chamada ao modelo é evitada quando os padrões já capturaram tudo
        que faltava, reduzindo custo e latência sem perda de qualidade.

        `ultima_pergunta_agente` é opcional e só afeta o caminho por LLM —
        ver `_extrair_por_llm`.
        """
        resultado = ResultadoQualificacao()

        por_padroes = self._extrair_por_padroes(texto, lead)
        pendentes_antes = [s for s, ok in lead.slots_status().items() if not ok]
        cobriu_tudo = all(s in por_padroes for s in pendentes_antes)

        por_llm: dict = {}
        if forcar_llm or not (cobriu_tudo and por_padroes):
            if not self._cliente._settings.modo_demo:
                dados, latencia = self._extrair_por_llm(
                    texto, ultima_pergunta_agente
                )
                resultado.latencia_ms = latencia
                if dados:
                    por_llm = self._normalizar_llm(dados, lead)
                    resultado.usou_llm = True

        consolidado, divergencias = self._consolidar(por_padroes, por_llm)
        resultado.divergencias = divergencias

        for campo, valor in consolidado.items():
            if campo == "intent":
                resultado.intent_identificada = valor
                lead.intent = valor
            else:
                setattr(lead, campo, valor)
                resultado.slots_atualizados[campo] = valor

        return resultado

    def eventos_do_resultado(
        self, resultado: ResultadoQualificacao, lead_id: int
    ) -> list[tuple]:
        """Traduz o resultado em eventos para o log de observabilidade."""
        eventos: list[tuple] = []

        if resultado.intent_identificada:
            eventos.append((
                EventType.INTENCAO_IDENTIFICADA,
                {"intent": str(resultado.intent_identificada),
                 "via": "llm" if resultado.usou_llm else "padroes"},
            ))

        for campo, valor in resultado.slots_atualizados.items():
            eventos.append((
                EventType.SLOT_PREENCHIDO,
                {"slot": campo, "valor": str(valor),
                 "via": "llm" if resultado.usou_llm else "padroes"},
            ))

        return eventos