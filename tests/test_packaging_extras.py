"""The `mcp` extra installs from wheels on every platform people develop on.

`mcp` depends on `pyjwt[crypto]`, so `cryptography` — a Rust extension — is a
transitive dependency of `pip install 'charter-ai[mcp]'`. Upstream has dropped
wheels for three platforms at three different versions, and with no wheel pip
builds from the sdist and dies in `cargo metadata` unless a Rust toolchain
happens to be installed. The error names maturin and Cargo.lock, which does not
read as anything to do with installing an MCP server.

The caps in the `mcp` extra pin those three platforms and only those three. This
asserts the markers still select that way, offline: PyPI is not consulted, so
what is checked is the intent of the declaration rather than today's index.

The version each cap allows is recorded here as the newest that actually shipped
a wheel for that platform, so raising a cap means checking the index again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import Requirement

try:
    import tomllib
except ModuleNotFoundError:  # 3.10 predates tomllib
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def _mcp_extra() -> list[Requirement]:
    spec = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return [Requirement(r) for r in spec["project"]["optional-dependencies"]["mcp"]]


def _environment(sys_platform: str, machine: str) -> dict:
    """Enough of a PEP 508 environment to evaluate the markers we write."""
    return {
        "sys_platform": sys_platform,
        "platform_machine": machine,
        "platform_system": {"darwin": "Darwin", "linux": "Linux", "win32": "Windows"}[sys_platform],
        "os_name": "nt" if sys_platform == "win32" else "posix",
        "python_version": "3.12",
        "python_full_version": "3.12.0",
        "implementation_name": "cpython",
        "implementation_version": "3.12.0",
        "platform_release": "",
        "platform_version": "",
        "extra": "",
    }


def _cryptography_constraint(sys_platform: str, machine: str) -> str | None:
    applied = [
        str(r.specifier)
        for r in _mcp_extra()
        if r.name == "cryptography"
        and (r.marker is None or r.marker.evaluate(_environment(sys_platform, machine)))
    ]
    assert len(applied) <= 1, (
        f"{sys_platform}/{machine} matches {len(applied)} cryptography caps "
        f"({applied}); overlapping markers make the resolved version depend on "
        f"the resolver's ordering"
    )
    return applied[0] if applied else None


# The last version upstream published a wheel for, per platform.
CAPPED = [
    # macOS Intel: 49.0.0 went arm64-only, dropping the universal2 wheel.
    ("darwin", "x86_64", "<49"),
    # Windows 32-bit: 49.0.0 dropped win32.
    ("win32", "x86", "<49"),
    # Windows ARM64: 46.0.4 dropped win_arm64.
    ("win32", "ARM64", "<46.0.4"),
]

UNCAPPED = [
    ("darwin", "arm64"),
    ("linux", "x86_64"),
    ("linux", "aarch64"),
    ("win32", "AMD64"),
]


@pytest.mark.parametrize(("sys_platform", "machine", "expected"), CAPPED)
def test_the_wheel_less_platforms_are_capped(sys_platform, machine, expected):
    """A platform with no current wheel resolves to the newest that has one."""
    assert _cryptography_constraint(sys_platform, machine) == expected, (
        f"{sys_platform}/{machine} has no cryptography wheel past {expected}; "
        f"without that cap `pip install 'charter-ai[mcp]'` builds from the sdist "
        f"and needs a Rust toolchain"
    )


@pytest.mark.parametrize(("sys_platform", "machine"), UNCAPPED)
def test_every_other_platform_is_left_alone(sys_platform, machine):
    """Upstream ships wheels here, so the cap must not reach this far.

    A cap is a cost — it holds a security-relevant package back — and it is only
    worth paying where the alternative is an install that cannot succeed.
    """
    assert _cryptography_constraint(sys_platform, machine) is None, (
        f"{sys_platform}/{machine} has current cryptography wheels and must "
        f"resolve to the newest version"
    )


def test_the_extra_still_asks_for_the_server_package():
    """The caps are additions to the extra, not a replacement for it."""
    names = {r.name for r in _mcp_extra()}
    assert "mcp" in names, "the mcp extra no longer installs mcp"


def test_charter_does_not_import_cryptography_on_the_served_path():
    """The caps cost these platforms no Charter behaviour.

    `cryptography` reaches Charter only through `mcp`'s OAuth verification for
    HTTP transports. Charter serves stdio, and nothing on that path imports it,
    which is what makes pinning someone else's transitive dependency defensible
    rather than merely expedient.
    """
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    import subprocess
    import sys

    probe = (
        "import sys, charter.adapters.mcp, charter.mcp;"
        "sys.exit(1 if 'cryptography' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", probe]).returncode == 0, (
        "importing Charter's MCP adapter now pulls in cryptography, so the "
        "version caps in the mcp extra have become load-bearing for behaviour"
    )
