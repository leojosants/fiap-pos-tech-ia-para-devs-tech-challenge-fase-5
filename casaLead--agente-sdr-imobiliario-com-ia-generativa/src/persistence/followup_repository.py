"""Repositório de tentativas de follow-up.

Encapsula todo o acesso SQL à tabela followups, expondo aos demais
módulos apenas objetos de domínio (Followup).

Mesmo estilo do appointment_repository: conversão explícita, sem
mapeamento genérico de colunas — poucos campos, nenhum JSON.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.enums import FollowupStatus
from src.core.models import Followup
from src.persistence.database import get_connection


class FollowupRepository:
    """Acesso às tentativas de reengajamento de leads inativos."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    # --------------------------------------------------------
    # Mapeamento
    # --------------------------------------------------------

    @staticmethod
    def _to_domain(row: sqlite3.Row) -> Followup:
        """Converte uma linha do banco em objeto de domínio."""
        return Followup(
            id=row["id"],
            lead_id=row["lead_id"],
            conversation_id=row["conversation_id"],
            tentativa=row["tentativa"],
            mensagem=row["mensagem"],
            status=FollowupStatus(row["status"]),
            motivo=row["motivo"],
            agendado_para=datetime.fromisoformat(row["agendado_para"]),
            enviado_em=(
                datetime.fromisoformat(row["enviado_em"])
                if row["enviado_em"]
                else None
            ),
        )

    # --------------------------------------------------------
    # Escrita
    # --------------------------------------------------------

    def criar(self, followup: Followup) -> Followup:
        """Registra uma nova tentativa de follow-up."""
        agora = datetime.now()
        followup.agendado_para = agora

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO followups
                    (lead_id, conversation_id, tentativa, mensagem, status,
                     motivo, agendado_para, enviado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    followup.lead_id,
                    followup.conversation_id,
                    followup.tentativa,
                    followup.mensagem,
                    str(followup.status),
                    followup.motivo,
                    agora.isoformat(),
                    followup.enviado_em.isoformat() if followup.enviado_em else None,
                ),
            )
            followup.id = cursor.lastrowid

        return followup

    def marcar_enviado(self, followup_id: int) -> None:
        """Registra que a tentativa foi de fato enviada, com o carimbo
        de horário do envio."""
        with get_connection(self._db_path) as conn:
            conn.execute(
                "UPDATE followups SET status = ?, enviado_em = ? WHERE id = ?",
                (
                    str(FollowupStatus.ENVIADO),
                    datetime.now().isoformat(),
                    followup_id,
                ),
            )

    def atualizar_status(self, followup_id: int, status: FollowupStatus) -> None:
        """Altera o status sem tocar em enviado_em.

        Usado para RESPONDIDO e SEM_RESPOSTA — nenhum dos dois deve
        sobrescrever o carimbo de envio original, que marcar_enviado()
        já gravou. Só marcar_enviado() escreve em enviado_em.
        """
        with get_connection(self._db_path) as conn:
            conn.execute(
                "UPDATE followups SET status = ? WHERE id = ?",
                (str(status), followup_id),
            )

    # --------------------------------------------------------
    # Leitura
    # --------------------------------------------------------

    def buscar_por_id(self, followup_id: int) -> Followup | None:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM followups WHERE id = ?", (followup_id,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def listar_do_lead(self, lead_id: int) -> list[Followup]:
        """Tentativas do lead, da mais antiga para a mais recente."""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM followups WHERE lead_id = ? ORDER BY id",
                (lead_id,),
            ).fetchall()
        return [self._to_domain(r) for r in rows]

    def ultima_tentativa_do_lead(self, lead_id: int) -> Followup | None:
        """A tentativa mais recente registrada para o lead.

        Usada pelo FollowupManager para saber o número da próxima
        tentativa e o status da última — por exemplo, se já foi
        respondida, o que interrompe a escalada.
        """
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM followups WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ).fetchone()
        return self._to_domain(row) if row else None

    def contar_tentativas(self, lead_id: int) -> int:
        """Quantas tentativas já foram registradas para o lead."""
        with get_connection(self._db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM followups WHERE lead_id = ?", (lead_id,)
            ).fetchone()[0]

    # --------------------------------------------------------
    # Agregações — insumo do dashboard
    # --------------------------------------------------------

    def estatisticas(self) -> dict:
        """Contagem de follow-ups por status."""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM followups GROUP BY status"
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM followups").fetchone()[0]

        return {
            "total": total,
            "por_status": {r["status"]: r["c"] for r in rows},
        }