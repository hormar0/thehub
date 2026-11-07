"""Database schema and seed data for the Milestone Hub control center."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS workstreams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lead TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phase TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    chair TEXT NOT NULL,
    entry_criteria TEXT NOT NULL,
    exit_criteria TEXT NOT NULL,
    outcome TEXT,
    decided_date TEXT
);

CREATE TABLE IF NOT EXISTS deliverables (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    workstream_id TEXT NOT NULL REFERENCES workstreams(id),
    owner TEXT NOT NULL,
    gate_id TEXT NOT NULL REFERENCES gates(id),
    state TEXT NOT NULL DEFAULT 'not_started',
    due_date TEXT NOT NULL,
    verified_by TEXT,
    verified_date TEXT,
    evidence_ref TEXT,
    dependency_ids TEXT NOT NULL DEFAULT '[]',
    grade TEXT NOT NULL DEFAULT '',
    responsible_user TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium',   -- low | medium | high
    dtype TEXT NOT NULL DEFAULT 'task',            -- task | milestone | document | report | other
    tags TEXT NOT NULL DEFAULT '',             -- comma-separated
    planned_hours REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conditions (
    id TEXT PRIMARY KEY,
    gate_id TEXT NOT NULL REFERENCES gates(id),
    text TEXT NOT NULL,
    owner TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_date TEXT NOT NULL,
    reexamined_at_gate TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    owner TEXT NOT NULL,
    raised_date TEXT NOT NULL,
    needed_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    blocks TEXT NOT NULL DEFAULT '',
    decision TEXT,
    decided_date TEXT
);

CREATE TABLE IF NOT EXISTS raid (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    owner TEXT NOT NULL,
    raised_date TEXT NOT NULL,
    movement TEXT NOT NULL DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS kanban_columns (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    position INTEGER NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_modules (
    name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS time_entries (
    id TEXT PRIMARY KEY,
    deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
    owner TEXT NOT NULL,
    hours REAL NOT NULL,
    week TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS program_phases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    program_phase_id TEXT NOT NULL,
    sap_phase TEXT NOT NULL DEFAULT 'Discover',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    light TEXT NOT NULL DEFAULT 'green',
    project_type TEXT NOT NULL DEFAULT 'template'
);

CREATE TABLE IF NOT EXISTS program_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    light TEXT NOT NULL DEFAULT 'green',
    report_on TEXT NOT NULL DEFAULT 'deliverables'
);

CREATE TABLE IF NOT EXISTS mrf_dimensions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    weight INTEGER NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mrf_criteria (
    id TEXT PRIMARY KEY,
    dimension_id TEXT NOT NULL REFERENCES mrf_dimensions(id),
    statement TEXT NOT NULL,
    measure_type TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    thresholds TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mrf_evidence (
    gate_id TEXT NOT NULL REFERENCES gates(id),
    criterion_id TEXT NOT NULL REFERENCES mrf_criteria(id),
    value TEXT NOT NULL DEFAULT '',
    as_at TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    override TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (gate_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS mistral_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'mistral-large-latest',
    base_url TEXT NOT NULL DEFAULT 'https://api.mistral.ai/v1',
    enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wbs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_id TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    synced INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT ''          -- comma-separated skills for allocation grid search
);

CREATE TABLE IF NOT EXISTS gate_reports (
    gate_id TEXT PRIMARY KEY REFERENCES gates(id),
    logo TEXT NOT NULL DEFAULT '',
    logo_name TEXT NOT NULL DEFAULT '',
    front_title TEXT NOT NULL DEFAULT '',
    front_description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    sort_key TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY,
    deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
    created TEXT NOT NULL,
    views INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_integrations (
    provider TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    token TEXT NOT NULL DEFAULT '',
    list_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ai_agents (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    owner TEXT NOT NULL,
    grounding TEXT NOT NULL DEFAULT '',
    accuracy_gate REAL NOT NULL DEFAULT 90.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS doc_repo (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL DEFAULT 'teams',
    webhook_url TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    citation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'missing',
    checked_date TEXT NOT NULL
);
"""


def seed(db: sqlite3.Connection):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM gates")
    if cur.fetchone()[0] > 0:
        return

    workstreams = [
        ("WS-CORE", "Core Template", "A. Reinhart"),
        ("WS-INT", "Integration", "M. Okafor"),
        ("WS-DATA", "Data Migration", "S. Lindqvist"),
        ("WS-CHANGE", "Change & Training", "L. Moreau"),
        ("WS-CUT", "Cutover & Go-Live", "D. Petrov"),
    ]
    cur.executemany("INSERT INTO workstreams VALUES (?,?,?)", workstreams)

    gates = [
        ("E-010", "Entry: Mobilization", "Entry", "2025-11-14", "passed", "R. Castellanos",
         "Charter signed; workstream leads named; register v1 published",
         "All WS leads confirmed; register has named owner per deliverable",
         "Passed unconditionally", "2025-11-14"),
        ("E-020", "Entry: Blueprint Sign-off", "Entry", "2026-01-30", "passed_with_conditions", "R. Castellanos",
         "Blueprint drafted by all workstreams; open questions logged",
         "Blueprint signed by process owners; top-10 risks have owners",
         "Passed with 3 enforced conditions", "2026-01-30"),
        ("E-030", "Entry: Fit-to-Standard Complete", "Entry", "2026-04-10", "in_progress", "R. Castellanos",
         "Fit workshops complete in all workstreams",
         "Gap register closed or dispositioned; config backlog sized",
         None, None),
        ("D-010", "Design: Solution Design Freeze", "Design", "2026-06-12", "upcoming", "R. Castellanos",
         "Design documents complete; integration contracts drafted",
         "Design freeze approved; no open critical design decisions",
         None, None),
        ("B-010", "Build: First Build Complete", "Build", "2026-09-04", "upcoming", "R. Castellanos",
         "Core configuration built in dev; unit tests passing",
         "Build demo passed; defect backlog < 20 open Sev1/2",
         None, None),
        ("T-010", "Test: SIT Entry", "Test", "2026-11-20", "upcoming", "R. Castellanos",
         "SIT environment ready; test scripts approved; data loaded",
         "SIT entry approved by QA lead and process owners",
         None, None),
        ("C-005", "Cutover: Go/No-Go", "Cutover", "2027-02-26", "upcoming", "R. Castellanos",
         "All cutover rehearsals done; rollback plan tested; readiness evidence complete",
         "Named Gate Chair decides go/no-go on assembled evidence",
         None, None),
    ]
    cur.executemany("INSERT INTO gates VALUES (?,?,?,?,?,?,?,?,?,?)", gates)

    cur.executemany("INSERT OR IGNORE INTO gates VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("M-15/07", "Milestone 15/07 — Quality, Organization and Validation", "Milestone", "2026-07-15", "upcoming", "R. Castellanos",
         "Quality/org/validation evidence complete", "Gate passes on assembled evidence", None, None),
        ("M-27/06", "Milestone 27/06 — Template fully validated; R2 scope defined", "Milestone", "2026-06-27", "upcoming", "R. Castellanos",
         "Template validated; high-level R2 scope and business process defined", "Gate passes on assembled evidence", None, None),
        ("M-22/08", "Milestone 22/08 — Localization build & FIT 1 done; R2 plan defined", "Milestone", "2026-08-22", "upcoming", "R. Castellanos",
         "Localization build and FIT 1 completed; checkpoint for FIT deliverables pre-Milestone 05", "Detailed project plan & resources defined for R2", None, None),
        ("M-30/10", "Milestone 30/10 — Template build finalized", "Milestone", "2026-10-30", "upcoming", "R. Castellanos",
         "Template build complete", "Gate passes on assembled evidence", None, None),
        ("M-MID", "Mid-cycle checkpoint — UAT / Release / Business Validation start", "Milestone", "2026-09-15", "upcoming", "R. Castellanos",
         "Checkpoint review", "UAT/release/business validation start confirmed", None, None),
        ("M-19/10", "Milestone 19/10 — UAT completed; handover to AMS; R2 design done", "Milestone", "2026-10-19", "upcoming", "R. Castellanos",
         "UAT completed (gateways check)", "Handover to AMS; Solution Design Release 2 complete", None, None),
        ("M-01/11", "MAJOR MILESTONE 01/11 — Release Go-Live", "Go-Live", "2026-11-01", "upcoming", "R. Castellanos",
         "All prior milestones passed; readiness evidence complete", "Go-live on assembled evidence", None, None),
        ("M-21/12", "Milestone 21/12 — Hypercare finished; R2 build complete", "Milestone", "2026-12-21", "upcoming", "R. Castellanos",
         "Warranty / hypercare phase finished", "Solution Build Release 2 complete", None, None),
    ])

    deliverables = [
        ("DEL-001", "Global Process Blueprint", "Standard process blueprint across all countries",
         "WS-CORE", "A. Reinhart", "E-020", "verified", "2026-01-28", "R. Castellanos", "2026-01-29",
         "SharePoint/BP/2026-014", "[]", "A", "areinhart", "PRJ-01"),
        ("DEL-002", "Fit-Gap Analysis Register", "Consolidated gap register with dispositions",
         "WS-CORE", "A. Reinhart", "E-030", "in_review", "2026-04-08", None, None,
         "SharePoint/FG/register-v3", "[\"DEL-001\"]", "B", "areinhart", "PRJ-01"),
        ("DEL-003", "Integration Landscape & Contracts", "End-to-end integration design with signed contracts",
         "WS-INT", "M. Okafor", "E-030", "in_progress", "2026-04-05", None, None,
         "", "[\"DEL-001\"]", "C", "mokafor", "PRJ-01"),
        ("DEL-004", "Legacy Data Extraction Specs", "Extraction specs for all legacy systems",
         "WS-DATA", "S. Lindqvist", "E-030", "in_progress", "2026-04-03", None, None,
         "Jira/DATA-221", "[]", "B", "slindqvist", "PRJ-02"),
        ("DEL-005", "Data Quality Rules & Profiling Report", "DQ rules signed off with profiling results",
         "WS-DATA", "S. Lindqvist", "E-030", "blocked", "2026-04-09", None, None,
         "", "[\"DEL-004\"]", "D", "slindqvist", "PRJ-02"),
        ("DEL-006", "Target Operating Model", "TOM with roles, spans, country adaptations",
         "WS-CHANGE", "L. Moreau", "D-010", "not_started", "2026-06-10", None, None,
         "", "[\"DEL-002\"]", "", "lmoreau", "PRJ-01"),
        ("DEL-007", "Training Curriculum & Materials", "Role-based curriculum for 4,000 users",
         "WS-CHANGE", "L. Moreau", "B-010", "not_started", "2026-08-28", None, None,
         "", "[\"DEL-006\"]", "", "lmoreau", "PRJ-02"),
        ("DEL-008", "Cutover Runbook v1", "Full cutover runbook with timings and owners",
         "WS-CUT", "D. Petrov", "T-010", "not_started", "2026-11-15", None, None,
         "", "[\"DEL-003\",\"DEL-005\"]", "", "dpetrov", "PRJ-03"),
        ("DEL-009", "Mock Cutover Rehearsal #2 Report", "Second rehearsal results with defect log",
         "WS-CUT", "D. Petrov", "C-005", "not_started", "2027-02-19", None, None,
         "", "[\"DEL-008\"]", "", "dpetrov", "PRJ-03"),
        ("DEL-010", "Go-Live Readiness Assessment", "Independent readiness evidence pack for go/no-go",
         "WS-CUT", "D. Petrov", "C-005", "not_started", "2027-02-24", None, None,
         "", "[\"DEL-009\"]", "", "dpetrov", "PRJ-03"),
    ]
    cur.executemany("INSERT INTO deliverables (id, title, description, workstream_id, owner, gate_id, state, due_date, verified_by, verified_date, evidence_ref, dependency_ids, grade, responsible_user, project_id, priority, tags, planned_hours, dtype) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(d) + ("medium", "", 0, "task") for d in deliverables])

    conditions = [
        ("COND-01", "E-020", "Close top-3 blueprint gaps with named process owners before E-030",
         "A. Reinhart", "2026-04-08", "open", "2026-01-30", "E-030"),
        ("COND-02", "E-020", "Appoint integration architect with contract authority",
         "M. Okafor", "2026-03-15", "met", "2026-01-30", "E-030"),
        ("COND-03", "E-020", "Publish data retention & archiving policy for legacy extracts",
         "S. Lindqvist", "2026-04-01", "open", "2026-01-30", "E-030"),
    ]
    cur.executemany("INSERT INTO conditions VALUES (?,?,?,?,?,?,?,?)", conditions)

    decisions = [
        ("DEC-01", "Approve custom workflow for PR approvals above threshold",
         "Finance process owner undecided between standard and custom workflow",
         "A. Reinhart", "2026-02-10", "2026-04-05", "open", "DEL-002 sign-off; config backlog sizing", None, None),
        ("DEC-02", "Select e-invoicing provider for 3 pilot countries",
         "Two vendors shortlisted; legal review complete",
         "M. Okafor", "2026-03-02", "2026-04-09", "open", "DEL-003 integration contracts", None, None),
        ("DEC-03", "Confirm archiving approach for 12-year-old legacy records",
         "Compliance requires either full migration or certified archive",
         "S. Lindqvist", "2026-03-20", "2026-04-01", "escalated", "DEL-005 (blocked deliverable)", None, None),
        ("DEC-04", "Approve blueprint scope for shared services center",
         "SSC scope approved by steering on 2026-01-28",
         "L. Moreau", "2026-01-15", "2026-01-28", "decided", "", "Approved as proposed", "2026-01-28"),
    ]
    cur.executemany("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?)", decisions)

    raid = [
        ("RAID-01", "risk", "Legacy data quality worse than profiled in 2 systems",
         "Profiling shows null rates 3x higher than assumed in payroll and asset registers",
         "very_high", "mitigating", "S. Lindqvist", "2026-03-18", "up"),
        ("RAID-02", "issue", "DEL-005 blocked: archiving decision pending (DEC-03)",
         "Data quality rules cannot be finalized until compliance decision lands",
         "high", "open", "S. Lindqvist", "2026-03-25", "new"),
        ("RAID-03", "risk", "Integration architect capacity gap in April",
         "Architect committed to another program 40% through April",
         "high", "mitigating", "M. Okafor", "2026-03-10", "down"),
        ("RAID-04", "dependency", "DEL-003 contracts gate DEL-008 cutover runbook",
         "Runbook cannot be finalized without signed integration contracts",
         "medium", "open", "D. Petrov", "2026-03-22", "unchanged"),
        ("RAID-05", "risk", "Training material translation lead time underestimated",
         "6 languages; vendor quotes 8 weeks vs 5 planned",
         "medium", "open", "L. Moreau", "2026-03-28", "up"),
        ("RAID-06", "issue", "E-020 condition COND-01 at risk of expiry",
         "2 of 3 blueprint gaps still without process owner sign-off",
         "high", "open", "A. Reinhart", "2026-03-30", "new"),
    ]
    cur.executemany("INSERT INTO raid VALUES (?,?,?,?,?,?,?,?,?)", raid)

    evidence = [
        ("EV-01", "DEL-001", "Signed blueprint PDF", "SharePoint", "SharePoint/BP/2026-014", "present", "2026-01-29"),
        ("EV-02", "DEL-002", "Gap register v3 with dispositions", "SharePoint", "SharePoint/FG/register-v3", "partial", "2026-04-01"),
        ("EV-03", "DEL-003", "Integration contracts", "Teams + SharePoint", "Teams/INT/contracts-draft", "partial", "2026-04-01"),
        ("EV-04", "DEL-004", "Extraction specs", "Jira", "Jira/DATA-221", "partial", "2026-04-01"),
        ("EV-05", "DEL-005", "DQ rules + profiling report", "SharePoint", "", "missing", "2026-04-01"),
    ]
    cur.executemany("INSERT INTO evidence VALUES (?,?,?,?,?,?,?)", evidence)

    cur.executemany("INSERT INTO app_modules VALUES (?,?,?)", [
        ("decisions", "Decisions", 1),
        ("risks", "Risks", 1),
        ("gantt", "Gantt Chart", 1),
        ("kanban", "Kanban", 1),
        ("timereport", "Time Reporting", 1),
        ("agents", "AI Agents", 1),
        ("invoicing", "Invoicing (placeholder)", 0),
        ("bookkeeping", "Bookkeeping integration (placeholder)", 0),
        ("projaccounting", "Project accounting (placeholder)", 0),
        ("consolidation", "Consolidation (placeholder)", 0),
        ("allocation", "Resource allocation grid", 1),
    ])

    time_entries = [
        ("TE-01", "DEL-001", "A. Reinhart", 32.0, "2026-W05"),
        ("TE-02", "DEL-002", "A. Reinhart", 28.5, "2026-W14"),
        ("TE-03", "DEL-003", "M. Okafor", 41.0, "2026-W14"),
        ("TE-04", "DEL-004", "S. Lindqvist", 22.0, "2026-W13"),
        ("TE-05", "DEL-005", "S. Lindqvist", 12.5, "2026-W13"),
        ("TE-06", "DEL-006", "L. Moreau", 8.0, "2026-W12"),
    ]
    cur.executemany("INSERT INTO time_entries VALUES (?,?,?,?,?,?)", [(t[0], t[1], t[2], t[3], t[4], "PRJ-01") for t in time_entries])


    cur.executemany("INSERT OR REPLACE INTO program_phases VALUES (?,?,?,?,?)", [
        ("PH-FORMULATE", "Program Formulation", "2025-10-01", "2026-01-31", 0),
        ("PH-ORGANIZE", "Organization", "2026-02-01", "2026-05-31", 1),
        ("PH-DEPLOY", "Deployment", "2026-06-01", "2026-12-31", 2),
        ("PH-APPRAISE", "Appraisal", "2027-01-01", "2027-03-31", 3),
        ("PH-DISSOLVE", "Dissolution", "2027-04-01", "2027-06-30", 4),
    ])

    cur.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)", [
        ("PRJ-R1", "Factory China", "PH-FORMULATE", "Explore", "2026-02-01", "2026-08-31", "active", "green", "rollout"),
        ("PRJ-R2", "Planning Gallin", "PH-ORGANIZE", "Realize", "2026-03-01", "2026-10-30", "active", "amber", "rollout"),
        ("PRJ-R3", "Market Western Europe", "PH-DEPLOY", "Deploy", "2026-07-01", "2026-12-31", "planned", "green", "rollout"),
        ("PRJ-R4", "Version 2 North America", "PH-DEPLOY", "Deploy", "2026-09-01", "2027-02-28", "planned", "amber", "rollout"),
        ("PRJ-C1", "Data Migration", "PH-ORGANIZE", "Realize", "2026-02-15", "2026-06-30", "active", "green", "cell"),
        ("PRJ-C2", "Testing", "PH-DEPLOY", "Realize", "2026-06-01", "2026-11-30", "planned", "amber", "cell"),
        ("PRJ-C3", "Cut over", "PH-DEPLOY", "Deploy", "2026-11-01", "2027-01-31", "planned", "red", "cell"),
        ("PRJ-C4", "Hypercare", "PH-APPRAISE", "Deploy", "2027-02-01", "2027-03-31", "planned", "green", "cell"),
        ("PRJ-C5", "Authorization", "PH-ORGANIZE", "Explore", "2026-03-01", "2026-07-31", "planned", "green", "cell"),
        ("PRJ-C6", "Training", "PH-DEPLOY", "Realize", "2026-08-01", "2026-12-15", "planned", "green", "cell"),
        ("PRJ-C7", "Business Realizing", "PH-DEPLOY", "Realize", "2026-07-15", "2026-12-31", "planned", "amber", "cell"),
        ("PRJ-V1", "Version 1", "PH-FORMULATE", "Explore", "2026-02-01", "2026-08-31", "active", "green", "rollout"),
        ("PRJ-V2", "Version 2", "PH-DEPLOY", "Realize", "2026-06-01", "2026-12-31", "planned", "amber", "rollout"),
        ("PRJ-V3", "Version 3", "PH-APPRAISE", "Deploy", "2027-01-01", "2027-04-30", "planned", "green", "rollout"),
    ])

    cur.execute("INSERT INTO doc_repo VALUES (1, 'teams', '', 0)")
    cur.execute("INSERT OR IGNORE INTO program_settings VALUES (1, 'green', 'deliverables')")
    cur.execute("INSERT OR IGNORE INTO mistral_config VALUES (1, '', 'mistral-large-latest', 'https://api.mistral.ai/v1', 0)")

    cur.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?)", [
        ("areinhart", "A. Reinhart", "a.reinhart@example.com", "+46 70 111 22 33", "PRJ-01", "SAP S/4, Finance, Process design"),
        ("mokafor", "M. Okafor", "m.okafor@example.com", "+44 7700 900 123", "PRJ-01", "Integration, APIs, EDI"),
        ("slindqvist", "S. Lindqvist", "s.lindqvist@example.com", "+46 70 444 55 66", "PRJ-02", "Data migration, SQL, Data quality"),
        ("lmoreau", "L. Moreau", "l.moreau@example.com", "+33 6 12 34 56 78", "PRJ-02", "OCM, Training, Localization"),
        ("dpetrov", "D. Petrov", "d.petrov@example.com", "+385 91 234 5678", "PRJ-03", "Cutover, Testing, PMO"),
        ("rcastellanos", "R. Castellanos", "r.castellanos@example.com", "+1 415 555 0132", "", "PMO, Governance, Steering"),
    ])

    cur.executemany("INSERT OR IGNORE INTO task_integrations VALUES (?,?,?,?)", [
        ("google_tasks", 0, "", "default"),
        ("ms_todo", 0, "", ""),
        ("todoist", 0, "", ""),
    ])

    cur.executemany("INSERT INTO ai_agents VALUES (?,?,?,?,?,?,?)", [
        ("Program Pulse", "Status & forecasting", "PMO", "SAP Cloud ALM, register, minutes", 90, 1, 0),
        ("Status Drafter", "Consolidated reporting", "PMO", "Register, RAID, gate outcomes", 90, 1, 1),
        ("Executive Briefing", "Decision packs for the Gate Chair", "Gate Chair office", "Briefing pack, evidence record", 92, 1, 2),
        ("Health Predictor", "Trajectory warnings", "PMO", "Time entries, RAID, gate history", 88, 1, 3),
        ("RAID Extractor", "Risks & issues from the record", "PMO", "Minutes, tickets, test results", 90, 1, 4),
        ("Decision Log Keeper", "Open decisions & latency", "PMO", "Decision logs, mail", 90, 1, 5),
        ("Evidence Auditor", "Completeness vs exit criteria", "QA", "Evidence store, register", 95, 1, 6),
        ("Document Finder", "Live version, cited", "PMO", "Teams / SharePoint doc repo", 90, 1, 7),
        ("Metadata Structurer", "Register agents can trust", "Data team", "Register, schema registry", 93, 1, 8),
        ("Template Guardian", "Deviation & reuse checks", "Methodology", "Playbooks, templates", 90, 1, 9),
        ("SAP Best Practices", "Fit-to-standard guidance & BP catalog lookup", "SAP lead", "SAP Best Practices explorer, BP content", 92, 1, 10),
        ("Localization Advisor", "Country/language requirements & translation readiness", "Change lead", "Localization playbooks, legal reqs", 90, 1, 11),
    ])

    cur.executemany("INSERT INTO milestones VALUES (?,?,?,?,?)", [
        ("MS-01", "15/07", "2026-07-15", "Quality, Organization and Validation", ""),
        ("MS-02", "30/10", "2026-10-30", "Template build finalized", ""),
        ("MS-03", "27/06", "2026-06-27", "Template fully validated", "High level scope & business process defined for R2"),
        ("MS-04", "22/08", "2026-08-22", "Localization build and FIT 1 completed", "Checkpoint for FIT deliverables pre-Milestone 05; detailed project plan & resources defined for R2"),
        ("MS-05", "Mid-cycle", "2026-09-15", "Checkpoint for UAT / Release / Business Validation start", ""),
        ("MS-06", "19/10", "2026-10-19", "UAT completed (gateways check)", "Handover to AMS; completion of Solution Design Release 2"),
        ("MS-07", "01/11", "2026-11-01", "MAJOR MILESTONE: Release Go-Live", ""),
        ("MS-08", "21/12", "2026-12-21", "Warranty / Hypercare phase finished", "Completion of Solution Build Release 2"),
    ])

    cur.executemany("INSERT INTO mrf_dimensions VALUES (?,?,?,?)", [
        ("D1", "Scope", 10, 0),
        ("D2", "Deliverables", 20, 1),
        ("D3", "Quality", 15, 2),
        ("D4", "Dependencies", 15, 3),
        ("D5", "Resources", 10, 4),
        ("D6", "Acceptance", 15, 5),
        ("D7", "Downstream", 10, 6),
        ("D8", "Risk & blockers", 5, 7),
    ])

    cur.executemany("INSERT INTO mrf_criteria VALUES (?,?,?,?,?,?,?,?)", [
        ("D1-01", "D1", "Change requests closed against baseline", "count", "0", '{"green":"==0","amber":"<=2","red":">2"}', "PMO change log", "PMO"),
        ("D2-01", "D2", "Deliverables in evidence contract verified", "percent", "100", '{"green":">=100","amber":">=90","red":"<90"}', "Deliverables register", "PMO"),
        ("D3-01", "D3", "Open high-severity defects on milestone scope", "count", "0", '{"green":"==0","amber":"<=3","red":">3"}', "DefectDB report", "QA"),
        ("D4-01", "D4", "Inbound dependencies landed on or before target", "percent", "100", '{"green":">=100","amber":">=90","red":"<90"}', "Dependency tracker", "PMO"),
        ("D5-01", "D5", "Named resources confirmed for the cycle", "percent", "100", '{"green":">=100","amber":">=80","red":"<80"}', "Resource plan", "PMO"),
        ("D6-01", "D6", "Receiving party formally accepted (confirmation on record)", "boolean", "true", '{"green":"true","red":"false"}', "Decision log / confirmation mail", "Gate Chair"),
        ("D7-01", "D7", "Next milestone can start on planned date", "boolean", "true", '{"green":"true","red":"false"}', "Integrated plan", "PMO"),
        ("D8-01", "D8", "Open high/critical blockers on this milestone", "count", "0", '{"green":"==0","amber":"<=2","red":">2"}', "RAID register", "PMO"),
    ])

    cur.executemany("INSERT INTO mrf_evidence VALUES (?,?,?,?,?,?)", [
        ("E-030", "D1-01", "1", "2026-10-28", "PMO change log 2026-10-28", ""),
        ("E-030", "D2-01", "25", "2026-10-29", "register export", ""),
        ("E-030", "D3-01", "2", "2026-10-30", "DefectDB MS-open-high", ""),
        ("E-030", "D4-01", "80", "2026-10-29", "Dependency tracker", ""),
        ("E-030", "D5-01", "90", "2026-10-27", "Resource plan W44", ""),
        ("E-030", "D6-01", "false", "2026-10-30", "", ""),
        ("E-030", "D7-01", "true", "2026-10-28", "Integrated plan v12", ""),
        ("E-030", "D8-01", "1", "2026-10-30", "RAID register", ""),
        ("C-005", "D1-01", "0", "2026-10-30", "PMO change log", ""),
        ("C-005", "D2-01", "0", "2026-10-30", "register export", ""),
        ("C-005", "D3-01", "0", "2026-10-30", "DefectDB", ""),
        ("C-005", "D4-01", "0", "2026-10-30", "Dependency tracker", ""),
        ("C-005", "D5-01", "0", "2026-10-30", "Resource plan", ""),
        ("C-005", "D6-01", "false", "2026-10-30", "", ""),
        ("C-005", "D7-01", "false", "2026-10-30", "Integrated plan", ""),
        ("C-005", "D8-01", "0", "2026-10-30", "RAID register", ""),
    ])

    cur.executemany("INSERT INTO wbs VALUES (?,?,?,?,?,?,?)", [
        ("WBS-R1", "PRJ-R1", "", "1", "Factory China", "2026-02-01", "2026-08-31"),
        ("WBS-R1-1", "PRJ-R1", "WBS-R1", "1.1", "Design & blueprint", "2026-02-01", "2026-05-31"),
        ("WBS-R1-2", "PRJ-R1", "WBS-R1", "1.2", "Build & configure", "2026-06-01", "2026-08-15"),
        ("WBS-C1", "PRJ-C1", "", "1", "Data Migration", "2026-02-15", "2026-06-30"),
        ("WBS-C2", "PRJ-C2", "", "1", "Testing", "2026-06-01", "2026-11-30"),
        ("WBS-C3", "PRJ-C3", "", "1", "Cut over", "2026-11-01", "2027-01-31"),
    ])
    db.commit()


def seed_columns(db: sqlite3.Connection):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM kanban_columns")
    if cur.fetchone()[0] > 0:
        return
    defaults = [
        ("not_started", "Not started", 0, 1),
        ("in_progress", "In progress", 1, 1),
        ("in_review", "In review", 2, 1),
        ("blocked", "Blocked", 3, 1),
        ("verified", "Verified", 4, 1),
    ]
    cur.executemany("INSERT INTO kanban_columns VALUES (?,?,?,?)", defaults)
    db.commit()
