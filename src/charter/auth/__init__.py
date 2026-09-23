# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Authentication — the whole of it, and nothing else.

Everything about proving who a call is made as lives here: the credential seam
the runtime pulls tokens through, and the OAuth 2.0 declarations that renew them.
Nothing here builds a tool or shapes a request; for that, see :mod:`charter`.

Two modules, one import path. :mod:`charter.auth.credentials` is the seam —
``CredentialProvider`` and the four implementations that cover a token you
already hold, plus ``SubjectProvider`` for putting any of them behind an
end-user identity. :mod:`charter.auth.oauth` is the protocol — ``OAuth2Server``
declares a token endpoint, ``OAuth2Client`` refreshes against it, and
``OAuth2Flow`` covers the two steps of obtaining a grant in the first place. The
split is where the code lives, not what you import: import from
``charter.auth``.

    from charter.auth import EnvTokenProvider
    from charter.packs import gmail

    gmail.configure(credential_provider=EnvTokenProvider("GMAIL_TOKEN"))

Charter never acquires, stores, or re-acquires credentials on its own. It reads
what the host hands it, refreshes a grant the host already holds, and raises
:class:`~charter.types.errors.CredentialError` when that is not enough — which
is why the error stays in the root namespace with the rest of the hierarchy,
where ``except CharterError`` catches it alongside everything else.
"""

from charter.auth.credentials import (
    CallbackProvider,
    CredentialProvider,
    Credentials,
    EnvTokenProvider,
    StaticTokenProvider,
    SubjectProvider,
    current_subject,
    use_subject,
)
from charter.auth.oauth import (
    AuthorizationRequest,
    Grant,
    OAuth2Client,
    OAuth2Flow,
    OAuth2Server,
    OnRefresh,
    TokenEndpointAuthMethod,
    TokenGrant,
    scopes_for,
    states_match,
)

# The public auth surface. It is not re-exported from `charter` — one name, one
# import path, so a pack generated from the skill file and a pack written by hand
# read the same. `charter.auth.credentials` and `charter.auth.oauth` are where
# the code lives; import from them and expect them to move.
__all__ = [
    # credentials — a token you already hold
    "Credentials",
    "CredentialProvider",
    "StaticTokenProvider",
    "EnvTokenProvider",
    "CallbackProvider",
    # many end users, one set of tools
    "SubjectProvider",
    "current_subject",
    "use_subject",
    # OAuth 2.0, declared — no vendor SDK
    "OAuth2Server",
    "OAuth2Client",
    # getting the grant — the two protocol steps; the host owns everything between
    "OAuth2Flow",
    "AuthorizationRequest",
    "TokenGrant",
    "states_match",
    "scopes_for",
    # the types those signatures are declared in — a host writing its own
    # wrapper has to name them
    "Grant",
    "TokenEndpointAuthMethod",
    "OnRefresh",
]
