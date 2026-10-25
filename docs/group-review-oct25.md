# Group-review fixes and self-audit — v2.6.0

This release addresses six reported issues from the 25 October group review. All banking data and operations remain fictional.

| Item | Implemented change | Verification |
| --- | --- | --- |
| I01: chat and FX preview disagree | Chat tools, preview and receipts share a decimal calculator and data/transfer_policy.json. Fixed fictional EUR/USD quotes include principal, fee, total and recipient estimate. A bounded consistency check detects unsupported-FX claims and labelled numeric contradictions. | Calculator parity, numeric guards, edited amounts, currency context and a real model sample. |
| I02: loans appear after being excluded | Explicit exclusions persist, filter tools/evidence/buttons, and can be reversed by a later preference. Funding type is single-select, with actual study-level prefill. | Chinese/English negation, follow-ups, reversal and a forbidden tool-call test. |
| I03: unrelated follow-ups and sources | FAQ retrieval filters products, topics and requested attributes. Lost-card suggestions stay on task. Source metadata includes readable titles and stable fingerprints. | Product-source isolation and card-procedure relevance tests. |
| I04: classroom rate limits | Operator-configured customer accounts receive 18 questions/minute. Ordinary accounts retain 6/minute; global 30/minute and 240/hour limits remain. Retry delays preserve input/send IDs; queue/server/model timing is distinguished. | Rate boundaries/retries and a 20-minute SIMULATED-CLOCK classroom pace. This is not a timed live presentation. |
| I05: phone menu and helper text | Close button, outside overlay click and Escape close the sidebar. Helper text is at least 12px at the tested breakpoint. | Actual 375x812 browser check, DOM interactions, and no horizontal page overflow. |
| I06: test access and accumulated data | Existing staff-test access remains configurable. Classroom access is customer-only. Chats and ended requests can be archived/restored; staff can filter archived applications. | Owner isolation, no new admin rights, reversible archive tests. Existing records are retained. |

## Additional improvements

- Answer feedback: helpful/unhelpful controls, reason and optional comment are saved per answer/owner. scripts/export_feedback.py exports aggregate counts without names, comments or chats.
- Original-request supplementation/withdrawal: owners can update requests marked as needing information. The same reference, before/after revision and event timeline remain. Completed/withdrawn requests cannot be changed by a late staff action.
- Conversational slots: missing fields are identified, short replies fill the pending field, edits retain known values, and currency context selects the matching fictional scenario.
- Evaluation export: 50 authored bilingual cases (59 turns) cover direct questions, follow-ups, edits, exclusions, slots and boundaries. JSON/CSV include expected structured checks, answers, source versions, backend/wall time and API usage. Formula-like CSV strings are neutralized.

## Evidence and limits

133 Python tests and four DOM scripts pass. The API-free run covers 59 turns in 50 cases. Five critical cases yield 10 turns in each of Agent, RAG, LLM and Offline: all 40 structured proxy rows pass, with no API errors, using 35 provider calls. These are authored regression checks, NOT overall answer accuracy or independent user-study results. Human-rating columns remain blank for later scoring. Recorded replies were inspected for numeric, UI and source consistency.

All modes share portal constraints, drafts and the fictional calculator. Agent adds tools; RAG supplies filtered FAQ evidence; LLM omits FAQ retrieval; Offline uses local logic. This is an application-level comparison, not a completely unassisted-model baseline. The earlier 80-question benchmark predates the new filters and remains historical evidence.

## Reproduce

```powershell
python -m unittest discover -v
node scripts/verify_frontend.mjs
node scripts/verify_streaming.mjs
node scripts/verify_scenarios.mjs
node scripts/verify_review_ui.mjs
python -m evaluation.group_review --modes offline --output evaluation/results/group_review_offline
```

Online sampling requires a privately configured API key and explicit cost opt-in:

```powershell
python -m evaluation.group_review --online --modes agent,rag,llm,offline --ids FX_ZH,NEG_ZH,LOST_ZH,STUDENT_EN,LANGUAGE_SWITCH --max-api-calls 80 --output evaluation/results/group_review_matched
```

Classroom settings: BANKBOT_DEMO_ACCOUNTS (comma-separated existing customer usernames), BANKBOT_DEMO_RPM=18, BANKBOT_GLOBAL_RPM=30, BANKBOT_HOURLY_REQUESTS=240. The request cap is not a provider billing guarantee. Credentials belong in private storage. BANKBOT_OPEN_STAFF_TESTING controls test staff access independently.
