"""
Copy the Shopify CLI's access token into ``harness/.env``.

``shopify store auth`` needs a browser, so a human runs that half. It does not
print the token either - it writes it to the CLI's own config. This script is
the other half: find the session for our store, check it has not already
expired, and rewrite the one ``SHOPIFY_ACCESS_TOKEN=`` line.

Despite its ``shpat_`` prefix the token is an **online** token with a 24-hour
``expiresAt``, so this runs daily. A ``shpat_`` value normally means a
never-expiring custom-app token, which is why a stale one reads as a permissions
bug rather than an expiry.

    # in the Claude Code prompt, because it opens a browser:
    ! shopify store auth --store <shop> --scopes read_products,write_products,\\
read_customers,write_customers,read_inventory,write_inventory,read_locations

    .venv/bin/python scripts/sync_shopify_token.py

The token is never printed. Exits 0 on success, 1 if no usable session is found.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from charter_harness.settings import default_env_file, load

CONFIG = Path.home() / "Library/Preferences/shopify-cli-store-nodejs/config.json"


def sessions(config: dict):
    """Every (store, session) pair, flattened out of the client-id keying."""
    for entry in config.values():
        if not isinstance(entry, dict):
            continue
        for session in (entry.get("sessionsByUserId") or {}).values():
            if isinstance(session, dict) and session.get("accessToken"):
                yield session.get("store", ""), session


def main() -> int:
    shop = load().shopify_shop
    if not shop:
        print("SHOPIFY_SHOP is not set; nothing to match against.")
        return 1
    if not CONFIG.exists():
        print(f"No Shopify CLI config at {CONFIG}. Run `shopify store auth` first.")
        return 1

    # Keyed by client id, so match on the store field rather than the key.
    found = [s for store, s in sessions(json.loads(CONFIG.read_text())) if store == shop]
    if not found:
        print(f"No session for {shop} in {CONFIG}. Run `shopify store auth --store {shop}`.")
        return 1

    session = max(found, key=lambda s: s.get("acquiredAt") or "")
    expires = session.get("expiresAt")
    if expires:
        when = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        left = when - datetime.now(timezone.utc)
        if left.total_seconds() <= 0:
            print(f"The stored token for {shop} expired {-left.days}d ago ({expires}).")
            print(f"Re-run: shopify store auth --store {shop} --scopes ...")
            return 1
        print(f"Token valid for {left.total_seconds() / 3600:.1f}h (expires {expires}).")

    env = default_env_file()
    text = env.read_text()
    updated, count = re.subn(
        r"^SHOPIFY_ACCESS_TOKEN=.*$",
        f"SHOPIFY_ACCESS_TOKEN={session['accessToken']}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        print(f"Expected exactly one SHOPIFY_ACCESS_TOKEN line in {env}, found {count}.")
        return 1
    env.write_text(updated)
    print(f"Wrote a fresh token to {env} (not printed here).")
    print("Verify with: .venv/bin/python scripts/check_tools.py --only shopify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
