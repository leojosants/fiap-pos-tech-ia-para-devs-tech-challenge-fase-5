"""Módulo de scoring e classificação de leads (Etapa 5).

Calcula um score de 0 a 100 e uma temperatura (quente/morno/frio)
para cada lead, usando regras de negócio explícitas — não um
classificador de machine learning. Justificativa completa em
docs/decisoes_tecnicas.md (seção Etapa 5).
"""

from src.scoring.context import ContextoScoring
from src.scoring.rules import ResultadoScoring, calcular_score

__all__ = ["ContextoScoring", "ResultadoScoring", "calcular_score"]