# Laurel AI (formerly Lauria/Laurel) — Time Reporting & Tracking overview

Reference for The Hub's time-reporting module (benchmark of ambient/AI time capture).
Sources: laurel.ai, Workday Marketplace, Google Play, YouTube.

## Core value proposition
AI-powered "True Time" for professional services firms (legal, accounting, consulting): ambient background capture that eliminates manual timesheets.

## Key functions
- **Ambient Activity Capture** — auto-logs digital work across Outlook, calendar, Zoom, Word/Excel/PDFs and 100+ whitelisted cloud apps.
- **Offline Work & Gap Detection** — flags uncaptured gaps (phone calls, away-from-desk, client dinners) so non-digital billable hours get accounted for.
- **AI Categorization & Allocation** — matches work to the correct client/matter using document content, email context, billing history.
- **Automated Narrative Generation** — draft entry narratives compliant with client outside-counsel billing guidelines, in the professional's own voice.
- **"Review and Release" workflow** — ~5 min/day reviewing/editing/releasing pre-populated entries instead of creating from scratch.
- **Firm-Wide Work Intelligence** — dashboards on profitability, realization, utilization, tool usage, work breakdown by rank/department.
- **Mobile & Offline Mobility** — manual timers, auto billing codes, offline mode with auto-sync.

## Impact metrics
- Recovers ~28+ min of lost billable time per user/day.
- +4–11% firm revenue via better realization.
- Manual timesheet time reduced to <6 min/day.

## Mapping to The Hub
| Laurel | The Hub |
|---|---|
| Ambient capture | Not possible without desktop agent — Hub stays manual entry (week × project grid) |
| Gap detection | Could be a Mistral agent prompt over the week grid |
| AI categorization to client/matter | Project picker on time entries; Mistral agent could suggest project |
| Narrative generation | Mistral "✦ Run in Mistral" can draft entry narratives |
| Review & release | Kanban/state flow on deliverables; weekly review view |
| Firm-wide intelligence | Dashboard KPIs + by-project/by-owner hours |
| Mobile app | Responsive web on tablet |
