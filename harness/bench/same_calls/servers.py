"""The MCP server each case's calls go through, pinned, with why it was chosen.

Each is the most-starred MCP server for its API on GitHub on 2026-10-24, or the
vendor's own, at its quickstart configuration, with the harness's test credentials.
The write tools a server keeps off by default are switched on for the harness
channel only, which is the configuration its README gives for using them.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import urllib.request
from pathlib import Path

from mcp_layer import Server

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache" / "charter-bench"
OVERRIDES = HERE / "workspace_mcp_overrides.txt"

GITHUB_MCP_VERSION = "2.0.3"
GITHUB_MCP_SHA256 = {
    "Darwin_x86_64": None,  # read from the release's own checksums file
}


def _env(name: str) -> str:
    path = os.environ.get("CHARTER_HARNESS_ENV", str(HERE.parent.parent / ".env"))
    for line in Path(path).expanduser().read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip("'\"")
    return os.environ.get(name, "")


def github_binary() -> str:
    """github-mcp-server's release binary, downloaded once and checked against the
    release's checksums file. Docker would do as well; this needs no daemon."""
    system = {"Darwin": "Darwin", "Linux": "Linux"}[os.uname().sysname]
    machine = {"x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}[os.uname().machine]
    target = CACHE / f"github-mcp-server-{GITHUB_MCP_VERSION}-{system}-{machine}"
    if target.exists():
        return str(target)
    CACHE.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/github/github-mcp-server/releases/download/v{GITHUB_MCP_VERSION}"
    name = f"github-mcp-server_{system}_{machine}.tar.gz"
    archive = CACHE / name
    urllib.request.urlretrieve(f"{base}/{name}", archive)
    sums = (
        urllib.request.urlopen(f"{base}/github-mcp-server_{GITHUB_MCP_VERSION}_checksums.txt")
        .read()
        .decode()
    )
    want = next(line.split()[0] for line in sums.splitlines() if line.endswith(name))
    got = hashlib.sha256(archive.read_bytes()).hexdigest()
    if want != got:
        raise SystemExit(f"checksum mismatch for {name}")
    with tarfile.open(archive) as tar:
        member = tar.getmember("github-mcp-server")
        member.name = target.name
        tar.extract(member, CACHE)
    target.chmod(0o755)
    return str(target)


def servers(slack_channels: list[str], shopify: tuple[str, str] | None = None) -> dict[str, Server]:
    """Every server, pinned. ``shopify`` is (access token, shop domain), minted per run."""
    google_client = json.loads(Path(_env("WORKSPACE_MCP_CLIENT_FILE")).expanduser().read_text())[
        "installed"
    ]
    allowed = ",".join(slack_channels)
    return {
        "slack": Server(
            "korotovsky/slack-mcp-server 1.3.0",
            "the most-starred standalone Slack MCP server (1,871 stars)",
            ["npx", "-y", "slack-mcp-server@1.3.0", "--transport", "stdio"],
            {
                "SLACK_MCP_XOXB_TOKEN": _env("SLACK_BOT_TOKEN"),
                "SLACK_MCP_ADD_MESSAGE_TOOL": allowed,
                "SLACK_MCP_REACTION_TOOL": allowed,
            },
        ),
        "github": Server(
            f"github/github-mcp-server {GITHUB_MCP_VERSION}",
            "GitHub's official MCP server (33,921 stars)",
            [github_binary(), "stdio"],
            {"GITHUB_PERSONAL_ACCESS_TOKEN": _env("GITHUB_TOKEN")},
        ),
        "linear": Server(
            "Linear's hosted MCP server (mcp.linear.app)",
            "Linear's own; the most-starred Linear MCP repository points to it",
            url="https://mcp.linear.app/mcp",
            headers={"Authorization": f"Bearer {_env('LINEAR_API_KEY')}"},
        ),
        "google": Server(
            "taylorwilsdon/google_workspace_mcp 2.2.0",
            "the most-starred Gmail MCP server (3,405 stars); run with cryptography 46 "
            "because 50 has no Intel macOS wheel",
            [
                "uvx",
                "--overrides",
                str(OVERRIDES),
                "workspace-mcp==2.2.0",
                "--tools",
                "gmail",
                "calendar",
                "--single-user",
            ],
            {
                "GOOGLE_OAUTH_CLIENT_ID": google_client["client_id"],
                "GOOGLE_OAUTH_CLIENT_SECRET": google_client["client_secret"],
                "USER_GOOGLE_EMAIL": _env("GOOGLE_TEST_EMAIL"),
            },
        ),
        **(
            {
                "shopify": Server(
                    "GeLi2001/shopify-mcp 1.0.8",
                    "the most-starred Shopify Admin API MCP server (237 stars); Shopify's own "
                    "Dev MCP serves documentation, not a store",
                    [
                        "npx",
                        "-y",
                        "shopify-mcp@1.0.8",
                        "--accessToken",
                        shopify[0],
                        "--domain",
                        shopify[1],
                    ],
                    {},
                )
            }
            if shopify
            else {}
        ),
        "stripe": Server(
            "@stripe/mcp 0.3.3",
            "Stripe's official MCP server",
            ["npx", "-y", "@stripe/mcp@0.3.3"],
            {"STRIPE_SECRET_KEY": _env("STRIPE_API_KEY")},
        ),
    }
