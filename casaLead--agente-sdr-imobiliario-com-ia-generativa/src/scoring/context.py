"""Contexto externo necessário para o cálculo do score do lead.

Reúne os dados que vêm de fora do objeto Lead (base de imóveis e
histórico de mensagens) e que a camada de regras (rules.py) precisa
para pontuar o lead, sem que rules.py precise conhecer banco de dados.

Este módulo não acessa banco: apenas define a estrutura de dados.
Quem popula esse contexto é scoring/builder.py (próxima etapa).
"""

from dataclasses import dataclass


@dataclass
class ContextoScoring:
    """Dados de contexto necessários para pontuar um lead.

    Attributes:
        orcamento_viavel: True se existe, na base de imóveis, ao menos
            uma opção compatível com a zona/preço (ou ticket, no caso
            de investimento) declarados pelo lead. False se a
            informação foi declarada mas nenhuma opção compatível
            existe. None se não há dado suficiente para verificar
            (zona ou preço/ticket ainda não informados).
        turnos_substantivos: número de mensagens do lead na conversa
            com conteúdo não vazio e não monossilábico, usado como
            proxy de engajamento real.
    """

    orcamento_viavel: bool | None = None
    turnos_substantivos: int = 0