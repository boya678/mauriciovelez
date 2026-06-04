import httpx

from app.core.config import settings


def _extension_for_mime(mime_type: str) -> str:
    m = (mime_type or "").lower()
    if "ogg" in m:
        return "ogg"
    if "webm" in m:
        return "webm"
    if "mpeg" in m or "mp3" in m:
        return "mp3"
    if "mp4" in m:
        return "mp4"
    if "wav" in m:
        return "wav"
    return "bin"


async def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str) -> str:
    """Transcribe audio bytes using Azure OpenAI audio transcription deployment.

    Returns stripped transcript text. Raises httpx.HTTPError/RuntimeError on failure.
    """
    if not settings.AZURE_OPENAI_VOICE_DEPLOYMENT:
        raise RuntimeError("AZURE_OPENAI_VOICE_DEPLOYMENT is not configured")

    endpoint = (
        settings.AZURE_OPENAI_ENDPOINT_VOICE
        or settings.AZURE_OPENAI_ENDPOINT
    ).rstrip("/")
    api_key = settings.AZURE_OPENAI_API_KEY_VOICE or settings.AZURE_OPENAI_API_KEY
    url = (
        f"{endpoint}/openai/deployments/{settings.AZURE_OPENAI_VOICE_DEPLOYMENT}"
        f"/audio/transcriptions?api-version={settings.AZURE_OPENAI_API_VERSION}"
    )

    ext = _extension_for_mime(mime_type)
    filename = f"audio.{ext}"

    headers = {"api-key": api_key}
    files = {
        "file": (filename, audio_bytes, mime_type or "application/octet-stream"),
        "response_format": (None, "json"),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, files=files)

    resp.raise_for_status()
    data = resp.json()
    text = (data.get("text") or "").strip()
    if not text:
        raise RuntimeError("Empty transcript returned by Azure OpenAI")
    return text
