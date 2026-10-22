# Examples

Each file shows one thing and keeps what a real run printed in comments under its
`print`s. Most need nothing: free public APIs (httpbin.org, JSONPlaceholder, a public
GraphQL API) play your API.

```bash
pip install charter-ai
python examples/basics/01_hello_tool.py
```

Or run one straight from its URL, with nothing installed:

```bash
uv run --with charter-ai https://raw.githubusercontent.com/r28ai/charter/main/examples/basics/01_hello_tool.py
```

An example that calls a real API says what it needs on its first line, `# Needs GITHUB_TOKEN.`
for instance, and reads the key from the environment: `export GITHUB_TOKEN=...`, or
`set -a; source .env; set +a` to load a `.env`.

## Basics

Start at the top. None of these needs a key or an account.

| | what it shows |
|---|---|
| [`01_hello_tool.py`](basics/01_hello_tool.py) | Declare one API call, see what the model gets, make the call |
| [`02_wire_formats.py`](basics/02_wire_formats.py) | The model fills in an email; Charter writes the base64 MIME the API wants |
| [`03_errors_for_the_model.py`](basics/03_errors_for_the_model.py) | A wrong argument is refused before sending, with a message the model can act on |
| [`04_trim_responses.py`](basics/04_trim_responses.py) | Do nothing and the model gets the whole response; write a handler and it gets what it needs |
| [`05_catch_failed_200s.py`](basics/05_catch_failed_200s.py) | A GraphQL API's `200` with an `errors` list raises instead of reading as a success |
| [`06_cut_a_tool.py`](basics/06_cut_a_tool.py) | 33 kinds of Docs edit behind one URL, cut to the 3 that edit text |
| [`07_price_a_tool.py`](basics/07_price_a_tool.py) | Find the field that makes a tool expensive: 44,828 of 45,072 tokens |
| [`08_many_tools.py`](basics/08_many_tools.py) | All 613 tools in one session: 471,451 tokens up front, 4,476 on the first turn |
| [`09_rules_on_fields.py`](basics/09_rules_on_fields.py) | Rules on their fields instead of in the system prompt, gone when the field is cut |
| [`10_pin_a_value.py`](basics/10_pin_a_value.py) | A value the model can neither see nor set |
| [`11_one_tool_per_plan.py`](basics/11_one_tool_per_plan.py) | The same call refused on free, refused on pro, sent on max |
| [`12_scopes_from_tools.py`](basics/12_scopes_from_tools.py) | The OAuth scopes to ask your users for, computed from the tools you hand out |
| [`13_review_the_boundary.py`](basics/13_review_the_boundary.py) | What the agent can touch, as a diff: a new tool, a dropped pin |

## Connect an account

Yours, or each of your users', by OAuth or by API key.

| | OAuth | API key |
|---|---|---|
| **Your own account** | [`my_google.py`](connect/my_google.py): Google's consent flow once, from a terminal | [`my_api_keys.py`](connect/my_api_keys.py): a key fixed at startup, or fetched from your secret store on every call |
| **Your users' accounts** | [`users_oauth.py`](connect/users_oauth.py): a web app where each user connects GitHub, with Disconnect that revokes | [`users_api_keys.py`](connect/users_api_keys.py): each user pastes a key, and every call uses the right one |

[`users_refresh.py`](connect/users_refresh.py) keeps each user's Google grant fresh: Charter
refreshes an expired token and hands you the new one to store.

[`use_a_pack.py`](connect/use_a_pack.py) calls a tool that ships with Charter, with your own
GitHub token: GitHub sends 346.6 KB, the pack hands on 10.7 KB. Turn that off, or parse it your way.

## Frameworks

[`openai_loop.py`](frameworks/openai_loop.py) gives tools to any OpenAI-compatible model with
Charter's own loop, no framework (needs a model key).
[`langchain_agent.py`](frameworks/langchain_agent.py) puts Charter tools in a LangChain
agent. [`mcp_server.py`](frameworks/mcp_server.py) serves them over MCP.

## Full agents built on Charter

- [Shipmate](https://github.com/r28ai/shipmate): an open-source assistant in your terminal
  that reads your email, calendar, GitHub, Slack and Linear, and asks before it changes
  anything.
- MCP servers, one per job: [chief of staff](https://github.com/r28ai/chief-of-staff-mcp),
  [GitHub + Linear dev workflows](https://github.com/r28ai/github-linear-mcp),
  [product manager](https://github.com/r28ai/product-manager-mcp) and
  [eight more](https://github.com/r28ai?q=mcp).
