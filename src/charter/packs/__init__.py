# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""The shipped packs, one module each: ``charter.packs.<name>``."""

from __future__ import annotations

import importlib

__all__ = ["is_configured"]


def is_configured(pack: str) -> bool:
    """Whether ``charter.packs.<pack>`` has a credential to call with.

    True once its ``configure()`` has run, or when the environment holds what the
    pack reads by itself: its key, its token, or a grant it can renew. It is the
    test the pack makes before its first call, so a host can tell "connected" from
    "not yet" without making one. It says nothing about whether the API will
    accept the credential; only a call says that.

    Raises ``ModuleNotFoundError`` for a pack that does not exist.
    """
    module = importlib.import_module(f"charter.packs.{pack}")
    # Every pack holds its credential in one of these, filled by configure().
    for name in ("_credentials", "_headers"):
        holder = getattr(module, name, None)
        if holder is not None:
            return bool(holder.is_configured)
    raise TypeError(f"charter.packs.{pack} holds no credential that can be checked")
