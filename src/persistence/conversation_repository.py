"""Repositório de conversas, mensagens e eventos.

Reúne as três entidades que compõem o registro do atendimento:

    conversations — sessões de atendimento de um lead
    messages      — histórico turno a turno (memória conversacional)
    events        — log estruturado para observabilidade e métricas

Ficam no mesmo módulo porque são sempre gravadas em conjunto no mesmo
ponto do fluxo: ao processar um turno, o sistema persiste a mensagem,
atualiza a conversa e registra o evento correspondente.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.enums import ConversationStatus, EventType, MessageRole
from src.core.models import Conversation, Event, Message
from src.persistence.database import get_connection


class ConversationRepository:
    """Persistência de conversas, mensagens e eventos."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    # ========================================================
    # CONVERSAS
    # ========================================================

    @staticmethod
    def _conversa_to_domain(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"],
            lead_id=row["lead_id"],
            status=ConversationStatus(row["status"]),
            canal=row["canal"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_activity_at=datetime.fromisoformat(row["last_activity_at"]),
            ended_at=(
                datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None
            ),
        )

    def criar_conversa(self, conversa: Conversation) -> Conversation:
        """Abre uma nova sessão de atendimento."""
        agora = datetime.now()
        conversa.started_at = agora
        conversa.last_activity_at = agora

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO conversations
                    (lead_id, status, canal, started_at, last_activity_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversa.lead_id,
                    str(conversa.status),
                    conversa.canal,
                    agora.isoformat(),
                    agora.isoformat(),
                ),
            )
            conversa.id = cursor.lastrowid

        return conversa

    def buscar_conversa(self, conversa_id: int) -> Conversation | None:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversa_id,)
            ).fetchone()
        return self._conversa_to_domain(row) if row else None

    def conversa_ativa_do_lead(self, lead_id: int) -> Conversation | None:
        """Retorna a sessão em aberto do lead, se houver.

        Base da continuidade: ao retomar contato, o agente reaproveita a
        conversa existente em vez de começar do zero, preservando o
        histórico.
        """
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM conversations
                WHERE lead_id = ? AND status IN ('ativa', 'aguardando_lead')
                ORDER BY last_activity_at DESC LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
        return self._conversa_to_domain(row) if row else None

    def listar_conversas_do_lead(self, lead_id: int) -> list[Conversation]:
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE lead_id = ? ORDER BY started_at",
                (lead_id,),
            ).fetchall()
        return [self._conversa_to_domain(r) for r in rows]

    def atualizar_status_conversa(
        self, conversa_id: int, status: ConversationStatus
    ) -> None:
        """Altera o status e, quando encerrada, registra o término."""
        agora = datetime.now()
        encerrada = status in (
            ConversationStatus.ENCERRADA,
            ConversationStatus.ESCALADA,
        )

        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE conversations
                SET status = ?, last_activity_at = ?, ended_at = ?
                WHERE id = ?
                """,
                (
                    str(status),
                    agora.isoformat(),
                    agora.isoformat() if encerrada else None,
                    conversa_id,
                ),
            )

    def registrar_atividade(self, conversa_id: int) -> None:
        """Atualiza o carimbo de última atividade da conversa.

        É esse carimbo que o gerenciador de follow-up consulta para
        identificar conversas interrompidas.
        """
        with get_connection(self._db_path) as conn:
            conn.execute(
                "UPDATE conversations SET last_activity_at = ? WHERE id = ?",
                (datetime.now().isoformat(), conversa_id),
            )

    # ========================================================
    # MENSAGENS
    # ========================================================

    @staticmethod
    def _mensagem_to_domain(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            modelo_usado=row["modelo_usado"],
            latencia_ms=row["latencia_ms"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def adicionar_mensagem(self, mensagem: Message) -> Message:
        """Grava um turno e atualiza a atividade da conversa."""
        agora = datetime.now()
        mensagem.created_at = agora

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, modelo_usado,
                     latencia_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mensagem.conversation_id,
                    str(mensagem.role),
                    mensagem.content,
                    mensagem.modelo_usado,
                    mensagem.latencia_ms,
                    agora.isoformat(),
                ),
            )
            mensagem.id = cursor.lastrowid

            conn.execute(
                "UPDATE conversations SET last_activity_at = ? WHERE id = ?",
                (agora.isoformat(), mensagem.conversation_id),
            )

        return mensagem

    def listar_mensagens(
        self, conversa_id: int, limite: int | None = None
    ) -> list[Message]:
        """Histórico da conversa em ordem cronológica.

        Com limite, retorna as N mais recentes — ainda em ordem
        cronológica, para preservar a leitura natural do diálogo.
        """
        sql = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id"
        params: list[object] = [conversa_id]

        if limite:
            sql = (
                "SELECT * FROM ("
                "SELECT * FROM messages WHERE conversation_id = ? "
                "ORDER BY id DESC LIMIT ?"
                ") ORDER BY id"
            )
            params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._mensagem_to_domain(r) for r in rows]

    def historico_para_llm(
        self, conversa_id: int, limite: int = 20
    ) -> list[dict]:
        """Histórico no formato esperado pela API de chat.

        Converte os papéis do domínio (lead/agent) para os papéis da API
        (user/assistant), e descarta mensagens de sistema, que não fazem
        parte do diálogo.
        """
        mapeamento = {
            MessageRole.LEAD: "user",
            MessageRole.AGENT: "assistant",
        }

        return [
            {"role": mapeamento[m.role], "content": m.content}
            for m in self.listar_mensagens(conversa_id, limite)
            if m.role in mapeamento
        ]

    def contar_mensagens(self, conversa_id: int) -> int:
        with get_connection(self._db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversa_id,),
            ).fetchone()[0]

    # ========================================================
    # EVENTOS
    # ========================================================

    def registrar_evento(
        self,
        tipo: EventType,
        *,
        lead_id: int | None = None,
        conversation_id: int | None = None,
        **detalhes,
    ) -> Event:
        """Grava um evento no log estruturado.

        Detalhes arbitrários são aceitos como argumentos nomeados e
        serializados em JSON — permitindo registrar contexto específico
        de cada tipo de evento sem alterar o schema.
        """
        evento = Event(
            tipo=tipo,
            lead_id=lead_id,
            conversation_id=conversation_id,
            detalhes=detalhes,
        )
        agora = datetime.now()
        evento.created_at = agora

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (tipo, lead_id, conversation_id,
                                    detalhes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(tipo),
                    lead_id,
                    conversation_id,
                    json.dumps(detalhes, ensure_ascii=False, default=str),
                    agora.isoformat(),
                ),
            )
            evento.id = cursor.lastrowid

        return evento

    def listar_eventos(
        self,
        *,
        lead_id: int | None = None,
        tipo: EventType | None = None,
        limite: int = 100,
    ) -> list[Event]:
        clausulas: list[str] = []
        params: list[object] = []

        if lead_id is not None:
            clausulas.append("lead_id = ?")
            params.append(lead_id)
        if tipo is not None:
            clausulas.append("tipo = ?")
            params.append(str(tipo))

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?", params
            ).fetchall()

        return [
            Event(
                id=r["id"],
                tipo=EventType(r["tipo"]),
                lead_id=r["lead_id"],
                conversation_id=r["conversation_id"],
                detalhes=json.loads(r["detalhes"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def metricas_de_eventos(self) -> dict:
        """Contagem por tipo de evento — base do painel de métricas."""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT tipo, COUNT(*) c FROM events GROUP BY tipo ORDER BY c DESC"
            ).fetchall()
        return {r["tipo"]: r["c"] for r in rows}