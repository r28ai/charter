### A failure the API reports inside a 2xx

| case | charter | charter (labels_patch) | mcp | raw | composio | the vendor's words |
|---|---|---|---|---|---|---|
| gmail-update-missing-label | reported success | reported the failure | reported the failure | reported success | reported the failure | Not documented: found live on 2026-10-23. A label update for an id that does not exist answers 200 with the request echoed back, and changes nothing. |
| linear-comment-missing-issue | reported the failure |  | reported the failure | returned the error as data |  | 'GraphQL queries can partially succeed with a 200 HTTP status' (linear.app/developers/graphql) |
| linear-update-missing-issue | reported the failure |  | reported the failure | returned the error as data |  | 'GraphQL queries can partially succeed with a 200 HTTP status, returning some data while including errors for failed fields.' (linear.app/developers/graphql) |
| shopify-update-missing-customer | reported the failure |  | reported the failure | returned the error as data |  | 'the GraphQL API can return a 200 OK response code in cases that would typically produce 4xx or 5xx errors in REST' (shopify.dev/docs/api/admin-graphql) |
| shopify-update-missing-product | reported the failure |  | reported the failure | returned the error as data |  | 'the GraphQL API can return a 200 OK response code in cases that would typically produce 4xx or 5xx errors in REST' (shopify.dev/docs/api/admin-graphql) |
| slack-post-archived-channel | reported the failure |  | reported the failure | returned the error as data |  | chat.postMessage, Errors: is_archived: Channel has been archived (docs.slack.dev/reference/methods/chat.postMessage) |
| slack-react-deleted-message | reported the failure |  | reported the failure | returned the error as data |  | reactions.add, Errors: message_not_found: Message does not exist. Slack Web API: 'a top-level boolean property ok that indicates success or failure' (docs.slack.dev/reference/methods/reactions.add, docs.slack.dev/apis/web-api) |

### A call outside the documented contract

| case | charter | charter (labels_patch) | mcp | raw | composio | the vendor's words |
|---|---|---|---|---|---|---|
| calendar-empty-window | refused before sending |  | silently accepted | silently accepted |  | events.list timeMax: 'If timeMin is set, timeMax must be greater than timeMin.' (Calendar v3 discovery document) |
| calendar-over-max | refused before sending |  | silently accepted | silently accepted |  | events.list maxResults: 'The page size can never be larger than 2500 events.' (Calendar v3 discovery document) |
| calendar-sync-token-with-filter | refused before sending |  | not offered | refused |  | events.list syncToken: 'There are several query parameters that cannot be specified together with nextSyncToken to ensure consistency of the client state.' (Calendar v3 discovery document) |
| github-page-over-max | refused before sending |  | refused | silently accepted |  | List repository issues, per_page: 'The number of results per page (max 100).' (docs.github.com/rest/issues/issues#list-repository-issues) |
| gmail-list-over-max | refused before sending |  | silently accepted | silently accepted | refused | users.messages.list maxResults: 'The maximum allowed value for this field is 500.' (Gmail v1 discovery document) |
| stripe-page-over-max | refused before sending |  | silently accepted | silently accepted |  | List all customers, limit: 'Limit can range between 1 and 100, and the default is 10.' (docs.stripe.com/api/customers/list) |

### A Gmail draft, read back through Gmail's API

| case | charter | charter (labels_patch) | mcp | raw | composio | the vendor's words |
|---|---|---|---|---|---|---|
| gmail-draft-cc | exact |  | exact |  | exact | users.drafts.create stores the message as given; Cc read back through users.drafts.get. |
| gmail-draft-non-ascii-body | exact |  | exact |  | exact | A body outside ASCII needs a charset and a transfer encoding (RFC 2045). Read back through users.drafts.get. |
| gmail-draft-non-ascii-name | exact |  | exact |  | wrong: To read back as 'zoe.muller@example.com' | RFC 5322 headers are ASCII; a display name outside it is encoded as RFC 2047 (datatracker.ietf.org/doc/html/rfc2047). Read back through users.drafts.get. |
| gmail-draft-reply-in-thread | exact |  | exact |  | exact | users.drafts.create: 'The requested threadId must be specified on the Message or Draft.Message ... The References and In-Reply-To headers must be set in compliance with the RFC 2822 standard. The Subject headers must match.' (developers.google.com/workspace/gmail/api/guides/threads) |

MCP servers: @stripe/mcp 0.3.3; GeLi2001/shopify-mcp 1.0.8; Linear's hosted MCP server (mcp.linear.app); github/github-mcp-server 2.0.3; korotovsky/slack-mcp-server 1.3.0; taylorwilsdon/google_workspace_mcp 2.2.0.
