"""
WhatsApp Cloud API sender.
Tenant credentials come from the Tenant row (not global settings).
"""
import base64
import logging

import httpx

logger = logging.getLogger(__name__)

WA_API_BASE = "https://graph.facebook.com/v20.0"


def _to_field(phone_or_bsuid: str) -> dict:
    """Return {"to": ...} for phone numbers or {"recipient": ...} for BSUIDs.

    A BSUID has the form <COUNTRY_CODE>.<alphanumeric>, e.g. "CO.1949266959121697".
    Regular phone numbers contain only digits (and optionally a leading '+').
    The dot is the distinguishing character.
    """
    if "." in phone_or_bsuid:
        return {"recipient": phone_or_bsuid}
    return {"to": phone_or_bsuid}


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
        **_to_field(to),
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
        **_to_field(to),
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
        **_to_field(to),
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


async def send_request_contact_info(
    phone_id: str,
    token: str,
    to: str,
    body_text: str = "Para brindarte un mejor servicio, necesitamos tu número de teléfono. Por favor compártelo tocando el botón.",
) -> dict:
    """Send a REQUEST_CONTACT_INFO interactive message (pedir_contacto utility).

    `to` can be a phone number or a BSUID — _to_field() handles both.
    When the user taps the button, Meta sends a 'contacts' webhook with their
    real phone number.
    """
    url = f"{WA_API_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        **_to_field(to),
        "type": "interactive",
        "interactive": {
            "type": "request_contact_info",
            "body": {"text": body_text},
            "action": {"name": "request_contact_info"},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("pedir_contacto send failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


async def upload_media(
    phone_id: str,
    token: str,
    media_bytes: bytes,
    mime_type: str,
    filename: str,
) -> str:
    """Upload media to WhatsApp Cloud API and return media id."""
    url = f"{WA_API_BASE}/{phone_id}/media"
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "messaging_product": (None, "whatsapp"),
        "file": (filename, media_bytes, mime_type),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, files=files)
    if resp.status_code >= 400:
        logger.error("WhatsApp media upload failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    media_id = data.get("id")
    if not media_id:
        raise RuntimeError("Meta did not return media id")
    return media_id


async def send_image_message(
    phone_id: str,
    token: str,
    to: str,
    media_id: str,
    caption: str | None = None,
) -> dict:
    """Send an image message referencing a previously uploaded media id."""
    url = f"{WA_API_BASE}/{phone_id}/messages"
    image_obj: dict = {"id": media_id}
    if caption:
        image_obj["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        **_to_field(to),
        "type": "image",
        "image": image_obj,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("WhatsApp image send failed %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()


async def send_audio_message(
    phone_id: str,
    token: str,
    to: str,
    media_id: str,
) -> dict:
    """Send an audio message referencing a previously uploaded media id."""
    url = f"{WA_API_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        **_to_field(to),
        "type": "audio",
        "audio": {"id": media_id},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if resp.status_code >= 400:
        logger.error("WhatsApp audio send failed %s: %s", resp.status_code, resp.text)
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
                elif msg_type == "sticker":
                    sticker = msg.get("sticker", {})
                    content = "[sticker]"
                    media_id = sticker.get("id")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    btn = interactive.get("button_reply") or interactive.get("list_reply")
                    if btn:
                        content = btn.get("id", "")
                    else:
                        content = f"[{msg_type}]"
                elif msg_type == "button":
                    # Template quick-reply button. Meta sends:
                    #   { "type": "button", "button": { "text": "Sí", "payload": "..." } }
                    btn = msg.get("button", {})
                    content = btn.get("text") or btn.get("payload") or "[button]"
                    msg_type = "text"
                else:
                    content = f"[{msg_type}]"

                # Sender identification: prefer phone number ("from"),
                # fall back to BSUID ("from_user_id") when user hides their number.
                phone_from = msg.get("from")
                bsuid = msg.get("from_user_id", "")
                sender_id = phone_from or bsuid or ""

                # Resolve username from the contacts array in this change block
                contacts_map: dict[str, str] = {
                    c.get("user_id", ""): c.get("profile", {}).get("username", "")
                    for c in value.get("contacts", [])
                    if c.get("user_id")
                }
                username = contacts_map.get(bsuid, "") if bsuid else ""

                # Handle contacts message type (user shared phone via pedir_contacto)
                if msg_type == "contacts":
                    shared = msg.get("contacts", [])
                    real_phone = ""
                    for sc in shared:
                        phones = sc.get("phones", [])
                        if phones:
                            real_phone = phones[0].get("wa_id") or phones[0].get("phone", "")
                            if real_phone:
                                break
                    entry_data: dict = {
                        "phone_number": sender_id,
                        "bsuid": bsuid,
                        "external_id": msg.get("id"),
                        "content": f"[contacto_compartido:{real_phone}]" if real_phone else "[contacto_compartido]",
                        "message_type": "contacts",
                        "real_phone": real_phone,
                    }
                    if username:
                        entry_data["username"] = username
                    messages.append(entry_data)
                    continue

                entry_data = {
                    "phone_number": sender_id,
                    "bsuid": bsuid,
                    "external_id": msg.get("id"),
                    "content": content,
                    "message_type": msg_type,
                }
                if username:
                    entry_data["username"] = username
                if media_id:
                    entry_data["media_id"] = media_id
                messages.append(entry_data)
    return messages

