"""Repositório de leads.

Encapsula a persistência da entidade Lead, incluindo a serialização dos
campos compostos (listas em JSON) e a conversão entre enums do domínio
e valores textuais do banco.

O mapeamento é declarado uma única vez em _COLUNAS, e as operações de
INSERT e UPDATE são derivadas dele — evitando a divergência típica de
escrever cada coluna manualmente em vários lugares.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.enums import (
    Intent,
    InvestmentGoal,
    InvestorProfile,
    LeadStatus,
    LeadTemperature,
    PropertyType,
    Urgency,
    Zone,
)
from src.core.models import Lead
from src.persistence.database import get_connection

# Colunas persistidas, na ordem do schema. O id e os timestamps são
# tratados separadamente.
_COLUNAS = (
    "nome", "telefone", "email", "canal_origem",
    "intent", "status", "temperature", "score",
    "zona_interesse", "bairros_interesse", "tipo_imovel",
    "preco_min", "preco_max", "quartos_desejados", "vagas_desejadas",
    "preferencias", "urgencia", "disponibilidade_reuniao",
    "perfil_investidor", "ticket_disponivel", "objetivo_investimento",
    "expectativa_retorno", "prazo_investimento",
    "resumo_corretor",
)

# Campos armazenados como JSON em coluna TEXT
_CAMPOS_JSON = {"bairros_interesse", "preferencias"}

# Campos que são enums opcionais — podem valer None no banco
_ENUMS_OPCIONAIS = {
    "zona_interesse": Zone,
    "tipo_imovel": PropertyType,
}

# Campos que são enums obrigatórios
_ENUMS_OBRIGATORIOS = {
    "intent": Intent,
    "status": LeadStatus,
    "temperature": LeadTemperature,
    "urgencia": Urgency,
    "perfil_investidor": InvestorProfile,
    "objetivo_investimento": InvestmentGoal,
}


class LeadRepository:
    """Persistência da entidade Lead."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    # --------------------------------------------------------
    # Mapeamento
    # --------------------------------------------------------

    @staticmethod
    def _to_row(lead: Lead) -> list:
        """Converte o objeto de domínio em valores para o banco."""
        valores = []
        for coluna in _COLUNAS:
            valor = getattr(lead, coluna)
            if coluna in _CAMPOS_JSON:
                valores.append(json.dumps(valor, ensure_ascii=False))
            elif valor is None:
                valores.append(None)
            else:
                # StrEnum serializa como str; demais tipos passam direto
                valores.append(str(valor) if isinstance(valor, str) else valor)
        return valores

    @staticmethod
    def _to_domain(row: sqlite3.Row) -> Lead:
        """Converte uma linha do banco em objeto de domínio."""
        dados: dict = {"id": row["id"]}

        for coluna in _COLUNAS:
            valor = row[coluna]

            if coluna in _CAMPOS_JSON:
                dados[coluna] = json.loads(valor) if valor else []
            elif coluna in _ENUMS_OBRIGATORIOS:
                dados[coluna] = _ENUMS_OBRIGATORIOS[coluna](valor)
            elif coluna in _ENUMS_OPCIONAIS:
                dados[coluna] = _ENUMS_OPCIONAIS[coluna](valor) if valor else None
            else:
                dados[coluna] = valor

        dados["created_at"] = datetime.fromisoformat(row["created_at"])
        dados["updated_at"] = datetime.fromisoformat(row["updated_at"])
        return Lead(**dados)

    # --------------------------------------------------------
    # Escrita
    # --------------------------------------------------------

    def criar(self, lead: Lead) -> Lead:
        """Insere um novo lead e devolve o objeto com o id atribuído."""
        agora = datetime.now()
        lead.created_at = agora
        lead.updated_at = agora

        colunas = ", ".join([*_COLUNAS, "created_at", "updated_at"])
        marcadores = ", ".join("?" for _ in range(len(_COLUNAS) + 2))
        valores = [*self._to_row(lead), agora.isoformat(), agora.isoformat()]

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                f"INSERT INTO leads ({colunas}) VALUES ({marcadores})", valores
            )
            lead.id = cursor.lastrowid

        return lead

    def atualizar(self, lead: Lead) -> Lead:
        """Grava o estado atual do lead. Exige que o lead já exista."""
        if lead.id is None:
            raise ValueError("Lead sem id não pode ser atualizado. Use criar().")

        lead.updated_at = datetime.now()
        atribuicoes = ", ".join(f"{c} = ?" for c in _COLUNAS)
        valores = [*self._to_row(lead), lead.updated_at.isoformat(), lead.id]

        with get_connection(self._db_path) as conn:
            conn.execute(
                f"UPDATE leads SET {atribuicoes}, updated_at = ? WHERE id = ?",
                valores,
            )

        return lead

    def salvar(self, lead: Lead) -> Lead:
        """Insere ou atualiza, conforme o lead já possua id."""
        return self.atualizar(lead) if lead.id else self.criar(lead)

    def remover(self, lead_id: int) -> None:
        """Remove um lead e, em cascata, suas conversas e mensagens."""
        with get_connection(self._db_path) as conn:
            conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))

    # --------------------------------------------------------
    # Leitura
    # --------------------------------------------------------

    def buscar_por_id(self, lead_id: int) -> Lead | None:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def listar(
        self,
        *,
        status: LeadStatus | None = None,
        temperature: LeadTemperature | None = None,
        intent: Intent | None = None,
        ordenar_por: str = "score",
        limite: int = 100,
    ) -> list[Lead]:
        """Lista leads com filtros opcionais. Alimenta o dashboard.

        A ordenação padrão por score decrescente reflete a prioridade
        de atendimento: leads mais quentes aparecem primeiro.
        """
        clausulas: list[str] = []
        params: list[object] = []

        if status is not None:
            clausulas.append("status = ?")
            params.append(str(status))
        if temperature is not None:
            clausulas.append("temperature = ?")
            params.append(str(temperature))
        if intent is not None:
            clausulas.append("intent = ?")
            params.append(str(intent))

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        coluna_ordem = {
            "score": "score DESC, updated_at DESC",
            "recentes": "updated_at DESC",
            "antigos": "created_at ASC",
        }.get(ordenar_por, "score DESC, updated_at DESC")

        params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM leads {where} ORDER BY {coluna_ordem} LIMIT ?",
                params,
            ).fetchall()

        return [self._to_domain(r) for r in rows]

    def contar(self) -> int:
        with get_connection(self._db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    # --------------------------------------------------------
    # Agregações — insumo do dashboard e das métricas
    # --------------------------------------------------------

    def estatisticas(self) -> dict:
        """Resumo do funil, exibido no dashboard."""
        with get_connection(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

            por_status = {
                r["status"]: r["c"]
                for r in conn.execute(
                    "SELECT status, COUNT(*) c FROM leads GROUP BY status"
                ).fetchall()
            }
            por_temperatura = {
                r["temperature"]: r["c"]
                for r in conn.execute(
                    "SELECT temperature, COUNT(*) c FROM leads GROUP BY temperature"
                ).fetchall()
            }
            por_intencao = {
                r["intent"]: r["c"]
                for r in conn.execute(
                    "SELECT intent, COUNT(*) c FROM leads GROUP BY intent"
                ).fetchall()
            }
            score_medio = conn.execute(
                "SELECT AVG(score) FROM leads"
            ).fetchone()[0]

        return {
            "total": total,
            "por_status": por_status,
            "por_temperatura": por_temperatura,
            "por_intencao": por_intencao,
            "score_medio": round(score_medio, 1) if score_medio else 0.0,
        }

    def buscar_inativos(self, horas: int = 24) -> list[Lead]:
        """Leads sem atividade há mais que o período informado.

        Base do gerenciador de follow-up (cenário 3.3 do enunciado):
        identifica quem iniciou conversa e não retornou.
        """
        limite_iso = datetime.now().isoformat()

        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM leads
                WHERE status NOT IN ('encaminhado', 'perdido')
                  AND (julianday(?) - julianday(updated_at)) * 24 >= ?
                ORDER BY score DESC
                """,
                (limite_iso, horas),
            ).fetchall()

        return [self._to_domain(r) for r in rows]