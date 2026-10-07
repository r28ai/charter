# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Disconnecting a Stripe App's user: uninstalling the app from their account.

Stripe has no endpoint that revokes a Stripe App's token. A grant is an
install, and it ends when the install does: Stripe's App Installs API finds
the install for an app on an account, and uninstalls it. Both requests carry
the developer's secret key and no token, and neither fits a declared
:class:`~charter.auth.Revocation`, so this is a :class:`~charter.auth.Revoker`.

Connect's ``oauth/deauthorize`` looks like the answer and is not. Measured on
2026-10-06, it ended the app's access but left the app installed, and the
install link then answered "already installed" and issued tokens Stripe
refused, until the user uninstalled the app from their Dashboard.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any, ClassVar, Dict

import httpx

from charter.auth import GrantToRevoke
from charter.types.errors import CredentialError, DeclarationError

__all__ = ["StripeAppUninstall"]

INSTALLS_URL = "https://api.stripe.com/v1/apps/installs"

# The version the App Installs API was measured on. The account default that
# predates it lists no installs on other accounts and names fields differently.
INSTALLS_API_VERSION = "2026-09-30.endive"
_VERSION = {"Stripe-Version": INSTALLS_API_VERSION}

_DOCS = "auth/your-users#disconnecting-a-user"

# How often the opt-in wait asks whether the install is gone.
_POLL_SECONDS = 2.0

logger = logging.getLogger("charter")


@dataclass(frozen=True)
class StripeAppUninstall:
    """End a Stripe App's grant by uninstalling the app from the user's account.

    Declared on ``STRIPE_APPS`` as ``revocation=StripeAppUninstall(app="app_...")``,
    so :meth:`OAuth2Client.revoke <charter.auth.OAuth2Client.revoke>` and
    :meth:`SubjectProvider.revoke <charter.auth.SubjectProvider.revoke>`
    disconnect a Stripe user as they do any other.

    ``app`` is the app's ID, ``app_...``, from its page in the Dashboard; the
    Installs API refuses the manifest's ID. The account is the
    ``stripe_user_id`` Stripe's token response carries, which a client keeps
    from the exchange or any refresh.

    The install is looked up as the developer, filtered by app and account,
    because that lookup tells the cases apart, as measured: an account without
    the app comes back empty, which is ``False``, already gone; another
    account's key or a wrong app ID gets a ``400`` and a bad key a ``401``,
    which raise. The same lookup made as the account (``Stripe-Account``)
    answers ``403 account_invalid`` both to an account without the app and to
    another account's key, so it is not used to decide.

    ``revoke`` returns once Stripe accepts the uninstall, ``status:
    uninstalling``. Stripe finishes it seconds later (measured, 10 to 15) and
    sends ``apps.install.deleted``; until then the old access token still
    works, though the client has already stopped using it. ``wait_seconds``
    makes it wait for the install to be gone, for a script or a test that must
    not go on before. It waits holding the client's refresh lock, so another
    process refreshing this user waits too: a production disconnect returns at
    once and confirms by the event instead. Still uninstalling at the deadline
    is logged and still ``True``: the uninstall was accepted, and Stripe
    completes it.
    """

    app: str
    wait_seconds: float = 0
    grant_fields: ClassVar[tuple[str, ...]] = ("stripe_user_id",)

    def __post_init__(self) -> None:
        if not isinstance(self.app, str) or not self.app.startswith("app_"):
            raise DeclarationError(
                "StripeAppUninstall needs the app's ID, app_..., from its page in the "
                f"Dashboard; the manifest's ID is not accepted. Got {self.app!r}.",
                docs=_DOCS,
            )
        wait = self.wait_seconds
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or wait < 0:
            raise DeclarationError(
                f"wait_seconds must be a number of seconds, 0 or more, got {wait!r}",
                docs=_DOCS,
            )

    async def revoke(self, grant: GrantToRevoke) -> bool:
        account = grant.fields["stripe_user_id"]
        found = await grant.send(
            "GET",
            INSTALLS_URL,
            doing=f"Looking up {self.app} on {account}",
            auth_method="secret_key_basic",
            provider="stripe",
            headers=_VERSION,
            params={"app": self.app, "account": account},
        )
        # One install of an app per account and mode: Stripe has a test version
        # uninstalled before the published one goes on, and the other way round.
        listed = _json_object(found, f"Looking up {self.app} on {account}").get("data")
        if not isinstance(listed, list):
            raise CredentialError(
                f"Looking up {self.app} on {account}: Stripe answered without a list of installs.",
                provider="stripe",
                token_refused=False,
                docs=_DOCS,
            )
        install = next(
            (
                i
                for i in listed
                if isinstance(i, dict)
                and i.get("account") == account
                and i.get("status") == "installed"
            ),
            None,
        )
        if install is None:
            return False
        # As Stripe's reference sends it: the developer's key, acting on the
        # account that installed the app.
        await grant.send(
            "POST",
            f"{INSTALLS_URL}/{install['id']}/uninstall",
            doing=f"Uninstalling {self.app} from {account}",
            auth_method="secret_key_basic",
            provider="stripe",
            headers={**_VERSION, "Stripe-Account": account},
        )
        if self.wait_seconds:
            await self._until_gone(install["id"], grant)
        return True

    async def _until_gone(self, install_id: str, grant: GrantToRevoke) -> None:
        """Ask after the install until Stripe no longer has it, or the wait runs out."""
        deadline = monotonic() + self.wait_seconds
        while True:
            # Measured: "uninstalling" for a few seconds, then 404, not found.
            resp = await grant.send(
                "GET",
                f"{INSTALLS_URL}/{install_id}",
                doing=f"Checking {install_id}",
                auth_method="secret_key_basic",
                provider="stripe",
                headers=_VERSION,
                allow=(404,),
            )
            if resp.status_code == 404:
                return
            if _json_object(resp, f"Checking {install_id}").get("status") != "uninstalling":
                return
            if monotonic() >= deadline:
                logger.warning(
                    "charter: Stripe accepted uninstalling %s but had not finished after "
                    "%s seconds; it completes on its own",
                    install_id,
                    self.wait_seconds,
                )
                return
            await asyncio.sleep(_POLL_SECONDS)


def _json_object(resp: httpx.Response, doing: str) -> Dict[str, Any]:
    """Stripe's answer as a JSON object, or the CredentialError a 2xx without one is.

    Read as empty instead, a lookup would find no install and report the grant
    already gone, which is the one wrong answer a disconnect must not give.
    """
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise CredentialError(
            f"{doing}: Stripe answered HTTP {resp.status_code} without a JSON object.",
            provider="stripe",
            token_refused=False,
            docs=_DOCS,
        )
    return body
