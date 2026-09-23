# Campaign `stage3-final-all`

## Headline — task success by (model, arm)

| model | arm | runs | success | rate | ± stderr | tool calls/run | tool errors/run | guard rejections | truncations | context bytes/run | tokens/run | wall s/run | errors | limits | harness errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| glm-5p3-flash | progressive | 157 | 153 | 97% | 0.013 | 6.92 | 0.46 | 0 | 0 | 10,581 | 91,394 | 48.7 | 0 | 6 | 3 |
| glm-5p3-flash | raw | 157 | 151 | 96% | 0.015 | 7.12 | 0.47 | 6 | 17 | 39,785 | 106,490 | 96.3 | 0 | 6 | 3 |

## Per scenario — successes / runs

| scenario | glm-5p3-flash · progressive | glm-5p3-flash · raw |
|---|---:|---:|
| calendar_cleanup | 10/10 | 10/10 |
| calendar_to_doc | 10/10 | 10/10 |
| doc_to_gmail_draft | 10/10 | 6/10 |
| firecrawl_to_linear | 9/9 | 8/9 |
| github_to_linear | 4/8 | 7/8 |
| gmail_label_sweep | 10/10 | 10/10 |
| inbox_to_sheet | 10/10 | 10/10 |
| linear_to_slack_digest | 10/10 | 10/10 |
| linear_triage | 10/10 | 10/10 |
| pr_to_doc | 10/10 | 10/10 |
| sheet_to_calendar | 10/10 | 10/10 |
| sheet_to_stripe_refunds | 10/10 | 10/10 |
| shopify_customer_to_stripe | 10/10 | 10/10 |
| shopify_low_stock_to_github | 10/10 | 10/10 |
| slack_thread_to_github | 10/10 | 10/10 |
| stripe_to_sheet | 10/10 | 10/10 |

## Failures, with the judge's reason

- **github_to_linear** · glm-5p3-flash · progressive · epoch 5: GitHub #1715 has no comment naming its Linear issue; GitHub #1716 has no comment naming its Linear issue
- **github_to_linear** · glm-5p3-flash · progressive · epoch 6: GitHub #1718 has no comment naming its Linear issue; GitHub #1719 has no comment naming its Linear issue; GitHub #1720 has no comment naming its Linear issue
- **github_to_linear** · glm-5p3-flash · progressive · epoch 7: GitHub #1723 has no comment naming its Linear issue; GitHub #1724 has no comment naming its Linear issue; GitHub #1726 has no comment naming its Linear issue
- **github_to_linear** · glm-5p3-flash · progressive · epoch 8: GitHub #1729 has no comment naming its Linear issue; GitHub #1731 has no comment naming its Linear issue; GitHub #1732 has no comment naming its Linear issue
- **doc_to_gmail_draft** · glm-5p3-flash · raw · epoch 2: expected exactly one draft on the thread, found 0 (of 0 drafts)
- **doc_to_gmail_draft** · glm-5p3-flash · raw · epoch 6: expected exactly one draft on the thread, found 0 (of 0 drafts)
- **doc_to_gmail_draft** · glm-5p3-flash · raw · epoch 8: expected exactly one draft on the thread, found 0 (of 0 drafts)
- **doc_to_gmail_draft** · glm-5p3-flash · raw · epoch 9: expected exactly one draft on the thread, found 0 (of 0 drafts)
- **firecrawl_to_linear** · glm-5p3-flash · raw · epoch 10: expected exactly one tagged Linear issue, found 0
- **github_to_linear** · glm-5p3-flash · raw · epoch 8: GitHub #1727 has no comment naming its Linear issue

## Harness errors — excluded from the rates above

- **firecrawl_to_linear** · glm-5p3-flash · progressive · epoch 3: harness error: seed failed: WorldError: HTTP 409 — PUT https://api.github.com/repos/nqme-archive/harness-sandbox/contents/h83ab10/RUNBOOK.md failed
{"message":"is at 8362bcdcc6e5e089073d8e51c410b5ec5b02c9c6 but expected 72b0bc571da12de7f5d7650d38bb33fdc5b9cfa6","documentation_url":"https://docs.github.com/rest/repos/contents#create-or-update-file-contents","status":"409"}
- **github_to_linear** · glm-5p3-flash · progressive · epoch 9: harness error: seed failed: WorldError: HTTP 403 — POST https://api.github.com/repos/nqme-archive/harness-sandbox/issues failed
{"message":"You have exceeded a secondary rate limit and have been temporarily blocked from content creation. Please retry your request again later. For more on scraping GitHub and how it may affect your rights, please review our Terms of Service (https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) If you reach out to GitHub Support for help, please include the request ID E7E4:7D142:1A0D7D7:1911659:6AAAF8F7 and timestamp 2026-09-16 20:15:52 UTC.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api#about-secondary-rate-limits","status":"403"}
- **github_to_linear** · glm-5p3-flash · progressive · epoch 10: harness error: seed failed: WorldError: HTTP 403 — POST https://api.github.com/repos/nqme-archive/harness-sandbox/issues failed
{"message":"You have exceeded a secondary rate limit and have been temporarily blocked from content creation. Please retry your request again later. For more on scraping GitHub and how it may affect your rights, please review our Terms of Service (https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) If you reach out to GitHub Support for help, please include the request ID E7E4:7D142:1A11291:1914F94:6AAAF8FD and timestamp 2026-09-16 20:15:57 UTC.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api#about-secondary-rate-limits","status":"403"}
- **firecrawl_to_linear** · glm-5p3-flash · raw · epoch 1: harness error: seed failed: WorldError: HTTP 409 — PUT https://api.github.com/repos/nqme-archive/harness-sandbox/contents/h359f7e/RUNBOOK.md failed
{"message":"is at 8362bcdcc6e5e089073d8e51c410b5ec5b02c9c6 but expected 72b0bc571da12de7f5d7650d38bb33fdc5b9cfa6","documentation_url":"https://docs.github.com/rest/repos/contents#create-or-update-file-contents","status":"409"}
- **github_to_linear** · glm-5p3-flash · raw · epoch 9: harness error: seed failed: WorldError: HTTP 403 — POST https://api.github.com/repos/nqme-archive/harness-sandbox/issues failed
{"message":"You have exceeded a secondary rate limit and have been temporarily blocked from content creation. Please retry your request again later. For more on scraping GitHub and how it may affect your rights, please review our Terms of Service (https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) If you reach out to GitHub Support for help, please include the request ID E7C3:1DC456:18917B9:17A3C91:6AAAF8F0 and timestamp 2026-09-16 20:15:45 UTC.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api#about-secondary-rate-limits","status":"403"}
- **github_to_linear** · glm-5p3-flash · raw · epoch 10: harness error: seed failed: WorldError: HTTP 403 — POST https://api.github.com/repos/nqme-archive/harness-sandbox/issues failed
{"message":"You have exceeded a secondary rate limit and have been temporarily blocked from content creation. Please retry your request again later. For more on scraping GitHub and how it may affect your rights, please review our Terms of Service (https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) If you reach out to GitHub Support for help, please include the request ID E7C3:1DC456:189256F:17A49DF:6AAAF8F2 and timestamp 2026-09-16 20:15:46 UTC.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api#about-secondary-rate-limits","status":"403"}

## How to read this

- A run is one scenario-epoch. Success means the scenario's judge accepted the state read back from the real accounts after the agent finished; the transcript is never consulted for the verdict.
- A harness error is a run the agent never had a fair shot at: its seed or read-back failed, or the inference provider refused to serve the model (auth, billing, precondition, or the provider's own 5xx). Such a run is listed individually above and not counted for or against any model. A rate limit is not one of these - that is the harness's concurrency to retry - and neither is a 4xx from a target API, which is a result about the arm that built the request.
- stderr is the binomial standard error of the success rate over runs.
- Context bytes are the bytes of tool output handed back to the model, summed over a run. On the Charter arm this is after the packs' response trimming; on the raw arm it is the API's response body, capped at 100,000 bytes per call (truncations are counted).
- Tool errors on the Charter arm include calls rejected by schema validation before any request was sent.
- Same model settings, system prompt, task text, credentials, endpoint set (guard-enforced) and limits on every arm; only the tool surface differs.
