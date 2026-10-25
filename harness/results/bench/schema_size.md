### The same operation

| operation | Charter | MCP server | Composio |
|---|---:|---:|---:|
| Slack: add a reaction | 568 | 669 (`reactions_add`) |  |
| Slack: post a message | 3,750 | 1,403 (`conversations_add_message`) |  |
| Linear: update an issue | 5,757 | 8,271 (`save_issue`) |  |
| Linear: comment on an issue | 3,239 | 2,821 (`save_comment`) |  |
| Gmail: update a label | 3,842 | 1,887 (`manage_gmail_label`) | 2,100 |
| Gmail: list messages | 1,477 | 1,341 (`search_gmail_messages`) | 2,789 |
| Gmail: create a draft | 3,240 | 5,759 (`draft_gmail_message`) | 2,510 |
| Calendar: list events | 7,367 | 3,490 (`get_events`) |  |
| GitHub: list a repository's issues | 2,605 | 2,340 (`list_issues`) |  |
| Stripe: list customers | 1,075 | 1,246 (`stripe_api_read`) |  |

### The whole surface

| API | Charter tools | Charter bytes | MCP server | its tools | its bytes |
|---|---:|---:|---|---:|---:|
| Github | 139 | 160,089 | github/github-mcp-server 2.0.3 | 46 | 49,408 |
| Gmail and Calendar | 37 | 176,906 | taylorwilsdon/google_workspace_mcp 2.2.0 | 22 | 46,828 |
| Linear | 128 | 375,895 | Linear's hosted MCP server (mcp.linear.app) | 60 | 84,263 |
| Slack | 18 | 20,035 | korotovsky/slack-mcp-server 1.3.0 | 16 | 13,269 |
| Stripe | 66 | 118,596 | @stripe/mcp 0.3.3 | 9 | 15,840 |
