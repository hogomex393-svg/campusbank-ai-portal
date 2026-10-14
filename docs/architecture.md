# Architecture and AI integration

## Components

The browser uses plain HTML, CSS, and JavaScript. FastAPI serves the interface and JSON endpoints. A SQLite store holds users, hashed sessions, chats, messages, service requests, tickets, and staff invitations. One server instance is used in the current deployment.

The model service is separate from the portal. This allows the CLI, web interface, evaluation harness, and test fixtures to use the same dialogue/retrieval/orchestration implementation.

## One AI turn

1. Validate the session, active role, message, chat ownership, and send identifier.
2. If support is waiting or active, append the message to support context without making a model call.
3. Otherwise determine Chinese/English language and build recent dialogue context. The default model context retains six complete dialogue turns; storage retains the full conversation.
4. Run the requested mode. Agent mode lets DeepSeek request approved tools within a bounded round/time budget. RAG supplies retrieved records before generation; LLM mode omits factual retrieval; offline uses local logic.
5. Validate tool names/arguments and execute local tools. The model does not receive arbitrary system access. Preserve reasoning content required for model tool-message continuity.
6. Validate the generated answer's language. If it differs from the target, ask the model once to rewrite the same supported content in that language, without tools and within the remaining time budget. Persist only the final answer; include correction calls in usage metadata. A failed correction uses a labeled fallback.
7. Return an answer, source identifiers, tool traces, mode, token usage, latency, and approved UI actions. On API failure, expose sanitized failure metadata with a labeled offline fallback.
8. Persist the user and assistant messages. Duplicate send identifiers do not create repeated turns.

## Tools and retrieval

| Tool | Data or action |
| --- | --- |
| `search_bank_faq` | Rank synthetic FAQ records and return supported facts. |
| `get_product_info` | Read a structured product record. |
| `find_branch` | Read fictional branch addresses and opening hours. |
| `open_service_window` | Return a catalog-approved window/button; it does not submit a request. |

FAQ ranking uses separate Chinese/English indexes over questions and aliases. Word unigram/bigram TF-IDF cosine similarity contributes **0.8** and character `char_wb` 3–5-gram similarity contributes **0.2**. Synonym normalization helps match everyday phrasing. Scores aggregate by canonical FAQ ID, with optional product filtering. This is lexical retrieval, without a vector database, embeddings, or a learned multilingual retriever.

Explicit requests for a human also have a deterministic UI-action safeguard. This helps ensure a handoff button appears even if the model omits a tool call; it is not a general intent classifier.

## Authentication and authorization

- Passwords use salted PBKDF2-HMAC-SHA256 with 600,000 iterations. Session tokens are stored as hashes; cookies are HttpOnly, SameSite Strict, and Secure in cloud mode.
- Mutations validate CSRF and origin. Responses include a self-origin content policy and frame/content-type protections.
- Customer records require ownership. Staff endpoints require both staff capability and an active staff session role.
- Staff claim/reply operations check assignment atomically. Other assigned staff cannot send replies as the ticket owner. Resolved tickets are read-only.
- Cloud staff initialization requires a private owner bootstrap code. Staff invitations are single-use and expire after 24 hours. Group testing registration uses a separate private code.
- Cloud model quotas are 6 questions/account/minute and 30/service/minute. The limiter is process-local, supporting the current single-instance configuration.

These controls have automated coverage; this is not a security audit or a certified banking system.

## Persistence and synchronization

SQLite uses WAL and transactional operations. Cloud storage mounts `/data`; the database path is `/data/portal.sqlite3`. Provider restart persistence was checked. Visible customer/staff pages poll every three seconds; updates preserve selected context and unfinished staff replies. The implementation does not use WebSockets.

For larger deployments, external relational storage, centralized quotas, push events, structured operational monitoring, and account recovery would need further work.
