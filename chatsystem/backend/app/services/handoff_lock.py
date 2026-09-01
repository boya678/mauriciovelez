"""Distributed lock shared by manual and automatic human handoff paths."""
import uuid

HANDOFF_FLOW_LOCK_SECONDS = 60
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _lock_key(conversation_id: uuid.UUID) -> str:
    return f"handoff_flow:{conversation_id}"


async def acquire_handoff_lock(redis, conversation_id: uuid.UUID) -> str | None:
    token = str(uuid.uuid4())
    acquired = await redis.set(
        _lock_key(conversation_id),
        token,
        nx=True,
        ex=HANDOFF_FLOW_LOCK_SECONDS,
    )
    return token if acquired else None


async def release_handoff_lock(
    redis,
    conversation_id: uuid.UUID,
    token: str,
) -> None:
    await redis.eval(
        _RELEASE_LOCK_SCRIPT,
        1,
        _lock_key(conversation_id),
        token,
    )
