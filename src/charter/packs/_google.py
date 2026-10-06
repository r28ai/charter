# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The refreshing credential the six Google packs fall back to.

``$GOOGLE_ACCESS_TOKEN`` lasts about an hour and cannot be renewed, which is
the right trade for a script and the wrong one for anything left running — an
MCP server, say, that a client starts once and keeps. A grant can be renewed,
so the packs also look for one in the environment, in either of two shapes:

- ``$GOOGLE_TOKEN_FILE``, the path of an authorized-user JSON file. That is the
  file google-auth's ``Credentials.to_json()`` writes (``token.json`` in
  Google's quickstarts, ``google_token.json`` in Hermes Agent) and the one
  ``gcloud auth application-default login`` writes. Only ``client_id``,
  ``client_secret`` and ``refresh_token`` are read from it.
- ``$GOOGLE_REFRESH_TOKEN`` with ``$GOOGLE_CLIENT_ID`` and
  ``$GOOGLE_CLIENT_SECRET`` — the three values the own-account guide ends with.

Either one wins over ``$GOOGLE_ACCESS_TOKEN``: a grant can always produce a
valid token, and a raw one left in the environment usually cannot.

One :class:`~charter.auth.OAuth2Client` serves all six packs, so a session that
reads mail and then files a calendar event spends one refresh, not two. The
file is read on every call, and a different grant in it builds a new client, so
re-authorizing does not need a restart.

**One account per process.** This is the shape the MCP spec prescribes for a
stdio server — credentials from the environment — and it is one person's
grant. A process serving several users needs a grant per user, which is
:class:`~charter.auth.SubjectProvider` over your own store; set these variables
on a shared server and every user acts as this one account.

The file holds a refresh token, so it should be readable by its owner alone
(``chmod 600``). Charter never changes its permissions; like ``kubectl`` with a
group-readable kubeconfig, it warns once when other users can read it.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, Set, Tuple

from charter.auth import CredentialProvider, OAuth2Client, OAuth2Server, Revocation
from charter.types.errors import CredentialError

__all__ = ["GOOGLE", "GoogleEnvGrant", "ENV_GRANT"]

# Equal to the canonical copy in docs/auth/providers/google.mdx;
# tests/test_docs_oauth.py holds them together.
GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
    revocation=Revocation("https://oauth2.googleapis.com/revoke", auth_method="none"),
)

TOKEN_FILE = "GOOGLE_TOKEN_FILE"
REFRESH_TOKEN = "GOOGLE_REFRESH_TOKEN"
CLIENT_ID = "GOOGLE_CLIENT_ID"
CLIENT_SECRET = "GOOGLE_CLIENT_SECRET"

_DOCS = "auth/setup/google"

logger = logging.getLogger("charter")

# Paths already warned about in this process, so a file read on every call
# warns once rather than once per tool call.
_warned: Set[str] = set()

_Grant = Tuple[str, str, str]


class GoogleEnvGrant:
    """A Google grant read from the environment, as a credential provider."""

    variables = f"${TOKEN_FILE}, or ${REFRESH_TOKEN} with ${CLIENT_ID} and ${CLIENT_SECRET}"

    def __init__(self) -> None:
        self._client: Optional[OAuth2Client] = None
        self._grant: Optional[_Grant] = None

    def is_set(self) -> bool:
        return bool(os.environ.get(TOKEN_FILE) or os.environ.get(REFRESH_TOKEN))

    def provider(self) -> CredentialProvider:
        """The client for the grant the environment names now.

        Only called when :meth:`is_set` is true. A grant that is named but
        unusable — a file that is missing, or a refresh token without its
        client — raises rather than falling through to ``$GOOGLE_ACCESS_TOKEN``,
        because that is a configuration someone meant and got wrong.
        """
        grant = _grant_from_environment()
        if self._client is None or grant != self._grant:
            client_id, client_secret, refresh_token = grant
            self._client = OAuth2Client(
                GOOGLE,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
            self._grant = grant
        return self._client

    def reset(self) -> None:
        """Drop the cached client, so the next call builds one from scratch."""
        self._client = None
        self._grant = None
        _warned.clear()


ENV_GRANT = GoogleEnvGrant()


def _grant_from_environment() -> _Grant:
    path = os.environ.get(TOKEN_FILE)
    if path:
        return _grant_from_file(path)

    refresh_token = os.environ.get(REFRESH_TOKEN, "")
    missing = [name for name in (CLIENT_ID, CLIENT_SECRET) if not os.environ.get(name)]
    if missing:
        raise CredentialError(
            f"${REFRESH_TOKEN} is set but {' and '.join('$' + m for m in missing)} "
            "is not. A refresh token is only accepted together with the client id "
            "and secret it was issued to.",
            provider="google",
            docs=_DOCS,
        )
    return os.environ[CLIENT_ID], os.environ[CLIENT_SECRET], refresh_token


def _grant_from_file(value: str) -> _Grant:
    path = Path(value).expanduser()
    where = f"${TOKEN_FILE} points at {path}"
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise CredentialError(
            f"{where}, which cannot be read: {exc.strerror or exc}", provider="google", docs=_DOCS
        ) from None
    except ValueError:
        raise CredentialError(
            f"{where}, which is not JSON.", provider="google", docs=_DOCS
        ) from None
    if not isinstance(data, dict):
        raise CredentialError(
            f"{where}, which is not a JSON object.", provider="google", docs=_DOCS
        )

    # The two files people point at by mistake, named for what they are.
    if "installed" in data or "web" in data:
        raise CredentialError(
            f"{where}, which is an OAuth client file — the client id and secret — "
            "not a user's token. Run the consent flow once to get a refresh token, "
            "then point at the file that holds it.",
            provider="google",
            docs=_DOCS,
        )
    if data.get("type") == "service_account":
        raise CredentialError(
            f"{where}, which is a service account key. The Google packs act as a "
            "user, so they need that user's grant: an authorized-user file.",
            provider="google",
            docs=_DOCS,
        )

    missing = [key for key in ("client_id", "client_secret", "refresh_token") if not data.get(key)]
    if missing:
        raise CredentialError(
            f"{where}, which has no {', '.join(missing)}. Expected an authorized-user "
            "file: the token.json google-auth writes, Hermes Agent's google_token.json, "
            "or gcloud's application_default_credentials.json.",
            provider="google",
            docs=_DOCS,
        )
    _warn_if_others_can_read(path)
    return str(data["client_id"]), str(data["client_secret"]), str(data["refresh_token"])


def _warn_if_others_can_read(path: Path) -> None:
    """Warn, once, when users other than the owner can reach the file.

    A warning and not a refusal: the file belongs to the user and was written by
    another tool — Google's quickstart and Hermes Agent both leave it at the
    default umask — so refusing would break a working setup over a fix that is
    one command. POSIX only; Windows does not carry these bits.
    """
    if os.name != "posix":
        return
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077 and str(path) not in _warned:
        _warned.add(str(path))
        logger.warning(
            "%s holds a refresh token and other users on this machine can read it "
            "(mode %03o). Restrict it to its owner: chmod 600 %s",
            path,
            mode,
            path,
        )
