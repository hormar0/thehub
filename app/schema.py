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
    dependency_ids TEXT NOT NULL DEFAULT '[]'
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
    week TEXT NOT NULL
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

    deliverables = [
        ("DEL-001", "Global Process Blueprint", "Standard process blueprint across all countries",
         "WS-CORE", "A. Reinhart", "E-020", "verified", "2026-01-28", "R. Castellanos", "2026-01-29",
         "SharePoint/BP/2026-014", "[]"),
        ("DEL-002", "Fit-Gap Analysis Register", "Consolidated gap register with dispositions",
         "WS-CORE", "A. Reinhart", "E-030", "in_review", "2026-04-08", None, None,
         "SharePoint/FG/register-v3", "[\"DEL-001\"]"),
        ("DEL-003", "Integration Landscape & Contracts", "End-to-end integration design with signed contracts",
         "WS-INT", "M. Okafor", "E-030", "in_progress", "2026-04-05", None, None,
         "", "[\"DEL-001\"]"),
        ("DEL-004", "Legacy Data Extraction Specs", "Extraction specs for all legacy systems",
         "WS-DATA", "S. Lindqvist", "E-030", "in_progress", "2026-04-03", None, None,
         "Jira/DATA-221", "[]"),
        ("DEL-005", "Data Quality Rules & Profiling Report", "DQ rules signed off with profiling results",
         "WS-DATA", "S. Lindqvist", "E-030", "blocked", "2026-04-09", None, None,
         "", "[\"DEL-004\"]"),
        ("DEL-006", "Target Operating Model", "TOM with roles, spans, country adaptations",
         "WS-CHANGE", "L. Moreau", "D-010", "not_started", "2026-06-10", None, None,
         "", "[\"DEL-002\"]"),
        ("DEL-007", "Training Curriculum & Materials", "Role-based curriculum for 4,000 users",
         "WS-CHANGE", "L. Moreau", "B-010", "not_started", "2026-08-28", None, None,
         "", "[\"DEL-006\"]"),
        ("DEL-008", "Cutover Runbook v1", "Full cutover runbook with timings and owners",
         "WS-CUT", "D. Petrov", "T-010", "not_started", "2026-11-15", None, None,
         "", "[\"DEL-003\",\"DEL-005\"]"),
        ("DEL-009", "Mock Cutover Rehearsal #2 Report", "Second rehearsal results with defect log",
         "WS-CUT", "D. Petrov", "C-005", "not_started", "2027-02-19", None, None,
         "", "[\"DEL-008\"]"),
        ("DEL-010", "Go-Live Readiness Assessment", "Independent readiness evidence pack for go/no-go",
         "WS-CUT", "D. Petrov", "C-005", "not_started", "2027-02-24", None, None,
         "", "[\"DEL-009\"]"),
    ]
    cur.executemany("INSERT INTO deliverables VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", deliverables)

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
    ])

    time_entries = [
        ("TE-01", "DEL-001", "A. Reinhart", 32.0, "2026-W05"),
        ("TE-02", "DEL-002", "A. Reinhart", 28.5, "2026-W14"),
        ("TE-03", "DEL-003", "M. Okafor", 41.0, "2026-W14"),
        ("TE-04", "DEL-004", "S. Lindqvist", 22.0, "2026-W13"),
        ("TE-05", "DEL-005", "S. Lindqvist", 12.5, "2026-W13"),
        ("TE-06", "DEL-006", "L. Moreau", 8.0, "2026-W12"),
    ]
    cur.executemany("INSERT INTO time_entries VALUES (?,?,?,?,?)", time_entries)

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
