"""What counts as a data point, and what the report refuses to count.

`provider_outage` decides whether a failed sample is evidence about an arm or
evidence about the account. It is a lever for discarding inconvenient runs, so
the tests that matter most here are the ones asserting it stays shut.
"""

from __future__ import annotations

import pytest

from charter_harness.report import Run, provider_outage, summarise

SUSPENDED = (
    "Error code: 412 - {'error': {'message': 'Account support-ja5zpuvsit5w is suspended, "
    "possibly due to reaching the monthly spending limit or failure to pay past invoices.'}}"
)


@pytest.mark.parametrize("code", [401, 402, 403, 412, 500, 502, 503, 504])
def test_account_and_infrastructure_codes_are_not_data(code: int) -> None:
    assert provider_outage(f"Error code: {code} - {{'error': {{}}}}") == f"provider {code}"


def test_the_billing_suspension_that_prompted_this() -> None:
    assert provider_outage(SUSPENDED) == "provider 412"


@pytest.mark.parametrize("code", [400, 404, 422, 429])
def test_the_arms_own_mistakes_stay_counted(code: int) -> None:
    """A malformed request is about the arm; a rate limit is about our concurrency."""
    assert provider_outage(f"Error code: {code} - {{'error': {{}}}}") is None


@pytest.mark.parametrize(
    "message",
    [
        None,
        "",
        "WorldError('PUT https://api.github.com/repos/x/contents/RUNBOOK.md failed')",
        "the model returned 'Error code: 412' in its answer",
        "TimeoutError",
    ],
)
def test_nothing_else_qualifies(message: str | None) -> None:
    assert provider_outage(message) is None


def _run(**kw: object) -> Run:
    base = dict(
        model="glm-5p3-flash",
        arm="raw",
        scenario="doc_to_gmail_draft",
        template="doc_to_gmail_draft",
        epoch=1,
        correct=False,
        explanation="",
    )
    base.update(kw)
    return Run(**base)  # type: ignore[arg-type]


def test_an_outage_run_is_excluded_from_the_rate() -> None:
    runs = [
        _run(correct=True, harness_error=None),
        _run(correct=False, harness_error="provider 412", error=SUSPENDED),
    ]
    cells, _ = summarise(runs)
    cell = cells[("glm-5p3-flash", "raw")]
    assert (cell.n, cell.successes) == (1, 1), "the outage must not count as a failure"
    assert len(cell.harness_errors) == 1


def test_a_genuine_failure_still_counts() -> None:
    cells, _ = summarise([_run(correct=True), _run(correct=False)])
    cell = cells[("glm-5p3-flash", "raw")]
    assert (cell.n, cell.successes) == (2, 1)
