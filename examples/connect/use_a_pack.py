# Needs GITHUB_TOKEN. With the GitHub CLI: export GITHUB_TOKEN=$(gh auth token)
"""Call a tool that ships with Charter, then change what it hands back."""

import logging

from charter import pass_through
from charter.packs import github

# One line per call: what came back, and what the model was handed.
logging.basicConfig(format="%(message)s")
logging.getLogger("charter").setLevel(logging.INFO)

runs = github.actions_list_workflow_runs
repo = {"owner": "r28ai", "repo": "charter"}

latest = runs.invoke(repo)["workflow_runs"][0]
print(f"Latest CI run: {latest['name']} #{latest['run_number']}, {latest['conclusion']}")
# actions_list_workflow… GET  repos/{owner}/{repo}/acti… 200  1.27s  ↓ 346.6 KB →  10.7 KB  (97%)
# Latest CI run: CI #108, success

# The pack's trimming is a default. Turn it off:
runs.derived(name="runs_as_sent", response_handler=pass_through).invoke(repo)
# runs_as_sent           GET  repos/{owner}/{repo}/acti… 200  1.80s  ↓ 346.6 KB → 346.6 KB


# Or parse the answer your own way:
async def one_line_each(answer: dict) -> list:
    return [f"#{run['run_number']} {run['conclusion']}" for run in answer["workflow_runs"][:5]]


print(runs.derived(name="recent_runs", response_handler=one_line_each).invoke(repo))
# recent_runs            GET  repos/{owner}/{repo}/acti… 200  1.15s  ↓ 346.6 KB →     76 B
# ['#108 success', '#107 success', '#106 success', '#105 failure', '#104 success']
