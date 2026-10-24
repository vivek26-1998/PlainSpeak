"""Reson8 short-lived token issuance. The permanent API key never leaves the backend."""

import httpx

RESON8_TOKEN_URL = "https://api.reson8.dev/v1/auth/token"  # noqa: S105 - URL, not a secret
RESON8_TURNS_URL = "wss://api.reson8.dev/v1/speech-to-text/turns"
RESON8_REALTIME_URL = "wss://api.reson8.dev/v1/speech-to-text/realtime"


class VoiceError(RuntimeError):
    pass


def request_token(api_key: str) -> dict[str, object]:
    if not api_key:
        raise VoiceError("RESON8_API_KEY is not configured.")
    try:
        response = httpx.post(
            RESON8_TOKEN_URL, headers={"Authorization": f"ApiKey {api_key}"}, timeout=10
        )
    except httpx.HTTPError as e:
        raise VoiceError("Could not reach Reson8.") from e
    if response.status_code != 200:
        raise VoiceError(f"Reson8 token request failed ({response.status_code}).")
    body = response.json()
    return {
        "accessToken": body["access_token"],
        "expiresIn": body.get("expires_in", 600),
        "turnsUrl": RESON8_TURNS_URL,
        "realtimeUrl": RESON8_REALTIME_URL,
    }
