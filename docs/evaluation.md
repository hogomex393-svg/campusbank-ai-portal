# Evaluation: what the evidence supports

## Automated behavior checks

The 82-test Python suite covers system behavior, bilingual logic, natural dialogue/history regressions, portal accounts, shared support, password recovery, cloud configuration, and customer/staff role separation. Model calls are stubbed in unit/integration tests; these tests do not establish DeepSeek answer quality.

The frontend script uses jsdom and mocked HTTP. It checks that earlier chats/messages remain available; service forms submit after confirmation; support controls respect the active role and status; customer updates preserve staff reply drafts; and user/model HTML is escaped. It is a workflow regression suite, not a visual browser test or a human usability study.

The cloud workflow adds a Linux image build and disposable Docker smoke test. It creates synthetic customer/owner/staff accounts, verifies support messages, restarts the container, and checks persistence. CI does not receive a production API key or real accounts.

## Authored FAQ benchmark

Frozen output: [offline_queries.json](evidence/offline_queries.json). Run: **2026-10-14**, Python 3.13.3. FAQ SHA-256: `99acfc0f662cc8366b52e2127a88978dbacd1a894df93477c6dcff011ca2546f`.

These historical hashes cover raw Windows file bytes. The Git repository normalizes text to LF, so a clone on another system can have a different byte hash while retaining the same logical knowledge records. Record the hash and line-ending convention when comparing runs.

| Metric | Result | Meaning |
| --- | --- | --- |
| Queries | 80 | Authored inputs in this repository; not an independently sampled population. |
| Retrieval-scorable queries | 78 | Queries with expected FAQ identifiers. |
| Hit@1 | 49/78, 62.82% | The highest-ranked FAQ matches an expected FAQ. |
| Hit@3 | 72/78, 92.31% | At least one expected FAQ appears among the top three. |
| Lexical key-point pass | 57/80, 71.25% | Answer text matches required keyword groups. |
| API calls / tokens | 0 / 0 | This run is entirely offline. |

Retrieval Hit@3 is **not** answer accuracy. Keyword matching can accept an unhelpful answer or reject a valid paraphrase, especially across languages. The gap between retrieval and the offline response proxy is a reason to inspect answer construction rather than report one overall “AI accuracy” percentage. These cases have already informed development and are not a held-out test set.

Reproduce with `python -m evaluation.run --mode offline`. For conversation cases, add `--dialogues`. New results go to `evaluation/results/`; frozen evidence remains separate.

## Small online bilingual regression

Frozen output: [bilingual_agent.json](evidence/bilingual_agent.json). Run: **2026-10-11**, model `deepseek-v4-pro`, same FAQ hash as above. Eight authored turns check language switching, short contextual city replies, and selected facts. Recorded result: 8/8 language checks, 8/8 lexical key-point checks, 12 API calls, no errors.

This confirms that the configured API was exercised in that pilot. It cannot establish general factuality, naturalness, robustness, or user satisfaction. Outputs depend on provider/model configuration and may change on rerun.

### Later observed language-following failure

During hosted verification on **2026-10-14**, a Chinese request opened the account-application window correctly. The next user message was “Before I apply, what documents do I need? Please keep it brief.” The recorded mode was `agent`, the requested response language was `en`, `get_product_info` was called, and two actual API calls completed without error. However, the generated answer remained Chinese.

This was a failed live language-switch case in version 2.2.1. Detection and API connectivity succeeded, while the generated output did not follow the requested language. [Sanitized case metadata](evidence/live_language_regression.json) and [the visible failure](assets/language-drift.png) are retained as historical evidence.

### Fix and post-fix regression (version 2.2.2)

The service now compares the actual output language with the current turn's target. A mismatch triggers one model correction without tools, within the original time budget. The correction preserves grounded meaning and replaces the answer in stored dialogue; its internal instruction does not enter visible or future conversation history. If correction fails, the response uses a labeled fallback in the current language. API usage includes the correction call.

[bilingual_after_language_fix.json](evidence/bilingual_after_language_fix.json) records **10/10 language checks, 10/10 lexical key-point checks, 18 actual API calls, one successful language correction, and no errors** on 2026-10-14. The added two-turn case reproduces the service-window → English-documents sequence. Its English follow-up triggered correction and returned an English answer. Seven added automated regressions check both switch directions, valid mixed prose, bounded attempts/time, included usage, failure fallback, and clean history; the complete Python suite now has 82 tests.

The language check is a Chinese/English text heuristic, not a general multilingual quality judge. This small post-fix regression supports the repaired scenario; it does not guarantee every future answer's language or factuality. The original eight-turn evidence remains a dated pre-fix observation.

Optional rerun: `python -m evaluation.check_bilingual --online`. Agent/RAG/LLM baseline inquiry runs use `python -m evaluation.run --mode agent` (or `rag`, `llm`); the default online run is eight cases. These commands consume your API quota. Comparisons require identical case sets, knowledge hashes, sampling settings, and declared scoring criteria.

## Hosted deployment observations

[cloud_validation.json](evidence/cloud_validation.json) records version 2.2.1 checks: HTTPS health, secure cookies, first-customer privilege separation, actual DeepSeek agent responses, handoff creation, records retained after a provider restart, and customer support history without staff reply inputs. Screenshots are visual evidence of selected states, not a continuous uptime record.

[post_fix_hosted.json](evidence/post_fix_hosted.json) records the subsequent version 2.2.2 deployment and browser check: an existing synthetic account and earlier chats remained available, and the original Chinese-service → English-documents sequence returned an English answer in online agent mode with one recorded correction and no error.

## Remaining evidence to collect

No independent user study, accessibility review, prompt-injection evaluation, or production security assessment has been completed. The research plan proposes task completion, role clarity, handoff context loss, multilingual grounding, and cost/latency measurements. Publish those as future work until a documented experiment is actually conducted.
