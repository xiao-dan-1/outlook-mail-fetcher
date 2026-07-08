from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.error
import urllib.parse
import urllib.request

from .accounts import Account


TOKEN_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
DEFAULT_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"


class OAuthError(RuntimeError):
    """Raised when Microsoft OAuth token refresh fails."""


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    expires_in: int | None = None
    scope: str | None = None
    token_type: str | None = None


def refresh_access_token(
    account: Account,
    *,
    endpoint: str = TOKEN_ENDPOINT,
    scope: str = DEFAULT_SCOPE,
    timeout: int = 30,
) -> OAuthToken:
    payload = urllib.parse.urlencode(
        {
            "client_id": account.client_id,
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
            "scope": scope,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"token refresh failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"token refresh network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OAuthError("token refresh returned invalid JSON") from exc

    access_token = data.get("access_token")
    if not access_token:
        raise OAuthError(f"token refresh response did not contain access_token: {data}")

    return OAuthToken(
        access_token=access_token,
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
        token_type=data.get("token_type"),
    )
