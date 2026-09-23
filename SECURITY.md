# Security

## Reporting a vulnerability

Email **security@r28.ai**. Please do not open a public issue for a
vulnerability — a report about a library that mediates credentials is useful to
an attacker the moment it is public.

Include what you need to make it reproducible: the version, the pack or module,
and the shape of the failure. You will get an acknowledgement within three
working days and an assessment within ten. If a fix ships, you will be credited
in the changelog unless you would rather not be.

## What is in scope

Charter sits between a model and your APIs, and holds bearer tokens in memory
while they are valid. The things that matter most:

- **A credential reaching somewhere it should not** — a token in a log record, an
  exception message, a `ToolCall`, or an error handed back to a model.
- **The egress boundary failing to hold** — a field marked `Mode("response_only")`
  or `Mode("disabled")` reaching a model's context, or `egress_map()` reporting a
  boundary that differs from what the runtime enforces.
- **One principal's credentials serving another** — anything that lets
  `SubjectProvider` hand subject A's token to subject B.
- **A tool call the schema should have rejected reaching the network.**
- **Anything that makes the library phone home.** It makes no network calls
  except the API calls you define and, when you call it by name,
  `OAuth2Server.discover`. A network call from anywhere else is a bug of this
  class.

## What is not in scope

- **What your agent does with a response.** Charter governs what crosses the
  boundary; what your own code or prompt does afterwards is yours.
- **`Mode` as authorization.** It is schema visibility — it decides what a tool
  exposes, never who may call it.
- **Vulnerabilities in the APIs a pack targets.** Report those to that vendor.
  Do tell us if a pack's *declaration* is wrong in a way that has a security
  consequence.
- **The absence of a feature we say we do not have.** Request signing, HITL
  enforcement and multi-call orchestration are named limits in the README, not
  gaps to report.

## Supported versions

Pre-1.0, only the latest release is supported. Fixes ship in a new patch
release rather than as backports.

## How releases are signed off

Releases are published from CI through PyPI trusted publishing, so no long-lived
upload token exists to steal. Every release runs the full suite, `ruff`,
`pyright`, and a `gitleaks` scan; the suite is entirely offline, so a test that
suddenly needs the network is itself a signal.
