# Security Software Daily Writing Framework

## 1. Source Judgment

Rank sources by decision value, not by convenience.

Tier 1: company direct evidence

- SEC filings, earnings calls, investor presentations.
- company press releases and official product pages.
- company blogs, security research blogs, docs changelog, release notes.
- customer case studies if they name product, deployment, or use case.

Use Tier 1 for direct impact. A direct item should usually name a company, product, customer, integration, financial event, legal event, or product capability.

Tier 2: high-signal external events

- CISA KEV, vendor advisories, major CVEs, ransomware campaigns, large breaches.
- AI model/product releases that change security workflows.
- cloud/platform ecosystem changes from AWS, Azure, GCP, GitHub, Anthropic, OpenAI, Google, Microsoft.
- regulatory or compliance changes.

Use Tier 2 for indirect impact. The report must explain why the event changes demand for a company or category.

Tier 3: market interpretation

- X/Twitter long-form investor pitches.
- analyst notes and expert commentary.
- high-quality practitioner threads.

Use Tier 3 to understand market framing, not as sole proof. If X is enabled, record who said it, what the claim is, and whether it is new versus repeated.

Tier 4: low-signal news

- syndicated rewrites, vague partnership blurbs, vendor awards, SEO news pages, low-detail conference announcements.

Usually exclude Tier 4 unless it confirms a higher-tier source.

## 2. Prior-Context Comparison

Each daily item should be compared against stored context:

- prior company thesis: What did we already believe about this company?
- prior category map: Which control layer does this touch: identity, access, endpoint/workload, cloud/app/code, data, SOC, recovery/compliance?
- prior evidence: Has this same company already announced similar capabilities?
- market expectation: Is this already consensus, or does it move the narrative?
- contradiction: Does the new event weaken a previous assumption?

Use one of these comparison outcomes:

- new thesis: introduces a new demand vector or product category.
- confirmation: supports an existing thesis with stronger evidence.
- extension: expands an existing product narrative into a new workflow or buyer.
- contradiction: conflicts with prior narrative or weakens a company/category.
- noise: not worth including in the daily.

## 3. Direct vs Indirect Impact

Direct impact examples:

- RBRK announces an Anthropic/Claude Code integration around agentic cyber resilience.
- PANW launches a CNAPP capability or reports customer traction.
- CRWD changes packaging, pricing, or expands Falcon modules.
- OKTA reports identity governance or PAM customer momentum.

Indirect impact examples:

- Anthropic releases a model or project that changes vulnerability discovery economics.
- A major breach increases demand for data security or backup recovery.
- A cloud platform changes identity, API, or marketplace behavior.
- A regulator increases audit or recovery requirements.
- A service firm makes a large OT security acquisition, signaling category budget movement.

The bridge must be explicit:

`external event -> changed enterprise risk/budget -> affected security workflow -> likely company/category read-through`.

## 4. Article Shape

Use a single article, not disconnected notes.

Recommended outline:

1. Title: one sentence naming the day's real theme.
2. Lead: 1-2 paragraphs explaining the theme and why today matters.
3. Body section 1: the most important direct event.
4. Body section 2: the most important indirect event.
5. Body section 3: other category signal if it changes budget or competition.
6. Synthesis: what changed versus prior context.
7. Watchlist: what to verify next.
8. Sources: links.

## 5. Writing Standards

Good paragraph:

> Rubrik's Anthropic/Claude Code work matters because it turns agent risk into a recovery workflow. The issue is not only that an AI assistant can write code; it is that the assistant may change configuration, touch sensitive data, or widen an incident before a human notices. If Rubrik can make that risk observable and reversible, the company can argue that cyber resilience extends beyond backup into agent-era operational recovery.

Bad paragraph:

> RBRK + Anthropic is important. Direct impact. Benefits cyber resilience.

## 6. Output Schema For The Backend

Recommended object fields:

- `date`
- `mode`
- `title`
- `summary_conclusion`
- `article_count_label`
- `event_count_label`
- `article_sections`
  - `heading`
  - `paragraphs`
- `items`
  - `title`
  - `impact_type`
  - `companies`
  - `source_ids`
- `sources`
  - `label`
  - `url`
  - `tier`
- `comparison_notes`
- `watchlist`

## 7. Daily Acceptance Test

Reject the draft if any of these are true:

- It is mostly bullets or headline fragments.
- It names tickers before explaining the mechanism.
- It contains "direct" or "indirect" labels without reasoning.
- It cannot be understood without clicking sources.
- It does not say what changed versus previous context.
- It includes more than five events without a clear ranking.
