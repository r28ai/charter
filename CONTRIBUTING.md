# Contributing

Thanks for looking. The most useful contributions here are, in order: a pack for
an API you actually use, a failing test for something the runtime gets wrong, and
a declaration fixed to match what an API really does.

## Getting set up

```bash
uv venv
uv pip install -e ".[dev,langchain,mcp]"
uv run pytest -q
```

Everything must pass before you open a PR:

```bash
uv run ruff check src tests examples scripts
uv run pyright --pythonpath .venv/bin/python src
uv run pytest -q
```

## The rules that are not negotiable

These are enforced by `tests/test_package.py`, so you will find out anyway — but
knowing them first saves a round trip.

**The core is pydantic + httpx.** Nothing else. Anything heavier lives behind an
extra, under `adapters/`. This budget is a feature of the library, not an
accident of its youth.

**The suite is offline.** Every test mocks HTTP with `respx`. No test may touch
the network, which is why the live Google check lives in `scripts/` rather than
in `tests/`.

**No telemetry, ever.** The library makes no network call except the API calls a
user defines. There is no version ping, no analytics, no default sink.

**No real credentials in fixtures.** Invented values only. `gitleaks` runs in CI.

## Adding a pack

This is the highest-value contribution and there is a guide for it:
[`skills/writing-charter-packs/SKILL.md`](skills/writing-charter-packs/SKILL.md).
Read it before starting — it covers the checklist that makes a pack correct
rather than merely working, and `tests/test_conformance.py` will hold you to most
of it automatically. Where to find the vendor's machine-readable source, which is
most of the work, is
[`FINDING-THE-SOURCE.md`](skills/writing-charter-packs/FINDING-THE-SOURCE.md).

The short version: model every field and enum from the vendor's own docs, mark
`Path`/`Query`/`Body`, set the casing, mark server-set fields
`Mode("response_only")`, declare the `Envelope` if the API reports failure inside
a 200, and add a response handler if raw responses carry more than about 2KB of
noise.

**There is one namespace.** A pack lives at `charter.packs.<name>` and is listed in
`PACK_NAMES`, whoever wrote it. There is no community tier and there will not be one,
for the same reason there is no built-in catalogue of OAuth vendors: a tier says a pack
is second class before anyone has read it, and the variance it is meant to signal is
already measured by something better. `tests/test_conformance.py` is the quality gate,
it runs over every pack alike, and `tests/test_conformance_is_not_vacuous.py` breaks
each of its checks on purpose so the gate cannot go quietly hollow. A pack that passes
is in.

**A pack tested only offline is fine.** The suite is offline by design and nobody has
credentials for every API here. Say in the PR what you could not exercise against the
real service, so the gap is on the record rather than assumed shut.

**Partial packs are welcome.** Four tools covering what you actually needed is a real
contribution — the alternative to a partial pack is no pack, not a complete one. Each
tool has to be right: every field of the endpoints you do cover, every enum value,
the failure envelope. What is optional is how much of the API you take on, never how
carefully you take it on.

## Changing the runtime

`src/charter/execution/` is the deterministic core, and behaviour there is
load-bearing for every pack. A change needs a test that fails without it. If you
are fixing something subtle, a test that *only* passes with the fix is worth more
than a paragraph explaining it — see `tests/test_conformance_is_not_vacuous.py`
for the standard.

Architecture notes for anyone (or anything) working in this codebase live in
[`AGENTS.md`](AGENTS.md).

## Pull requests

- One concern per PR.
- Say what breaks without the change.
- New behaviour needs a test; a bug fix needs a test that fails before it.
- Match the surrounding style. The comments here explain *why*, not *what* — if a
  line needed a decision, the reason for the decision is worth writing down.

By opening a PR you certify the [Developer Certificate of
Origin](https://developercertificate.org/) — that you wrote the contribution or
have the right to submit it. There is no CLA.

## Reporting a security issue

Do not open an issue. See [SECURITY.md](SECURITY.md).
