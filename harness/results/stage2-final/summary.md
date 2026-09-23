# Campaign `stage2-final`

## Headline — task success by (model, arm)

| model | arm | runs | success | rate | ± stderr | tool calls/run | tool errors/run | guard rejections | truncations | context bytes/run | tokens/run | wall s/run | errors | limits | harness errors |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| glm-5p3-flash | progressive | 110 | 109 | 99% | 0.009 | 7.22 | 0.29 | 0 | 0 | 7,382 | 75,817 | 46.3 | 0 | 2 | 0 |
| glm-5p3-flash | raw | 110 | 105 | 95% | 0.020 | 7.43 | 0.47 | 4 | 3 | 36,383 | 112,336 | 96.4 | 0 | 4 | 0 |

## Per template — successes / runs, variants rolled up

| scenario | glm-5p3-flash · progressive | glm-5p3-flash · raw |
|---|---:|---:|
| calendar_cleanup | 7/7 | 7/7 |
| calendar_to_doc | 7/7 | 7/7 |
| doc_to_gmail_draft | 7/7 | 2/7 |
| firecrawl_to_linear | 6/6 | 6/6 |
| github_to_linear | 6/7 | 7/7 |
| gmail_label_sweep | 6/6 | 6/6 |
| inbox_to_sheet | 7/7 | 7/7 |
| linear_to_slack_digest | 7/7 | 7/7 |
| linear_triage | 7/7 | 7/7 |
| pr_to_doc | 7/7 | 7/7 |
| sheet_to_calendar | 7/7 | 7/7 |
| sheet_to_stripe_refunds | 7/7 | 7/7 |
| shopify_customer_to_stripe | 7/7 | 7/7 |
| shopify_low_stock_to_github | 7/7 | 7/7 |
| slack_thread_to_github | 7/7 | 7/7 |
| stripe_to_sheet | 7/7 | 7/7 |

## Per scenario — successes / runs

| scenario | glm-5p3-flash · progressive | glm-5p3-flash · raw |
|---|---:|---:|
| calendar_cleanup | 1/1 | 1/1 |
| calendar_cleanup@all_but_one | 1/1 | 1/1 |
| calendar_cleanup@cancelled_last | 1/1 | 1/1 |
| calendar_cleanup@decoy_title | 1/1 | 1/1 |
| calendar_cleanup@one_of_three | 1/1 | 1/1 |
| calendar_cleanup@six | 1/1 | 1/1 |
| calendar_cleanup@three_of_five | 1/1 | 1/1 |
| calendar_to_doc | 1/1 | 1/1 |
| calendar_to_doc@close_times | 1/1 | 1/1 |
| calendar_to_doc@five | 1/1 | 1/1 |
| calendar_to_doc@four | 1/1 | 1/1 |
| calendar_to_doc@reverse_order | 1/1 | 1/1 |
| calendar_to_doc@same_hour | 1/1 | 1/1 |
| calendar_to_doc@two | 1/1 | 1/1 |
| doc_to_gmail_draft | 1/1 | 0/1 |
| doc_to_gmail_draft@long | 1/1 | 0/1 |
| doc_to_gmail_draft@shipping | 1/1 | 1/1 |
| doc_to_gmail_draft@shipping_with_distractors | 1/1 | 1/1 |
| doc_to_gmail_draft@short | 1/1 | 0/1 |
| doc_to_gmail_draft@two_distractor_threads | 1/1 | 0/1 |
| doc_to_gmail_draft@with_distractor_thread | 1/1 | 0/1 |
| firecrawl_to_linear | 1/1 | 1/1 |
| firecrawl_to_linear@code_block | 1/1 | 1/1 |
| firecrawl_to_linear@decoy_h2 | 1/1 | 1/1 |
| firecrawl_to_linear@long_heading | 1/1 | 1/1 |
| firecrawl_to_linear@postmortem | 1/1 | 1/1 |
| firecrawl_to_linear@roadmap | 1/1 | 1/1 |
| github_to_linear | 1/1 | 1/1 |
| github_to_linear@awkward_titles | 1/1 | 1/1 |
| github_to_linear@five | 1/1 | 1/1 |
| github_to_linear@four | 1/1 | 1/1 |
| github_to_linear@two | 0/1 | 1/1 |
| github_to_linear@two_with_distractors | 1/1 | 1/1 |
| github_to_linear@with_distractors | 1/1 | 1/1 |
| gmail_label_sweep | 1/1 | 1/1 |
| gmail_label_sweep@eight | 1/1 | 1/1 |
| gmail_label_sweep@six | 1/1 | 1/1 |
| gmail_label_sweep@six_with_distractors | 1/1 | 1/1 |
| gmail_label_sweep@two | 1/1 | 1/1 |
| gmail_label_sweep@with_distractors | 1/1 | 1/1 |
| inbox_to_sheet | 1/1 | 1/1 |
| inbox_to_sheet@eight | 1/1 | 1/1 |
| inbox_to_sheet@seven | 1/1 | 1/1 |
| inbox_to_sheet@three | 1/1 | 1/1 |
| inbox_to_sheet@three_with_distractors | 1/1 | 1/1 |
| inbox_to_sheet@two | 1/1 | 1/1 |
| inbox_to_sheet@with_distractors | 1/1 | 1/1 |
| linear_to_slack_digest | 1/1 | 1/1 |
| linear_to_slack_digest@five | 1/1 | 1/1 |
| linear_to_slack_digest@five_with_distractors | 1/1 | 1/1 |
| linear_to_slack_digest@long_titles | 1/1 | 1/1 |
| linear_to_slack_digest@six | 1/1 | 1/1 |
| linear_to_slack_digest@two | 1/1 | 1/1 |
| linear_to_slack_digest@with_distractors | 1/1 | 1/1 |
| linear_triage | 1/1 | 1/1 |
| linear_triage@all_urgent | 1/1 | 1/1 |
| linear_triage@eight | 1/1 | 1/1 |
| linear_triage@none_urgent | 1/1 | 1/1 |
| linear_triage@one_urgent | 1/1 | 1/1 |
| linear_triage@three_urgent_of_six | 1/1 | 1/1 |
| linear_triage@urgent_mid_title | 1/1 | 1/1 |
| pr_to_doc | 1/1 | 1/1 |
| pr_to_doc@deep_paths | 1/1 | 1/1 |
| pr_to_doc@five | 1/1 | 1/1 |
| pr_to_doc@four | 1/1 | 1/1 |
| pr_to_doc@similar_names | 1/1 | 1/1 |
| pr_to_doc@six | 1/1 | 1/1 |
| pr_to_doc@two | 1/1 | 1/1 |
| sheet_to_calendar | 1/1 | 1/1 |
| sheet_to_calendar@afternoon | 1/1 | 1/1 |
| sheet_to_calendar@early_late | 1/1 | 1/1 |
| sheet_to_calendar@five_odd_minutes | 1/1 | 1/1 |
| sheet_to_calendar@four | 1/1 | 1/1 |
| sheet_to_calendar@long_blocks | 1/1 | 1/1 |
| sheet_to_calendar@two | 1/1 | 1/1 |
| sheet_to_stripe_refunds | 1/1 | 1/1 |
| sheet_to_stripe_refunds@all_full | 1/1 | 1/1 |
| sheet_to_stripe_refunds@all_partial | 1/1 | 1/1 |
| sheet_to_stripe_refunds@five | 1/1 | 1/1 |
| sheet_to_stripe_refunds@four | 1/1 | 1/1 |
| sheet_to_stripe_refunds@odd_cents | 1/1 | 1/1 |
| sheet_to_stripe_refunds@two | 1/1 | 1/1 |
| shopify_customer_to_stripe | 1/1 | 1/1 |
| shopify_customer_to_stripe@accented | 1/1 | 1/1 |
| shopify_customer_to_stripe@accented_with_lookalike | 1/1 | 1/1 |
| shopify_customer_to_stripe@apostrophe | 1/1 | 1/1 |
| shopify_customer_to_stripe@hyphenated | 1/1 | 1/1 |
| shopify_customer_to_stripe@long_name | 1/1 | 1/1 |
| shopify_customer_to_stripe@with_lookalike | 1/1 | 1/1 |
| shopify_low_stock_to_github | 1/1 | 1/1 |
| shopify_low_stock_to_github@all_low | 1/1 | 1/1 |
| shopify_low_stock_to_github@boundary_ten | 1/1 | 1/1 |
| shopify_low_stock_to_github@one_low | 1/1 | 1/1 |
| shopify_low_stock_to_github@six | 1/1 | 1/1 |
| shopify_low_stock_to_github@threshold_one | 1/1 | 1/1 |
| shopify_low_stock_to_github@two | 1/1 | 1/1 |
| slack_thread_to_github | 1/1 | 1/1 |
| slack_thread_to_github@five_replies | 1/1 | 1/1 |
| slack_thread_to_github@four_replies | 1/1 | 1/1 |
| slack_thread_to_github@invoice_bug | 1/1 | 1/1 |
| slack_thread_to_github@login_bug | 1/1 | 1/1 |
| slack_thread_to_github@one_reply | 1/1 | 1/1 |
| slack_thread_to_github@two_replies | 1/1 | 1/1 |
| stripe_to_sheet | 1/1 | 1/1 |
| stripe_to_sheet@eight | 1/1 | 1/1 |
| stripe_to_sheet@no_distractor | 1/1 | 1/1 |
| stripe_to_sheet@six | 1/1 | 1/1 |
| stripe_to_sheet@six_three_distractors | 1/1 | 1/1 |
| stripe_to_sheet@three_distractors | 1/1 | 1/1 |
| stripe_to_sheet@two | 1/1 | 1/1 |

## Failures, with the judge's reason

- **github_to_linear@two** · glm-5p3-flash · progressive · epoch 1: GitHub #1656 has no comment naming its Linear issue; GitHub #1657 has no comment naming its Linear issue
- **doc_to_gmail_draft** · glm-5p3-flash · raw · epoch 1: draft is addressed to '"Ada Lovelace  Subject: Re: [h3334f2] Invoice balance looks wrong" <ada.h3334f2@hars.invalid>', not the sender
- **doc_to_gmail_draft@long** · glm-5p3-flash · raw · epoch 1: draft is addressed to 'ada.ha’0a27@harness.invalid', not the sender
- **doc_to_gmail_draft@short** · glm-5p3-flash · raw · epoch 1: draft is addressed to 'ada.hf19b7f@harness.invalie', not the sender
- **doc_to_gmail_draft@two_distractor_threads** · glm-5p3-flash · raw · epoch 1: draft is addressed to 'ada.h44a343@harness.invalie', not the sender
- **doc_to_gmail_draft@with_distractor_thread** · glm-5p3-flash · raw · epoch 1: expected exactly one draft on the thread, found 0 (of 0 drafts)

## How to read this

- A run is one scenario-epoch. Success means the scenario's judge accepted the state read back from the real accounts after the agent finished; the transcript is never consulted for the verdict.
- A harness error is a run the agent never had a fair shot at: its seed or read-back failed, or the inference provider refused to serve the model (auth, billing, precondition, or the provider's own 5xx). Such a run is listed individually above and not counted for or against any model. A rate limit is not one of these - that is the harness's concurrency to retry - and neither is a 4xx from a target API, which is a result about the arm that built the request.
- stderr is the binomial standard error of the success rate over runs.
- Context bytes are the bytes of tool output handed back to the model, summed over a run. On the Charter arm this is after the packs' response trimming; on the raw arm it is the API's response body, capped at 100,000 bytes per call (truncations are counted).
- Tool errors on the Charter arm include calls rejected by schema validation before any request was sent.
- Same model settings, system prompt, task text, credentials, endpoint set (guard-enforced) and limits on every arm; only the tool surface differs.
