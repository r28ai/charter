"""
charter-harness — the scenario harness.

A real model drives multi-step, cross-pack tasks through the Charter boundary on
real accounts. Every run is scored by reading the world back through an
independent client — never by trusting the agent's own tool results. The same
tasks run through a raw-API-glue control arm so the boundary's contribution has
a baseline, and every scorer is proven to fail on a deliberately wrong outcome.

Layout::

    settings.py      credentials -> pack.configure(...) wiring
    arms/            the two tool surfaces: charter (Tool -> ToolDef) and raw
    guard.py         the approval policy both arms run under
    world/           raw-httpx seed / observe / teardown clients per provider
    scenarios/       the corpus; each scenario is seed + prompt + observe + judge
    task.py          the Inspect task
    campaign.py      arms x models -> results/<campaign>/
    report.py        Inspect logs -> summary.md / summary.json
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
