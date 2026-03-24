# Web Structure Guide

This document is the current structure contract for the web app in this repository.

Goal: reduce future technical debt without changing the existing product architecture, page behavior, or stored results.

## Current Principle

The project is intentionally still a single-process Flask app with:

- one backend entry file: `app.py`
- server-rendered HTML in `templates/`
- shared frontend styles in `static/style.css`
- page-specific behavior in page-scoped JavaScript files under `static/`
- JSON and file-backed persistence under `data/`, `uploads/`, `logs/`, and `reports/`

Do not split this into blueprints, packages, or SPA layers unless there is a deliberate migration plan. For now, the safer rule is: keep boundaries clear inside the current structure instead of introducing a second architecture.

## Repository Layout

```text
app.py                         Flask entrypoint, route layer, store helpers, domain logic
monitor_runner.py              Monitor worker launcher target
signal_monitor_runner.py       Signal monitor worker launcher target
oss_client.py                  OSS integration helper
tingwu_client.py               Tingwu integration helper

templates/                     Server-rendered page templates and shared partials
static/                        Shared CSS and page-specific JavaScript
data/                          Persistent JSON stores and runtime state
uploads/                       User-uploaded files
reports/                       Local report source fallback
logs/                          Monitor and runtime logs
output/                        Local verification artifacts and generated checks
tools/                         Utility scripts and helpers
```

## Frontend Shell

Shared shell lives in:

- `templates/_masthead.html`
- `templates/_theme_bootstrap.html`
- `static/style.css`
- `static/workspace-rail.js`
- `static/theme-switcher.js`
- `static/flash-messages.js`
- `static/calendar-modal.js`
- `static/confirm-modal.js`

Rule: if a behavior is used by multiple top-level pages, add it to the shared shell. If it is specific to one page, keep it in that page's own script.

## Page Map

Top-level pages and their main assets:

| Area | Route | Template | Primary JS |
| --- | --- | --- | --- |
| Reports home | `/` | `templates/index.html` | `static/stock-workspace.js`, `static/report-sources.js` |
| Stock workspace | `/stocks` | `templates/stocks.html` | `static/stock-workspace.js` |
| Stock detail | `/stocks/<symbol>` | `templates/stock_detail.html` | `static/stock-workspace.js`, `static/stock-detail-tabs.js`, `static/stock-detail-reader.js`, `static/rich-editor.js` |
| Stocks calendar | `/stocks/calendar` | `templates/stocks_calendar.html` | `static/calendar-page.js` |
| Schedule | `/schedule` | `templates/schedule.html` | `static/schedule-page.js`, `static/stock-workspace.js` |
| Experts | `/experts` | `templates/experts.html` | `static/experts-page.js`, shared stock/detail scripts |
| Transcript center | `/transcripts` | `templates/transcripts.html` | `static/transcript-page.js`, shared stock/detail scripts |
| AI chat | `/ai` | `templates/ai.html` | `static/ai-chat.js` |
| Research mindmap | `/mindmaps` | `templates/mindmaps.html` | `static/mindmap-workspace.js` |
| Mindmap studio lab | `/labs/mindmap-studio` | `templates/mindmap_studio.html` | `static/mindmap-studio.js`, `static/mindmap-studio.css` |
| Monitor | `/monitor` | `templates/monitor.html` | `static/monitor-page.js`, `static/stock-workspace.js` |
| Signal monitor | `/signals` | `templates/signal_monitor.html` | `static/signal-monitor-page.js`, `static/stock-workspace.js` |
| Export center | `/exports` | `templates/exports.html` | `static/export-center.js` |
| Search | `/search` | `templates/search.html` | `static/stock-workspace.js` |
| Trash | `/trash` | `templates/trash.html` | `static/trash-page.js`, `static/stock-workspace.js` |

Rule: each page should have one obvious frontend owner. If a new page is added, prefer:

1. one template
2. one page-specific JS file
3. shared partials only for truly reused UI

## Backend Domain Boundaries

`app.py` currently contains several route domains. Keep new work inside the nearest existing domain instead of scattering helpers randomly.

Suggested boundary map:

- Reports and homepage: `/`, `/files/...`
- Monitor: `/monitor...`
- Signal monitor: `/signals...`
- Stocks and earnings: `/stocks...`
- Schedule: `/schedule...`
- Experts: `/experts...`
- Search and trash: `/search`, `/trash...`
- Transcripts: `/transcripts...`
- AI chat: `/ai...`
- Research mindmaps: `/mindmaps...`
- Mindmap studio lab: `/labs/mindmap-studio...`

Rule: new helpers should sit close to the route family that uses them. Avoid creating cross-domain helpers unless they are clearly shared across at least two route families.

## Persistence Boundaries

Current persistent stores:

- `data/stocks.json`: stock workspace state, notes, groups, files, earnings
- `data/ai_chats.json`: AI chat sessions
- `data/ai_context/`: AI context snapshots and exports
- `data/mindmaps.json`: generated research mindmap records
- `data/mindmap_context/`: generated mindmap context payloads
- `data/mindmap_studio.json`: editable studio documents
- `data/monitor/`: monitor config, runtime, prompts, trash
- `data/signal_monitor/`: signal monitor config, runtime, prompts, reports, trash
- `uploads/stocks/`: stock-linked uploads
- `uploads/transcripts/`: transcript source files
- `reports/` or external `REPORTS_DIR`: report source files
- `logs/monitor/` and `logs/signal_monitor/`: runner logs

Rule: each top-level feature should own one primary store. If a feature needs to project data into another store, do it through an explicit sync helper instead of writing to both places inline throughout the code.

## Frontend Change Rules

To avoid debt buildup, keep using these rules:

- Shared styling stays in `static/style.css`.
- A separate CSS file is allowed only for a truly isolated lab surface such as `mindmap-studio.css`.
- Page-specific interactions belong in a page-scoped JS file, not in `_masthead.html`.
- Shared UI utilities belong in one of the existing shared shell scripts.
- When a template adds a new page-specific asset, keep the asset reference next to the page template instead of hiding it in a global include.
- Keep cache-busting version strings per-template when assets change.

## Safe Way To Add A New Module

When adding a new top-level module, follow this order:

1. Add one new route family in `app.py`.
2. Add one new page template in `templates/`.
3. Add one page-scoped script in `static/` if the page has interaction.
4. Reuse `_masthead.html` and `_theme_bootstrap.html`.
5. Add one primary JSON store only if the feature truly owns persistent state.
6. Document the new module in this file and in `README.md`.

Avoid:

- adding logic for a page into another page's JS file
- adding multiple unrelated stores for the same feature
- writing feature-specific behavior into the shared shell unless at least two pages need it
- creating hidden side effects between stocks, schedule, AI, and mindmap stores without a named sync function

## Mindmap-Specific Guardrails

The research mindmap stack now has two layers by design:

- `mindmaps`: generated, source-grounded research output
- `mindmap_studio`: editable follow-up workspace

Keep those layers separate:

- generated output remains the baseline record
- studio edits remain the editable working layer
- synchronization between them should go through dedicated sync helpers, not ad hoc field copying

## What We Are Intentionally Not Doing Yet

These may become valid later, but should not be done casually:

- splitting `app.py` into packages
- moving to a frontend framework
- introducing an ORM or database migration layer
- turning shared CSS into a design system rewrite
- replacing server-rendered templates with API-first pages

Those are migration decisions, not cleanup tasks.

## Maintenance Checklist

Before merging a new web feature, check:

- Does the page have one obvious template owner?
- Does the interaction live in one obvious JS owner?
- Is persistence written to one primary store?
- Are shared utilities reused instead of duplicated?
- Was this document updated if a new module or store was introduced?

If the answer to any of those is no, the feature is probably adding avoidable debt.
