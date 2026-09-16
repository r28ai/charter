"""
Shared credential plumbing for the shipped packs.

A pack builds its tools at import time so that ``from charter.packs.gmail import TOOLS``
works before anything is configured — schemas, ``llm_schema()`` and
``to_json_schema()`` are all available without a credential in sight.

Credentials arrive later, through the pack's ``configure()``. The indirection
below is what makes that possible: the tools hold a reference to a
``DeferredCredentialProvider`` (or a mutable header dict) from the start, and
``configure()`` fills it in. Tool identity never changes, so a reference taken
before configuration keeps working after it.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from charter.auth import CredentialProvider, Credentials
from charter.types.errors import CredentialError

__all__ = ["DeferredCredentialProvider", "DeferredApiKeyHeaders"]

_UNSET = "CHARTER_UNCONFIGURED"


class DeferredCredentialProvider:
    """A ``CredentialProvider`` whose real provider is supplied after import."""

    def __init__(self, pack: str, env_var: Optional[str] = None) -> None:
        self._pack = pack
        self._env_var = env_var
        self._provider: Optional[CredentialProvider] = None

    def configure(self, provider: CredentialProvider) -> None:
        self._provider = provider

    @property
    def env_var(self) -> Optional[str]:
        """The environment variable this pack falls back to, for documentation."""
        return self._env_var

    @property
    def is_configured(self) -> bool:
        return self._provider is not None or bool(
            self._env_var and os.environ.get(self._env_var)
        )

    async def get_credentials(self, provider: str) -> Credentials:
        if self._provider is not None:
            return await self._provider.get_credentials(provider)

        # Fall back to the documented environment variable, so a script or the
        # MCP entry point works without writing any configuration code.
        if self._env_var:
            token = os.environ.get(self._env_var)
            if token:
                return Credentials(token=token)

        # The slug is the pack's own page, which is where the three credential
        # shapes for this pack are written out. Two raise sites, twelve packs,
        # one link each: this is the first error a new adopter meets, and the
        # page it lands on is the one that answers it.
        raise CredentialError(
            f"charter.packs.{self._pack} has no credentials. Either call "
            f"charter.packs.{self._pack}.configure(credential_provider=...) or set "
            f"${self._env_var}.",
            provider=provider,
            docs=f"packs/{self._pack}",
        )


class DeferredApiKeyHeaders:
    """Auth headers for an API-key pack, resolved at request time.

    Passed to a factory as ``api_key_headers``; the runtime calls it on every
    request. That is what makes ``configure()`` reach tools built before it, and
    what makes an unconfigured pack fail locally instead of sending a sentinel —
    without any per-tool step a pack author could forget.
    """

    def __init__(
        self,
        pack: str,
        template: Dict[str, str],
        key_header: str,
        env_var: Optional[str] = None,
    ) -> None:
        self._pack = pack
        self._template = dict(template)
        self._key_header = key_header
        self._env_var = env_var
        self._api_key: Optional[str] = None

    def configure(self, api_key: str) -> None:
        if not api_key:
            raise CredentialError(f"charter.packs.{self._pack} was given an empty API key")
        self._api_key = api_key

    @property
    def key_header(self) -> str:
        """The header the key is sent in, for documentation."""
        return self._key_header

    @property
    def header_template(self) -> Dict[str, str]:
        """The headers with the key still a placeholder, for documentation.

        What a caller would have to write by hand instead of using this pack,
        which is what the generated wire block on each pack page shows.
        """
        return dict(self._template)

    @property
    def env_var(self) -> Optional[str]:
        """The environment variable this pack falls back to, for documentation."""
        return self._env_var

    @property
    def is_configured(self) -> bool:
        return self._api_key is not None

    def __call__(self) -> Dict[str, str]:
        if self._api_key is None:
            raise CredentialError(
                f"charter.packs.{self._pack} has no API key. Call "
                f"charter.packs.{self._pack}.configure(api_key=...) first.",
                provider=self._pack,
                docs=f"packs/{self._pack}",
            )
        return {
            key: value.replace(_UNSET, self._api_key)
            for key, value in self._template.items()
        }

    def __repr__(self) -> str:
        state = "configured" if self.is_configured else "unconfigured"
        return f"DeferredApiKeyHeaders({self._pack!r}, {state})"


def api_key_headers(
    pack: str, template: Dict[str, str], key_header: str, env_var: str
) -> DeferredApiKeyHeaders:
    """Build a deferred header dict, seeded from ``env_var`` when it is set."""
    headers = DeferredApiKeyHeaders(pack, template, key_header, env_var)
    from_env = os.environ.get(env_var)
    if from_env:
        headers.configure(from_env)
    return headers
