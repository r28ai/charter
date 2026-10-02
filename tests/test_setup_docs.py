"""The setup guides: where every pack's credential comes from.

A reader's first error is ``CredentialError``, and it links the pack's page.
These pin that the page answers it — names where the credential is issued, as a
link — and that the guides' prefilled links ask for what the packs declare,
read off the packs rather than typed into the page.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from charter.auth import scopes_for
from charter.mcp import PACKS
from charter.packs import github, slack

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GUIDES = ["google", "slack", "github", "notion"]


def _load_generator():
    path = ROOT / "scripts" / "generate_pack_docs.py"
    spec = importlib.util.spec_from_file_location("generate_pack_docs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()


@pytest.mark.parametrize("pack", PACKS)
def test_the_auth_section_opens_with_where_the_credential_comes_from(pack):
    """The lead comes first, and it is a link — never only a description of a place."""
    signpost = GEN.blocks(pack)["auth"]
    lead = GEN._SETUP[pack].lead

    assert signpost.startswith(lead)
    assert "](https://" in lead or "](/auth/setup/" in lead, f"{pack}: the lead links nowhere"


def test_the_overview_lists_every_pack():
    page = (DOCS / "auth" / "your-own-account.mdx").read_text()
    table = GEN.extract(page, "setup")

    assert table is not None
    for pack in PACKS:
        assert f"](/packs/{pack})" in table, f"{pack} is missing from the overview"


def test_the_slack_link_carries_the_manifest_on_the_page():
    """One click creates the app the page shows, and that app can call the tools."""
    page = (DOCS / "auth" / "setup" / "slack.mdx").read_text()
    link = re.search(r"\((https://api\.slack\.com/apps\?[^)]+)\)", page)
    block = re.search(r"```json manifest\.json\n(.*?)\n```", page, re.S)
    assert link and block

    carried = json.loads(parse_qs(urlparse(link.group(1)).query)["manifest_json"][0])
    shown = json.loads(block.group(1))

    assert carried == shown
    assert shown["oauth_config"]["scopes"]["bot"] == scopes_for(slack.TOOLS)


def test_the_github_link_asks_for_the_pack_s_scopes():
    page = (DOCS / "auth" / "setup" / "github.mdx").read_text()
    link = re.search(r"\((https://github\.com/settings/tokens/new\?[^)]+)\)", page)
    assert link

    asked = parse_qs(urlparse(link.group(1)).query)["scopes"][0].split(",")
    assert asked == github.SCOPES
    assert link.group(1) == GEN._GITHUB_TOKEN_FORM


def test_every_screenshot_is_on_the_page_and_every_reference_resolves():
    page = (DOCS / "auth" / "setup" / "google.mdx").read_text()
    referenced = set(re.findall(r'src="(/images/setup/google/[^"]+)"', page))
    on_disk = {f"/{p.relative_to(DOCS).as_posix()}" for p in (DOCS / "images/setup/google").iterdir()}

    assert referenced, "the guide shows no screenshots"
    assert referenced <= on_disk, f"missing images: {referenced - on_disk}"
    assert on_disk <= referenced, f"images no page shows: {on_disk - referenced}"


@pytest.mark.parametrize("guide", GUIDES)
def test_every_guide_is_in_the_navigation(guide):
    navigation = (DOCS / "docs.json").read_text()
    assert f'"auth/setup/{guide}"' in navigation
