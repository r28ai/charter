# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""``charter.packs.is_configured``: what a host asks instead of reading a pack's privates."""

from __future__ import annotations

import importlib

import pytest
from tests.test_conformance import PACK_NAMES

from charter.auth import StaticTokenProvider
from charter.packs import is_configured


@pytest.fixture
def unconfigured(monkeypatch):
    """A pack as it is before configure(), with nothing in the environment to find."""

    def strip(pack):
        module = importlib.import_module(f"charter.packs.{pack}")
        holder = getattr(module, "_credentials", None)
        if holder is not None:
            monkeypatch.setattr(holder, "_provider", None)
            if holder.env_var:
                monkeypatch.delenv(holder.env_var, raising=False)
            if holder.env_grant is not None:  # Google's refresh token, Shopify's client
                monkeypatch.setattr(type(holder.env_grant), "is_set", lambda self: False)
        else:
            monkeypatch.setattr(module._headers, "_api_key", None)
        return module

    return strip


@pytest.mark.parametrize("pack", PACK_NAMES)
def test_every_pack_answers_and_turns_true_once_configured(pack, unconfigured, monkeypatch):
    module = unconfigured(pack)
    assert is_configured(pack) is False

    holder = getattr(module, "_credentials", None)
    if holder is not None:
        # configure() is the pack's own; reset what it fills when the test ends.
        monkeypatch.setattr(holder, "_provider", holder._provider)
        holder.configure(StaticTokenProvider("t"))
    else:
        monkeypatch.setattr(module._headers, "_api_key", module._headers._api_key)
        module.configure("k")
    assert is_configured(pack) is True


def test_the_environment_alone_counts(monkeypatch, unconfigured):
    # github reads $GITHUB_TOKEN by itself, so a host that set it is connected.
    module = unconfigured("github")
    assert is_configured("github") is False
    monkeypatch.setenv(module._credentials.env_var, "ghp_from_env")
    assert is_configured("github") is True


def test_a_pack_that_does_not_exist_is_an_error():
    with pytest.raises(ModuleNotFoundError):
        is_configured("no_such_pack")
