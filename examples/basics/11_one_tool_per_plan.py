"""One tool, three plans: the same call is refused, refused, then sent.

httpbin.org stands in for your API: it echoes back the request it received.
"""

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter import Body, Mode, Path, ToolValidationError, api_key_tool_factory


class CreateReport(BaseModel):
    account_id: Annotated[str, Path()]
    metric: Annotated[str, Body()] = Field(description="The metric to report on.")
    raw_events: Annotated[
        Optional[bool],
        Body(),
        Mode("pro, max"),
    ] = None
    forecast_months: Annotated[
        Optional[int],
        Body(),
        Mode("max"),
    ] = None


reports = api_key_tool_factory(
    pack="reports",
    base_url="https://httpbin.org/anything/",
    api_key_headers={"Authorization": "Bearer sk_demo"},
)
create_report = reports(
    name="create_report",
    description="Build a report for one account.",
    method="POST",
    url_template="accounts/{account_id}/reports",
    args_schema=CreateReport,
)

# What the model asked for, word for word, under every plan.
call = {"account_id": "acc_42", "metric": "revenue", "raw_events": True, "forecast_months": 6}

for plan in ("free", "pro", "max"):
    try:
        sent = create_report.with_mode(plan).invoke(call)["json"]
        print(f"{plan:4}  sent     {sent}")
    except ToolValidationError as refused:
        print(f"{plan:4}  refused  {', '.join(e['loc'][-1] for e in refused.errors)}")
# free  refused  raw_events, forecast_months
# pro   refused  forecast_months
# max   sent     {'forecastMonths': 6, 'metric': 'revenue', 'rawEvents': True}
