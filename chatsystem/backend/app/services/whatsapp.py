"""
WhatsApp Cloud API sender.
Tenant credentials come from the Tenant row (not global settings).
"""
import logging

import httpx

logger = logging.getLogger(__name__)

WA_API_BASE = "https://graph.facebook.com/v20.0"


async def send_text_message(
    phone_id: str,
    token: str,
    to: str,
    text: str,
) -> dict:
    """Send a plain text message. Returns Meta API response dict."""
    url = f"{WA_API_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("WhatsApp send failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


def parse_incoming_message(payload: dict) -> list[dict]:
    """
    Extract message list from Meta webhook payload.
    Returns list of dicts with: phone_number, external_id, content, message_type.
    """
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type", "text")
                content = ""
                if msg_type == "text":
                    content = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    content = msg.get("image", {}).get("caption", "[image]")
                elif msg_type == "audio":
                    content = "[audio]"
                else:
                    content = f"[{msg_type}]"
                messages.append({
                    "phone_number": msg.get("from"),
                    "external_id": msg.get("id"),
                    "content": content,
                    "message_type": msg_type,
                })
    return messages
