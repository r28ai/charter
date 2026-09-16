"""
Every scenario's judge must accept a correct outcome and reject the wrong ones.

A scorer that says CORRECT no matter what would make the headline number a lie
in the direction the author wants. So, offline and for every registered
scenario: the hand-written ``example()`` must be judged CORRECT, and each of the
deliberately wrong observations from ``wrong_observations()`` must be judged
INCORRECT — with the reason the scenario author gave for why it is wrong quoted
back if the judge lets it through. A scenario with fewer than two wrong
observations does not pass either.

Same shape as ``oss/tests/test_conformance_is_not_vacuous.py``: the check is
run on broken input, and passing on broken input is the failure.
"""

from __future__ import annotations

import pytest

from charter_harness.scenarios import Scenario, all_scenarios, templates
from charter_harness.scenarios.base import Verdict

# Every instance: the 16 templates and each of their parametric variants. A
# variant shares its template's judge, but its example() and
# wrong_observations() may be shaped by its parameters, so each is checked.
SCENARIOS = all_scenarios(variants=True)
TEMPLATES = templates()
MIN_WRONG = 2
MIN_INSTANCES = 100  # phase 3 target: 100-300 scenario instances


def _ids(scenario: Scenario) -> str:
    return scenario.id


def test_the_corpus_is_the_phase_one_corpus():
    assert len(TEMPLATES) == 16, sorted(s.id for s in TEMPLATES)
    assert len({s.id for s in TEMPLATES}) == len(TEMPLATES)
    assert all(not s.variant and s.id == s.template for s in TEMPLATES)


def test_the_variants_reach_the_phase_three_corpus():
    assert len(SCENARIOS) >= MIN_INSTANCES, f"{len(SCENARIOS)} instances; phase 3 needs at least {MIN_INSTANCES}"
    assert len({s.id for s in SCENARIOS}) == len(SCENARIOS)
    for s in SCENARIOS:
        if s.variant:
            assert s.id == f"{s.template}@{s.variant}"
            assert set(s.params) == set(type(s).defaults), f"{s.id} params are not exactly the template's knobs"
            assert s.params != type(s).defaults, f"{s.id} is identical to its template"
    # no two variants of one template describe the same task
    seen: dict[str, list[dict]] = {}
    for s in SCENARIOS:
        siblings = seen.setdefault(s.template, [])
        assert s.params not in siblings, f"{s.id} duplicates another variant of {s.template}"
        siblings.append(s.params)
    # every template has been given variants
    without = [t.id for t in TEMPLATES if not type(t).variants]
    assert not without, f"templates with no variants: {without}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_judge_accepts_the_example(scenario: Scenario):
    expected, observed = scenario.example()
    verdict = scenario.judge(expected, observed)
    assert isinstance(verdict, Verdict)
    assert verdict.correct, f"scorer for {scenario.id} rejects its own correct example: {verdict.explanation}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_judge_rejects_every_wrong_observation(scenario: Scenario):
    expected, observed = scenario.example()
    wrongs = scenario.wrong_observations(expected, observed)
    assert len(wrongs) >= MIN_WRONG, f"{scenario.id} supplies {len(wrongs)} wrong observation(s); at least {MIN_WRONG} are required"
    vacuous = []
    for reason, wrong in wrongs:
        verdict = scenario.judge(expected, wrong)
        if verdict.correct:
            vacuous.append(reason)
    assert not vacuous, f"scorer for {scenario.id} is vacuous against: " + "; ".join(vacuous)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_wrong_observations_are_actually_different(scenario: Scenario):
    """A 'wrong' observation identical to the correct one would pass trivially in reverse."""
    expected, observed = scenario.example()
    for reason, wrong in scenario.wrong_observations(expected, observed):
        assert wrong != observed, f"{scenario.id}: wrong observation {reason!r} equals the correct one"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_judge_is_pure_and_explains_failures(scenario: Scenario):
    expected, observed = scenario.example()
    first = scenario.judge(expected, observed)
    second = scenario.judge(expected, observed)
    assert first == second
    for _, wrong in scenario.wrong_observations(expected, observed):
        verdict = scenario.judge(expected, wrong)
        assert verdict.explanation.strip(), f"{scenario.id}: an INCORRECT verdict carries no explanation"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_prompt_names_no_tool(scenario: Scenario):
    """The task text is the same on both arms, so it must not tell the model which tool to call."""
    expected, _ = scenario.example()
    prompt = scenario.prompt("hx", expected)
    assert prompt.strip()
    for forbidden in ("_api", "_graphql", "ainvoke", "tool"):
        assert forbidden not in prompt.casefold(), f"{scenario.id} prompt leaks tooling vocabulary: {forbidden!r}"
    assert set(scenario.packs) <= set(scenario.requires)
