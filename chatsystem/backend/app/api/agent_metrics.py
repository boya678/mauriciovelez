from datetime import date, datetime, time, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant import TenantContext, get_tenant_db, require_admin, resolve_tenant

router = APIRouter(prefix="/agent-metrics", tags=["agent-metrics"])


class AgentMetricRow(BaseModel):
    agent_id: uuid.UUID
    name: str
    email: str
    status: str
    active: bool
    assigned_conversations: int
    handled_conversations: int
    closed_conversations: int
    active_conversations: int
    released_conversations: int
    human_messages: int
    unread_messages: int
    avg_first_response_seconds: float | None
    avg_response_seconds: float | None
    avg_resolution_seconds: float | None
    first_response_samples: int
    response_samples: int
    resolution_samples: int


class DailyMetricRow(BaseModel):
    day: date
    assigned_conversations: int
    closed_conversations: int
    human_messages: int


class AgentMetricsResponse(BaseModel):
    from_date: date
    to_date: date
    agents: list[AgentMetricRow]
    daily: list[DailyMetricRow]


@router.get("", response_model=AgentMetricsResponse)
async def get_agent_metrics(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    agent_id: uuid.UUID | None = Query(default=None),
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _admin=Depends(require_admin),
) -> AgentMetricsResponse:
    today = datetime.now(timezone.utc).date()
    selected_to = to_date or today
    selected_from = from_date or (selected_to - timedelta(days=29))
    if selected_from > selected_to:
        raise HTTPException(status_code=422, detail="La fecha inicial debe ser anterior a la final.")
    if (selected_to - selected_from).days > 365:
        raise HTTPException(status_code=422, detail="El rango máximo es de 366 días.")

    start_at = datetime.combine(selected_from, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(selected_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    schema = tenant.schema
    params = {
        "tenant_id": tenant.id,
        "agent_id": agent_id,
        "start_at": start_at,
        "end_at": end_at,
        "from_date": selected_from,
        "to_date": selected_to,
    }

    rows = (await db.execute(text(f"""
        WITH filtered_agents AS (
            SELECT id, name, email, status, active
            FROM {schema}.agents
            WHERE tenant_id = :tenant_id
              AND (CAST(:agent_id AS uuid) IS NULL OR id = CAST(:agent_id AS uuid))
        ),
        assignment_stats AS (
            SELECT a.agent_id,
                COUNT(*) FILTER (WHERE a.assigned_at >= :start_at AND a.assigned_at < :end_at)::int AS assigned_conversations,
                COUNT(*) FILTER (
                    WHERE a.assigned_at >= :start_at AND a.assigned_at < :end_at
                      AND first_response.created_at IS NOT NULL
                )::int AS handled_conversations,
                COUNT(*) FILTER (
                    WHERE a.released_at >= :start_at AND a.released_at < :end_at
                      AND c.closed_at IS NOT NULL
                      AND ABS(EXTRACT(EPOCH FROM (c.closed_at - a.released_at))) <= 5
                )::int AS closed_conversations,
                                COUNT(*) FILTER (
                                        WHERE a.released_at IS NULL
                                            AND c.status = 'human_active'
                                            AND c.assigned_agent_id = a.agent_id
                                )::int AS active_conversations,
                COUNT(*) FILTER (
                    WHERE a.released_at >= :start_at AND a.released_at < :end_at
                      AND NOT (
                          c.closed_at IS NOT NULL
                          AND ABS(EXTRACT(EPOCH FROM (c.closed_at - a.released_at))) <= 5
                      )
                )::int AS released_conversations,
                AVG(EXTRACT(EPOCH FROM (first_response.created_at - a.assigned_at))) FILTER (
                    WHERE a.assigned_at >= :start_at AND a.assigned_at < :end_at
                      AND first_response.created_at IS NOT NULL
                ) AS avg_first_response_seconds,
                COUNT(first_response.created_at) FILTER (
                    WHERE a.assigned_at >= :start_at AND a.assigned_at < :end_at
                )::int AS first_response_samples,
                AVG(EXTRACT(EPOCH FROM (a.released_at - a.assigned_at))) FILTER (
                    WHERE a.released_at >= :start_at AND a.released_at < :end_at
                      AND c.closed_at IS NOT NULL
                      AND ABS(EXTRACT(EPOCH FROM (c.closed_at - a.released_at))) <= 5
                ) AS avg_resolution_seconds,
                COUNT(*) FILTER (
                    WHERE a.released_at >= :start_at AND a.released_at < :end_at
                      AND c.closed_at IS NOT NULL
                      AND ABS(EXTRACT(EPOCH FROM (c.closed_at - a.released_at))) <= 5
                )::int AS resolution_samples
            FROM {schema}.assignments a
            JOIN filtered_agents fa ON fa.id = a.agent_id
            JOIN {schema}.conversations c ON c.id = a.conversation_id
            LEFT JOIN LATERAL (
                SELECT m.created_at FROM {schema}.messages m
                WHERE m.conversation_id = a.conversation_id
                  AND m.sender_type = 'human'
                  AND m.created_at >= a.assigned_at
                  AND m.created_at <= COALESCE(a.released_at, 'infinity'::timestamptz)
                ORDER BY m.created_at LIMIT 1
            ) first_response ON true
            WHERE a.assigned_at < :end_at
              AND COALESCE(a.released_at, 'infinity'::timestamptz) >= :start_at
            GROUP BY a.agent_id
        ),
        attributed_human AS (
            SELECT attributed.agent_id, m.created_at
            FROM {schema}.messages m
            JOIN LATERAL (
                SELECT a.agent_id FROM {schema}.assignments a
                JOIN filtered_agents fa ON fa.id = a.agent_id
                WHERE a.conversation_id = m.conversation_id
                  AND a.assigned_at <= m.created_at
                  AND m.created_at <= COALESCE(a.released_at, 'infinity'::timestamptz)
                ORDER BY a.assigned_at DESC LIMIT 1
            ) attributed ON true
            WHERE m.sender_type = 'human'
              AND m.created_at >= :start_at AND m.created_at < :end_at
        ),
        human_stats AS (
            SELECT agent_id, COUNT(*)::int AS human_messages
            FROM attributed_human GROUP BY agent_id
        ),
        user_turns AS (
            SELECT m.conversation_id, m.created_at,
                LEAD(m.created_at) OVER (PARTITION BY m.conversation_id ORDER BY m.created_at) AS next_user_at
            FROM {schema}.messages m
            WHERE m.sender_type = 'user'
              AND m.created_at >= :start_at AND m.created_at < :end_at
        ),
        response_times AS (
            SELECT attributed.agent_id,
                EXTRACT(EPOCH FROM (response.created_at - user_turn.created_at)) AS seconds
            FROM user_turns user_turn
            JOIN LATERAL (
                SELECT m.created_at FROM {schema}.messages m
                WHERE m.conversation_id = user_turn.conversation_id
                  AND m.sender_type = 'human'
                  AND m.created_at > user_turn.created_at
                  AND m.created_at < COALESCE(user_turn.next_user_at, 'infinity'::timestamptz)
                  AND m.created_at < :end_at
                ORDER BY m.created_at LIMIT 1
            ) response ON true
            JOIN LATERAL (
                SELECT a.agent_id FROM {schema}.assignments a
                JOIN filtered_agents fa ON fa.id = a.agent_id
                WHERE a.conversation_id = user_turn.conversation_id
                  AND a.assigned_at <= response.created_at
                  AND response.created_at <= COALESCE(a.released_at, 'infinity'::timestamptz)
                ORDER BY a.assigned_at DESC LIMIT 1
            ) attributed ON true
        ),
        response_stats AS (
            SELECT agent_id, AVG(seconds) AS avg_response_seconds, COUNT(*)::int AS response_samples
            FROM response_times GROUP BY agent_id
        ),
        unread_stats AS (
            SELECT a.agent_id, COUNT(m.id)::int AS unread_messages
            FROM {schema}.assignments a
            JOIN filtered_agents fa ON fa.id = a.agent_id
                        JOIN {schema}.conversations c ON c.id = a.conversation_id
                            AND c.status = 'human_active'
                            AND c.assigned_agent_id = a.agent_id
            JOIN {schema}.messages m ON m.conversation_id = a.conversation_id
              AND m.sender_type = 'user'
              AND (a.last_read_at IS NULL OR m.created_at > a.last_read_at)
            WHERE a.released_at IS NULL GROUP BY a.agent_id
        )
        SELECT fa.id AS agent_id, fa.name, fa.email, fa.status, fa.active,
            COALESCE(ast.assigned_conversations, 0) AS assigned_conversations,
            COALESCE(ast.handled_conversations, 0) AS handled_conversations,
            COALESCE(ast.closed_conversations, 0) AS closed_conversations,
            COALESCE(ast.active_conversations, 0) AS active_conversations,
            COALESCE(ast.released_conversations, 0) AS released_conversations,
            COALESCE(hs.human_messages, 0) AS human_messages,
            COALESCE(us.unread_messages, 0) AS unread_messages,
            ast.avg_first_response_seconds, rs.avg_response_seconds, ast.avg_resolution_seconds,
            COALESCE(ast.first_response_samples, 0) AS first_response_samples,
            COALESCE(rs.response_samples, 0) AS response_samples,
            COALESCE(ast.resolution_samples, 0) AS resolution_samples
        FROM filtered_agents fa
        LEFT JOIN assignment_stats ast ON ast.agent_id = fa.id
        LEFT JOIN human_stats hs ON hs.agent_id = fa.id
        LEFT JOIN response_stats rs ON rs.agent_id = fa.id
        LEFT JOIN unread_stats us ON us.agent_id = fa.id
        ORDER BY handled_conversations DESC, fa.name
    """), params)).mappings().all()

    daily_rows = (await db.execute(text(f"""
        WITH days AS (
            SELECT generate_series(CAST(:from_date AS date), CAST(:to_date AS date), interval '1 day')::date AS day
        ),
        filtered_agents AS (
            SELECT id FROM {schema}.agents
            WHERE tenant_id = :tenant_id
              AND (CAST(:agent_id AS uuid) IS NULL OR id = CAST(:agent_id AS uuid))
        ),
        assigned AS (
            SELECT a.assigned_at::date AS day, COUNT(*)::int AS total
            FROM {schema}.assignments a JOIN filtered_agents fa ON fa.id = a.agent_id
            WHERE a.assigned_at >= :start_at AND a.assigned_at < :end_at
            GROUP BY a.assigned_at::date
        ),
        closed AS (
            SELECT a.released_at::date AS day, COUNT(*)::int AS total
            FROM {schema}.assignments a
            JOIN filtered_agents fa ON fa.id = a.agent_id
            JOIN {schema}.conversations c ON c.id = a.conversation_id
            WHERE a.released_at >= :start_at AND a.released_at < :end_at
              AND c.closed_at IS NOT NULL
              AND ABS(EXTRACT(EPOCH FROM (c.closed_at - a.released_at))) <= 5
            GROUP BY a.released_at::date
        ),
        human_messages AS (
            SELECT m.created_at::date AS day, COUNT(*)::int AS total
            FROM {schema}.messages m
            JOIN LATERAL (
                SELECT a.agent_id FROM {schema}.assignments a
                JOIN filtered_agents fa ON fa.id = a.agent_id
                WHERE a.conversation_id = m.conversation_id
                  AND a.assigned_at <= m.created_at
                  AND m.created_at <= COALESCE(a.released_at, 'infinity'::timestamptz)
                ORDER BY a.assigned_at DESC LIMIT 1
            ) attributed ON true
            WHERE m.sender_type = 'human'
              AND m.created_at >= :start_at AND m.created_at < :end_at
            GROUP BY m.created_at::date
        )
        SELECT days.day,
            COALESCE(assigned.total, 0) AS assigned_conversations,
            COALESCE(closed.total, 0) AS closed_conversations,
            COALESCE(human_messages.total, 0) AS human_messages
        FROM days
        LEFT JOIN assigned USING (day)
        LEFT JOIN closed USING (day)
        LEFT JOIN human_messages USING (day)
        ORDER BY days.day
    """), params)).mappings().all()

    return AgentMetricsResponse(
        from_date=selected_from,
        to_date=selected_to,
        agents=[AgentMetricRow.model_validate(row) for row in rows],
        daily=[DailyMetricRow.model_validate(row) for row in daily_rows],
    )
