# Development process and attribution

## Origin

CampusBank began with the banking inquiry-agent functionality in a six-person CNSCC324 coursework group (Lab Class 1, Team 12). This repository curates the interactive portal and reproducible engineering checks for a personal portfolio. It excludes university assignment PDFs, report drafts, private keys, accounts, and live conversations.

## Owner-led interaction iterations

The portfolio owner, Zhou Yuxi, repeatedly specified desired behavior and identified problems in prototype use:

1. Move from scripted menus toward understanding naturally phrased goals and follow-up questions.
2. Support Chinese and English based on the current user's language.
3. Keep every turn visible and retain old conversations after creating a new chat.
4. Replace a minimal demo page with account-linked conversations, business categories, and guided service windows.
5. Offer human transfer from ordinary conversation and carry its context to a shared support queue.
6. Separate customer and staff identities, enforce permissions, and support users on different computers.
7. Publish a hosted group-testing version and correct customer views that exposed staff reply controls.

These iterations provide a concrete record of interaction requirements and engineering decisions. They are informal prototype feedback, not a structured participant study.

## AI-assisted engineering

AI coding assistance was used substantially to write and revise the implementation, investigate errors, prepare tests, and document the project. The owner's contribution is represented as interaction goals, iterative requirements, prototype feedback, and project direction; the repository does not claim every line was independently handwritten.

The original group context is acknowledged without inventing equal contributions, individual task assignments, or unverified member work. If the repository is included in an application, its owner should be ready to explain the tool loop, retrieval method, persistence model, role checks, evidence limitations, and the role of AI assistance.

## Reproducibility

The public snapshot uses a runtime dependency lock, synthetic knowledge, source-level tests, frontend workflow checks, a Dockerfile, and CI. Current verification evidence is distinguished from prospective research ideas. A passing test suite supports the tested behavior; it does not prove all model outputs or all deployment conditions are correct.
