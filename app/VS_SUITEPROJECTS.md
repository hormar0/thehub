# The Hub vs NetSuite SuiteProjects — feature comparison

Based on the SuiteProjects datasheet summary (PSA module paired with NetSuite CRM/HR/ERP).

| Area | NetSuite SuiteProjects (datasheet) | The Hub (this app) |
|---|---|---|
| Positioning | Full PSA inside NetSuite ERP/CRM/HR — opp → delivery → invoicing → rev rec, no double entry | Standalone, zero-dependency program/milestone control center (Python stdlib + SQLite); integrates outward (task apps, Drive, Teams webhook) instead of embedding an ERP |
| Project management | Shared always-current project status; manager home dashboard with reminders, milestone status, KPIs, billing forecast gauge | Dashboard (KPIs, attention list), Gate Rail, Register, Kanban, Roadmap, per-gate printable reports, MRF readiness scoring |
| Milestone/gate governance | Milestone status on the PM dashboard | Dedicated gate model: entry/exit criteria, evidence contract per gate, named Gate Chair decision, enforced conditions carried to next gate, MRF evidence-derived RAG (computed server-side, never hand-entered) |
| Resource management | Staffing, bench-time reduction, skills matching, allocation grid, availability + skill search | Users table (name/email/phone/username/project), responsible-user assignment per deliverable, hours by owner; allocation grid = not built |
| Time & expense | Timesheets + expense reports, office and mobile | Time reporting with week, owner, deliverable **or project/sub-project** (settings toggle), WBS structure; expenses = not built |
| Billing / invoicing | Invoices, recurring T&M, fixed-fee, bill on completion/milestone/date schedule | Not applicable / not built (out of scope for a milestone hub) |
| Revenue recognition | Advanced Revenue Management, automatic per-project allocation | Not built |
| Project accounting / profitability | Links project activity to financials | Grades A–F + evidence links per deliverable, traffic lights, MRF score; financials = not built |
| Analytics | Project360, configurable dashboards: utilisation, margins, budget vs actual, portfolio health | Dashboard, Gantt (deliverables+gates and WBS-generated), Readiness (MRF), Briefing Pack, RAID movement; margin analytics = not built |
| Mobile | Mobile apps: time entry, expense receipts with photos, approvals | Responsive web UI; native mobile app = not built |
| Global / multi-entity | OneWorld: subsidiaries, currencies, tax, global resource pools | Multi-project/wave model with per-project traffic lights and types (template/rollout/cell); multi-currency/tax = not built |
| CRM / HR linkage | CRM + SuitePeople HR; time-off impacts staffing | Task-app sends (Google Tasks/To Do/Todoist), share links, Teams doc-repo webhook; HR = not built |
| Data foundation | Single NetSuite platform, no integrations | Single SQLite DB; Excel import (real Deliverables Master / Decision Register / Risk Register via import_files.py); error log with optional Google Drive sync |

## Where The Hub is stronger
- Gate discipline: evidence contracts, Chair decisions, enforced conditions, computed (not declared) readiness with stale-evidence and unmeasured-is-Red rules.
- Traceability: every status figure clickable back to source + as-at date; printable gate reports with custom cover/logo.
- Lightweight: runs anywhere Python runs (incl. Termux), no license, no ERP dependency.

## Where SuiteProjects is stronger
- End-to-end PSA + financials: billing, invoicing, revenue recognition, project accounting, consolidation.
- Resource allocation grid with skills search; mobile apps; HR/time-off integration.
