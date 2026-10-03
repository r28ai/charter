# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The renewing credential the Shopify pack falls back to.

An app made in Shopify's Dev Dashboard has no refresh token: its client ID and
secret are the grant. Shopify's client credentials grant trades them for an
Admin API token that lasts 24 hours, and trades them again when that one runs
out. So ``$SHOPIFY_CLIENT_ID`` and ``$SHOPIFY_CLIENT_SECRET``, beside
``$SHOPIFY_SHOP``, keep a process working indefinitely — an MCP server a client
starts once and keeps — where a minted ``$SHOPIFY_ACCESS_TOKEN`` stops working
the next day. The pair wins over that variable when both are set, as a Google
grant wins over ``$GOOGLE_ACCESS_TOKEN``: it can always produce a valid token,
and a raw one left in the environment usually cannot.

**Your own stores only.** Shopify grants this only when the app and the store
belong to the same organisation. An app installed on a merchant's store goes
through Shopify's authorization code flow instead and holds a token per store,
and keeping those is the host application's job.
https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/client-credentials-grant

The token endpoint is on the store's own host, so it is not a constant: it is
worked out from the configured store when a token is needed, and a different
store gets a different client rather than a token minted for the last one.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Tuple

from charter.auth import CredentialProvider, Credentials, OAuth2Client, OAuth2Server
from charter.auth.credentials import invalidate
from charter.types.errors import CredentialError

__all__ = ["ShopifyClientCredentials", "ShopifyEnvGrant", "token_server"]

CLIENT_ID = "SHOPIFY_CLIENT_ID"
CLIENT_SECRET = "SHOPIFY_CLIENT_SECRET"

_DOCS = "packs/shopify"


def token_server(store_url: str) -> OAuth2Server:
    """The authorization server for one store: its own ``/admin/oauth/access_token``.

    ``store_url`` is the store's base URL, ``https://my-store.myshopify.com/``.
    Shopify takes the client credentials as form fields, which is
    ``client_secret_post``.
    """
    return OAuth2Server(token_endpoint=f"{store_url.rstrip('/')}/admin/oauth/access_token")


class ShopifyClientCredentials:
    """A :class:`~charter.auth.CredentialProvider` for the client credentials grant.

    Wraps one :class:`~charter.auth.OAuth2Client` per store, which caches the
    token and renews it shortly before its 24 hours are up. ``store_url`` is
    called on every request, so it follows the pack's ``configure(shop=...)``.
    """

    def __init__(self, store_url: Callable[[], str], client_id: str, client_secret: str) -> None:
        if not client_id or not client_secret:
            raise CredentialError(
                "Shopify's client credentials grant needs both the client ID and the "
                "client secret.",
                provider="shopify",
                docs=_DOCS,
            )
        self._store_url = store_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._client: Optional[OAuth2Client] = None
        self._store: Optional[str] = None

    async def get_credentials(self, provider: str) -> Credentials:
        store = self._store_url()
        if self._client is None or store != self._store:
            self._client = OAuth2Client(
                token_server(store),
                client_id=self._client_id,
                client_secret=self._client_secret,
                grant="client_credentials",
            )
            self._store = store
        return await self._client.get_credentials(provider)

    def invalidate(self, credentials: Credentials) -> None:
        """Pass a rejection on to the client for the current store."""
        if self._client is not None:
            invalidate(self._client, credentials)

    def __repr__(self) -> str:
        return f"ShopifyClientCredentials(store={self._store!r}, client_secret=***)"


class ShopifyEnvGrant:
    """``$SHOPIFY_CLIENT_ID`` and ``$SHOPIFY_CLIENT_SECRET``, as a credential provider."""

    variables = f"${CLIENT_ID} with ${CLIENT_SECRET}"

    def __init__(self, store_url: Callable[[], str]) -> None:
        self._store_url = store_url
        self._provider: Optional[ShopifyClientCredentials] = None
        self._pair: Optional[Tuple[str, str]] = None

    def is_set(self) -> bool:
        return bool(os.environ.get(CLIENT_ID) or os.environ.get(CLIENT_SECRET))

    def provider(self) -> CredentialProvider:
        """The provider for the pair the environment holds now.

        Only called when :meth:`is_set` is true. Half a pair raises rather than
        falling through to ``$SHOPIFY_ACCESS_TOKEN``, because that is a
        configuration someone meant and got wrong.
        """
        missing = [name for name in (CLIENT_ID, CLIENT_SECRET) if not os.environ.get(name)]
        if missing:
            present = CLIENT_SECRET if missing == [CLIENT_ID] else CLIENT_ID
            raise CredentialError(
                f"${present} is set but ${missing[0]} is not. Shopify's client "
                "credentials grant needs both.",
                provider="shopify",
                docs=_DOCS,
            )
        pair = (os.environ[CLIENT_ID], os.environ[CLIENT_SECRET])
        if self._provider is None or pair != self._pair:
            self._provider = ShopifyClientCredentials(self._store_url, *pair)
            self._pair = pair
        return self._provider

    def reset(self) -> None:
        """Drop the cached provider, so the next call builds one from scratch."""
        self._provider = None
        self._pair = None
