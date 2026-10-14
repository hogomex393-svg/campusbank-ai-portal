# Prospective research directions

**Status: proposed work.** CampusBank is presently an applied AI and interaction-design prototype. The questions below describe possible studies, with no claimed results.

## 1. Does an intent-aware service agent help users reach the next step?

Compare agent-plus-service-buttons with a retrieval-answer interface on matched tasks such as account selection, required documents, a lost card, and online application guidance. Define successful completion against the synthetic service catalog before collecting data. Measure task completion, steps, clarification turns, unnecessary actions, and time to a correct confirmed service window.

Use counterbalanced tasks and consistent underlying knowledge. Report the exact model/version, prompt, token budget, latency, and API cost. Manual reviewers should distinguish factual correctness from fluent language.

## 2. How much context is lost during human handoff?

Compare context-linked handoff with a form that asks customers to restate the problem. Measure repeated information, time to a staff response that addresses the goal, and staff-rated context completeness. Use synthetic scenarios and separately measure waiting time versus interaction time. Do not describe queued messages as a human response before a staff participant actually replies.

## 3. How does bilingual switching affect grounding and dialogue continuity?

Construct matched Chinese/English tasks with mid-conversation switches, paraphrases, and language-neutral slot answers. Hold expected facts and service outcomes fixed. Assess grounded factual content, clarification relevance, language consistency, source support, and action correctness. Establish an unseen evaluation split and have independent reviewers score valid paraphrases rather than rely solely on keywords.

## 4. Do role-aware views clarify responsibility?

Study whether users can identify which messages came from AI or staff, who can answer a ticket, and whether a service action has merely been prepared or actually confirmed. Include completed-ticket states and staff draft preservation. Collect task-based comprehension and usability observations, with informed consent and institutional guidance if required.

## Suggested study outputs

A useful next release would publish a preregistered or clearly dated protocol, task materials, anonymized synthetic evaluation cases, scoring rubrics, model settings, cost/latency distributions, and error categories. Participant data should be collected and shared only under the applicable consent and privacy process. Report small samples and negative results explicitly.

The current repository establishes the system on which those experiments could run. It does not establish that this design improves user satisfaction or constitutes a novel research contribution.
