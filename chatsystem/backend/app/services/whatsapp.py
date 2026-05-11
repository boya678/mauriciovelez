"""
WhatsApp Cloud API sender.
Tenant credentials come from the Tenant row (not global settings).
"""
import base64
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


async def send_template_message(
    phone_id: str,
    token: str,
    to: str,
    template_name: str,
    language: str = "es",
) -> dict:
    """Send a WhatsApp template message (no variables). Returns Meta API response dict."""
    url = f"{WA_API_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("WhatsApp template send failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


async def send_interactive_message(
    phone_id: str,
    token: str,
    to: str,
    interactive: dict,
) -> dict:
    """
    Send a WhatsApp interactive message (buttons or list).

    `interactive` must be a valid Meta interactive object, e.g.:
      {"type": "button", "body": {...}, "action": {...}}
      {"type": "list",   "body": {...}, "action": {...}}
    """
    url = f"{WA_API_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("WhatsApp interactive send failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


async def download_media(media_id: str, token: str) -> tuple[bytes, str]:
    """
    Download a WhatsApp media file.

    Returns (raw_bytes, mime_type).
    Raises httpx.HTTPError on failure.
    """
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: resolve media URL
        meta_resp = await client.get(
            f"{WA_API_BASE}/{media_id}",
            headers=headers,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        media_url = meta["url"]
        mime_type: str = meta.get("mime_type", "application/octet-stream")

        # Step 2: download actual file
        dl_resp = await client.get(media_url, headers=headers)
        dl_resp.raise_for_status()

    return dl_resp.content, mime_type


def parse_incoming_message(payload: dict) -> list[dict]:
    """
    Extract message list from Meta webhook payload.
    Returns list of dicts with: phone_number, external_id, content,
    message_type, and optionally media_id (for image/video/document/audio).
    """
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type", "text")
                content = ""
                media_id = None

                if msg_type == "text":
                    content = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    img = msg.get("image", {})
                    content = img.get("caption", "") or "[imagen]"
                    media_id = img.get("id")
                elif msg_type == "audio":
                    media_id = msg.get("audio", {}).get("id")
                    content = "[audio]"
                elif msg_type == "video":
                    vid = msg.get("video", {})
                    content = vid.get("caption", "") or "[video]"
                    media_id = vid.get("id")
                elif msg_type == "document":
                    doc = msg.get("document", {})
                    content = doc.get("filename", "") or "[documento]"
                    media_id = doc.get("id")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    btn = interactive.get("button_reply") or interactive.get("list_reply")
                    if btn:
                        content = btn.get("id", "")
                    else:
                        content = f"[{msg_type}]"
                else:
                    content = f"[{msg_type}]"

                entry_data: dict = {
                    "phone_number": msg.get("from"),
                    "external_id": msg.get("id"),
                    "content": content,
                    "message_type": msg_type,
                }
                if media_id:
                    entry_data["media_id"] = media_id
                messages.append(entry_data)
    return messages

