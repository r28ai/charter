"""Shopify from a Dev Dashboard app's client ID and secret, on every path the harness uses.

The pack mints its own tokens from the pair; the harness used to know only
SHOPIFY_ACCESS_TOKEN, a token that dies a day after it is minted, and handed it
to the pack, the raw arm and the world separately. One provider now serves all
three, so every path sends the token the pack is sending.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from charter_harness.arms.raw_arm import _auth_headers
from charter_harness.settings import MissingCredentials, Settings, load, wire_packs

SHOP = "harness-test.myshopify.com"
TOKEN_URL = f"https://{SHOP}/admin/oauth/access_token"
PAIR = {"SHOPIFY_SHOP": SHOP, "SHOPIFY_CLIENT_ID": "cid", "SHOPIFY_CLIENT_SECRET": "csecret"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in (
        "SHOPIFY_SHOP",
        "SHOPIFY_ACCESS_TOKEN",
        "SHOPIFY_CLIENT_ID",
        "SHOPIFY_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    def make(**values: str) -> Settings:
        path = tmp_path / ".env"
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
        return load(path)

    return make


def test_the_client_id_and_secret_make_shopify_available_without_a_token(env):
    assert "shopify" in env(**PAIR).available()
    assert "shopify" in env(SHOPIFY_SHOP=SHOP, SHOPIFY_ACCESS_TOKEN="shpat_x").available()
    assert "shopify" not in env(SHOPIFY_SHOP=SHOP, SHOPIFY_CLIENT_ID="cid").available()


def test_a_missing_shopify_names_both_ways_to_configure_it(env):
    with pytest.raises(MissingCredentials) as caught:
        env(SHOPIFY_SHOP=SHOP).require("shopify")
    assert "SHOPIFY_ACCESS_TOKEN — or SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET" in str(caught.value)


@respx.mock
async def test_one_minted_token_reaches_the_pack_and_the_raw_arm(env):
    minted = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "minted", "expires_in": 86399})
    )
    wiring = wire_packs(env(**PAIR, SHOPIFY_ACCESS_TOKEN="shpat_stale"), frozenset({"shopify"}))

    assert await _auth_headers("shopify", wiring) == {"X-Shopify-Access-Token": "minted"}

    from charter.packs import shopify

    api = respx.post(url__regex=rf"https://{SHOP}/admin/api/.*/graphql\.json").mock(
        return_value=httpx.Response(200, json={"data": {"shop": {"name": "Harness"}}})
    )
    await shopify.shop_get.ainvoke({})
    assert api.calls.last.request.headers["x-shopify-access-token"] == "minted"
    assert minted.call_count == 1  # the pair wins over the stale token, and is minted once


async def test_a_lone_access_token_still_works(env):
    wiring = wire_packs(
        env(SHOPIFY_SHOP=SHOP, SHOPIFY_ACCESS_TOKEN="shpat_x"), frozenset({"shopify"})
    )
    assert await _auth_headers("shopify", wiring) == {"X-Shopify-Access-Token": "shpat_x"}
