# Failures that come back as a success: 16 APIs

Surveyed 2026-10-23. For each API Charter ships a pack for, the question is
whether the **vendor's own documentation** describes a request that fails, in
whole or in part, while the response is still 2xx. Only the endpoints the packs
declare were in scope.

Method: each vendor's error-handling page was read; for the six Google APIs every
field and method description in the discovery document was also searched for
`fail`, `partial`, `incomplete`, `ignored`, `silently` and `truncated`; for Graph,
the send-mail, list-messages and `$search` pages were searched the same way. Every
quote below was checked word for word against the page on that date. Live rows
are from `bench/survey_200.py` (`results/bench/survey_200_live.json`).

Four kinds, kept apart because they are not equally bad:

- **A, the body says it failed.** A 2xx whose body carries an error. Code that
  checks the status code and not the body reports success.
- **B, the body flags a partial result.** A 2xx with a flag saying something is
  missing.
- **C, ignored or incomplete, and nothing says so.** A 2xx, documented to drop part
  of the request or the result, with no field that tells you.
- **D, accepted, fails later.** A 2xx that only means accepted; the failure arrives
  afterwards by another route.

## Result

| | APIs |
|---|---:|
| at least one documented failure inside a 2xx (A, B or C) | **10 of 16** |
| ...of which the body carries the failure (A or B) | 8 of 16 |
| only D (accepted, fails later) | 2 of 16 |
| none found | 4 of 16 |

## Per API

| API | kind | what happens | vendor's words | live sample | Charter's pack |
|---|---|---|---|---|---|
| Slack | A | every method failure | "a top-level boolean property `ok` that indicates success or failure. For failure results, the `error` property will contain a short machine-readable error code." ([docs.slack.dev/apis/web-api](https://docs.slack.dev/apis/web-api/)) | `conversations.info` on a missing channel: **200**, `ok:false`, `channel_not_found` | `SLACK_ENVELOPE` raises |
| Linear | A | GraphQL errors, partial success | "GraphQL queries can partially succeed with a 200 HTTP status, returning some data while including errors for failed fields." ([linear.app/developers/graphql](https://linear.app/developers/graphql)) | `issue(id:)` for a missing id: **200**, `errors: Entity not found: Issue` | `LINEAR_ENVELOPE` raises |
| Shopify | A | every GraphQL failure, including rate limiting | "the status is `200 OK` — even if the operation inside it failed." ([shopify.dev/docs/api/usage/response-codes](https://shopify.dev/docs/api/usage/response-codes)) | not run: the store token returned 401 | `SHOPIFY_ENVELOPE` raises on `errors` and `userErrors` |
| Firecrawl | A | a scrape of a page that is itself an error; a crawl whose pages failed | `metadata.statusCode`: "The status code of the page" ([scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape)); "`total` counts completed, active, queued, and backlogged pages and excludes failed ones, so `completed == total` on a finished crawl does not mean every discovered page succeeded." ([crawl status](https://docs.firecrawl.dev/api-reference/endpoint/crawl-get)) | scrape of a 404 page: **200**, `success:true`, `metadata.statusCode: 404` | handler keeps `statusCode` and `error`; nothing raises |
| Tavily | A | extract, per URL | "Successful URLs appear in results; per-URL failures appear in failed_results. Check both arrays even when the response is HTTP 200." ([extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)) | not run: the plan's 1,000 calls were used up (432) | no handler; `failed_results` passes through |
| Google Calendar | A, C | a Meet link that could not be made; a visibility change ignored | `ConferenceRequestStatus.statusCode`: "\"failure\": the conference create request failed, there are no entry points." `Event.visibility`: "If the new setting is less restrictive (e.g. from private to public), the change is ignored." (Calendar v3 discovery document) | not run: the Google grant had expired | handler keeps `conferenceStatus` (since b7669ae; it was trimmed away before); the ignored visibility change is not caught |
| GitHub | B | search that timed out | "the API returns the matches that were already found prior to the timeout, and the response has the `incomplete_results` property set to `true`." ([REST search](https://docs.github.com/en/rest/search/search)) | not triggerable on demand | handler keeps `incomplete_results` |
| Google Drive | B, C | a search that could not cover every drive; a revision list that may be short | `FileList.incompleteSearch`: "If true, then some search results might be missing, since all documents were not searched." `revisions.list`: "The list of revisions returned by this method might be incomplete for files with a large revision history" (Drive v3 discovery document) | not triggerable on demand | handler keeps `incompleteSearch`; `revisions_list`'s description carries Google's warning |
| Google Docs | C | content sent to `documents.create` | "Other fields in the request, including any provided content, are ignored. Returns the created document." (Docs v1 discovery document) | not run: the Google grant had expired | the tool offers only `title` |
| Google Forms | C | settings sent to `forms.create` | `Form.settings`: "it is ignored during CreateForm and UpdateFormInfoRequest." (Forms v1 discovery document) | not run: the Google grant had expired | the tool offers only `info.title` and `info.documentTitle` |
| Stripe | D | a refund that fails after it was created | "a refund to a card can fail" and its status becomes `failed`; Stripe sends `refund.failed` ([docs.stripe.com/refunds](https://docs.stripe.com/refunds)) | control: a missing refund is **404** `resource_missing` | nothing to surface at call time |
| Outlook (Graph) | D | mail to an address that does not exist | `sendMail`: "A `202 Accepted` response code indicates that the request has been accepted; however, it doesn't indicate that the request processing has completed." "Transport detects invalid recipient addresses at this point, for which transport mails the non-delivery reports back to the sender." ([sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), [things to know about send mail](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)) | not run: no Outlook account in the harness | nothing to surface at call time |
| Gmail | none | | nothing in the endpoints the pack declares. Outside them, `SendAs.displayName` "will silently fail" for some accounts | | |
| Google Sheets | none | | `batchUpdate` is atomic: "If any request is not valid then the entire request will fail and nothing will be applied." | | |
| Notion | none | | every documented failure is a 4xx or 5xx ([status codes](https://developers.notion.com/reference/status-codes)) | | |
| Granola | none | | failures are 404, 413 and 429 ([introduction](https://docs.granola.ai/introduction)) | | |

## Found live, not in the docs

Two more turned up while verifying the Google scopes
(`scripts/live_google_scopes_check.py`, 2026-10-23, on a test account). Neither is
documented, so neither counts above.

| API | request | answer |
|---|---|---|
| Gmail | `PUT users/me/labels/{id}` for a label id that does not exist | **200**, the request body echoed back as if saved; no label created, none changed |
| Google Calendar | `GET calendars/primary/events/{id}/instances` for an event id that does not exist | **200**, an empty list; `events.get` for the same id answers 404 |

An agent that renames a label by a stale id is told it worked. One that asks for
the occurrences of a mistyped recurring event is told there are none.

## What this does not show

- **Documented is a floor.** An API can answer 200 to a failure its docs never
  mention; this counts only what the vendor wrote down.
- **Not every row was confirmed live.** Three were (Slack, Linear, Firecrawl), and
  the two controls (Stripe, GitHub) behaved as documented. Shopify and the Google
  rows wait on fresh credentials; GitHub's and Drive's flags cannot be triggered
  on demand.
- **Kind C is not one Charter catches by inspecting the response**: nothing in the
  response says so. Docs and Forms are covered because their tools do not offer
  the ignored fields. Calendar's ignored visibility change on a recurring
  instance is not covered.
- **Kind D is outside any tool layer at call time.** The failure arrives later,
  as a webhook or a bounce.
