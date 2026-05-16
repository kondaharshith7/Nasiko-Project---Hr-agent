"""
HR Nexus — SQLite Database Layer
Single source of truth for all three modules: Leave/Attendance, HR Data, Recruitment.
"""
import sqlite3
import os
import json
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "hr_nexus.db")

# ─────────────────────────────────────────────
# CONNECTION HELPER
# ─────────────────────────────────────────────

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def dict_row(row):
    return dict(row) if row else None


def dict_rows(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    department  TEXT NOT NULL,
    role        TEXT NOT NULL,
    hire_date   TEXT,
    salary      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id     TEXT PRIMARY KEY,
    annual_used     INTEGER DEFAULT 0,
    annual_remaining INTEGER DEFAULT 20,
    sick_used       INTEGER DEFAULT 0,
    sick_remaining  INTEGER DEFAULT 10,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS attendance_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT,
    name        TEXT,
    date        TEXT,
    status      TEXT,   -- present/absent/late/half_day/on_leave
    leave_type  TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     TEXT,
    employee_name   TEXT,
    task_title      TEXT,
    task_date       TEXT,
    priority        TEXT,   -- Critical/High/Medium/Low
    can_delegate    TEXT,   -- Yes/No
    delegate_to     TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    category            TEXT NOT NULL,  -- intern/full_time/contract/freelance/leadership
    department          TEXT,
    required_skills     TEXT,  -- JSON array
    description         TEXT,
    status              TEXT DEFAULT 'active',
    created_date        TEXT,
    shortlist_threshold INTEGER DEFAULT 65
);

CREATE TABLE IF NOT EXISTS candidates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    job_id          TEXT,
    category        TEXT,
    status          TEXT DEFAULT 'applied',  -- applied/screened/shortlisted/interview/offered/hired/rejected
    score           INTEGER DEFAULT 0,
    resume_text     TEXT,
    score_breakdown TEXT,  -- JSON
    applied_date    TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS email_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    to_email    TEXT,
    subject     TEXT,
    body        TEXT,
    status      TEXT,
    timestamp   TEXT
);

CREATE TABLE IF NOT EXISTS cv_profiles (
    id                TEXT PRIMARY KEY,
    candidate_id      TEXT,
    job_id            TEXT,
    sender_email      TEXT,
    attachment_name   TEXT,
    received_on       TEXT,
    name              TEXT,
    phone             TEXT,
    skills            TEXT,   -- JSON array
    education         TEXT,   -- JSON array
    experience_years  INTEGER DEFAULT 0,
    work_experience   TEXT,   -- JSON array
    projects          TEXT,   -- JSON array
    certifications    TEXT,   -- JSON array
    github            TEXT,
    portfolio         TEXT,
    summary           TEXT,
    raw_text          TEXT,
    full_json         TEXT,   -- complete parsed profile as JSON
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS hr_policy (
    id          INTEGER PRIMARY KEY,
    loaded_at   TEXT,
    content     TEXT
);

CREATE TABLE IF NOT EXISTS meetings (
    id              TEXT PRIMARY KEY,
    employee_name   TEXT,
    employee_email  TEXT,
    hr_email        TEXT,
    meeting_date    TEXT,
    start_time      TEXT,
    end_time        TEXT,
    duration_min    INTEGER,
    reason          TEXT,
    status          TEXT DEFAULT 'scheduled',
    created_at      TEXT
);
"""

# ─────────────────────────────────────────────
# SEED DATA
# ─────────────────────────────────────────────

def seed():
    conn = get_conn()
    cur = conn.cursor()

    # Check if already seeded
    cur.execute("SELECT COUNT(*) FROM employees")
    if cur.fetchone()[0] > 0:
        conn.close()
        return

    today = date.today()

    # ── EMPLOYEES ──────────────────────────────
    employees = [
        ("EMP001", "Anjali Singh",      "anjali@company.com",     "Engineering",   "Senior Python Developer", "2021-03-15", 1800000),
        ("EMP002", "Rahul Mehta",       "rahul@company.com",      "Engineering",   "React Developer",         "2022-06-01", 1200000),
        ("EMP003", "Priya Sharma",      "priya@company.com",      "Marketing",     "Marketing Manager",       "2020-01-10", 1400000),
        ("EMP004", "Karan Patel",       "karan@company.com",      "HR",            "HR Executive",            "2023-04-18", 900000),
        ("EMP005", "Sneha Nair",        "sneha@company.com",      "Engineering",   "DevOps Engineer",         "2021-09-05", 1600000),
        ("EMP006", "Arjun Verma",       "arjun@company.com",      "Finance",       "Financial Analyst",       "2022-02-14", 1100000),
        ("EMP007", "Divya Reddy",       "divya@company.com",      "Engineering",   "QA Engineer",             "2023-01-20", 1000000),
        ("EMP008", "Rohan Das",         "rohan@company.com",      "Product",       "Product Manager",         "2020-07-07", 2000000),
        ("EMP009", "Meena Iyer",        "meena@company.com",      "Marketing",     "Content Strategist",      "2022-11-03", 850000),
        ("EMP010", "Vikram Joshi",      "vikram@company.com",     "Engineering",   "Backend Developer",       "2021-12-01", 1350000),
        ("EMP011", "Nisha Kapoor",      "nisha@company.com",      "Finance",       "Accounts Manager",        "2019-08-25", 1250000),
        ("EMP012", "Amit Tiwari",       "amit@company.com",       "Engineering",   "ML Engineer",             "2022-03-10", 1700000),
    ]
    cur.executemany(
        "INSERT INTO employees VALUES (?,?,?,?,?,?,?)", employees
    )

    # ── LEAVE BALANCES ─────────────────────────
    balances = [
        ("EMP001", 8,  12, 3, 7),
        ("EMP002", 5,  15, 1, 9),
        ("EMP003", 12, 8,  4, 6),
        ("EMP004", 3,  17, 0, 10),
        ("EMP005", 15, 5,  5, 5),   # Low balance
        ("EMP006", 6,  14, 2, 8),
        ("EMP007", 4,  16, 1, 9),
        ("EMP008", 10, 10, 3, 7),
        ("EMP009", 2,  18, 0, 10),
        ("EMP010", 18, 2,  6, 4),   # Very low balance
        ("EMP011", 7,  13, 4, 6),
        ("EMP012", 9,  11, 2, 8),
    ]
    cur.executemany(
        "INSERT INTO leave_balances VALUES (?,?,?,?,?)", balances
    )

    # ── ATTENDANCE LOG ─────────────────────────
    attendance_rows = []
    emp_ids = [e[0] for e in employees]
    emp_names = {e[0]: e[1] for e in employees}

    # Generate 60 days of attendance history
    for i in range(60):
        d = (today - timedelta(days=60-i)).isoformat()
        weekday = (today - timedelta(days=60-i)).weekday()
        if weekday >= 5:
            continue  # skip weekends

        for emp_id in emp_ids:
            name = emp_names[emp_id]
            # Simulate realistic patterns
            if emp_id == "EMP010" and weekday == 0:  # Monday pattern
                status, lt, note = "absent", "", "Unplanned absence"
            elif emp_id == "EMP005" and i > 40:  # Many leaves recently
                status, lt, note = "on_leave", "annual", "Annual leave"
            elif emp_id == "EMP003" and weekday == 4 and i > 20:  # Friday pattern
                status, lt, note = "absent", "", "Unplanned absence"
            elif emp_id == "EMP002" and i in [15, 22, 35]:
                status, lt, note = "late", "", "Late arrival"
            else:
                status, lt, note = "present", "", ""
            attendance_rows.append((emp_id, name, d, status, lt, note))

    cur.executemany(
        "INSERT INTO attendance_log (employee_id,name,date,status,leave_type,notes) VALUES (?,?,?,?,?,?)",
        attendance_rows
    )

    # ── TASKS ──────────────────────────────────
    tasks = [
        ("EMP001", "Anjali Singh",  "Deploy payment service v2",     str(today + timedelta(days=2)), "Critical", "No",  ""),
        ("EMP001", "Anjali Singh",  "Code review for Auth module",    str(today + timedelta(days=3)), "High",     "Yes", "Rahul Mehta"),
        ("EMP001", "Anjali Singh",  "Sprint planning meeting",        str(today + timedelta(days=1)), "High",     "No",  ""),
        ("EMP002", "Rahul Mehta",   "Fix dashboard loading bug",      str(today + timedelta(days=2)), "High",     "Yes", "Divya Reddy"),
        ("EMP003", "Priya Sharma",  "Q4 campaign launch",             str(today + timedelta(days=1)), "Critical", "No",  ""),
        ("EMP005", "Sneha Nair",    "Kubernetes cluster upgrade",     str(today + timedelta(days=4)), "Critical", "No",  ""),
        ("EMP008", "Rohan Das",     "Stakeholder product review",     str(today + timedelta(days=2)), "Critical", "No",  ""),
        ("EMP012", "Amit Tiwari",   "Model retraining pipeline",      str(today + timedelta(days=3)), "High",     "Yes", "Anjali Singh"),
    ]
    cur.executemany(
        "INSERT INTO tasks (employee_id,employee_name,task_title,task_date,priority,can_delegate,delegate_to) VALUES (?,?,?,?,?,?,?)",
        tasks
    )

    # ── JOBS ──────────────────────────────────
    jobs = [
        ("FT-001", "Senior Python Developer", "full_time",  "Engineering",
         json.dumps(["Python", "FastAPI", "PostgreSQL", "Docker"]),
         "We are looking for a senior Python developer to lead backend development.", "active", "2025-01-10", 65),
        ("INT-001", "ML Intern",              "intern",     "AI/ML",
         json.dumps(["Python", "NumPy", "Pandas", "Basic ML"]),
         "3-month internship to work on NLP data pipelines.", "active", "2025-01-15", 55),
        ("CON-001", "DevOps Contractor",      "contract",   "Infrastructure",
         json.dumps(["Kubernetes", "Terraform", "AWS", "Docker"]),
         "6-month contract for cloud migration project.", "active", "2025-01-20", 70),
        ("FRL-001", "UI/UX Freelancer",       "freelance",  "Design",
         json.dumps(["Figma", "UI Design", "Prototyping", "User Research"]),
         "Project-based UI redesign for mobile app.", "active", "2025-02-01", 65),
        ("LDR-001", "VP Engineering",         "leadership", "Engineering",
         json.dumps(["Engineering Leadership", "System Design", "P&L", "Team Building"]),
         "Seeking a VP Engineering to lead 40+ engineer org.", "active", "2025-02-05", 75),
    ]
    cur.executemany(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", jobs
    )

    # ── CANDIDATES ────────────────────────────
    candidates = [
        # FT-001 Python Developer
        ("CAND-001", "Rishi Gupta",       "rishi@email.com",       "FT-001",  "full_time",  "shortlisted", 82,
         "8 years Python/Django/FastAPI. Led 3 production microservices. AWS certified. Open source contributor.",
         json.dumps({"skills": 35, "experience": 28, "projects": 14, "education": 12}), "2025-01-12"),
        ("CAND-002", "Tanvi Patel",       "tanvi@email.com",        "FT-001",  "full_time",  "interview",   76,
         "5 years Python. Built payment APIs at FinTech startup. Strong SQL. GitHub: 800 contributions.",
         json.dumps({"skills": 30, "experience": 24, "projects": 15, "education": 10}), "2025-01-13"),
        ("CAND-003", "Aditya Kumar",      "aditya@email.com",       "FT-001",  "full_time",  "rejected",    48,
         "2 years Python. Mostly scripting. No production experience. Applied for senior role.",
         json.dumps({"skills": 18, "experience": 12, "projects": 10, "education": 8}),  "2025-01-14"),
        ("CAND-004", "Pallavi Rao",       "pallavi@email.com",      "FT-001",  "full_time",  "applied",     71,
         "6 years backend dev. Django REST, PostgreSQL, Redis. Reduced API latency by 40%.",
         json.dumps({"skills": 28, "experience": 22, "projects": 15, "education": 6}),  "2025-01-15"),
        # INT-001 ML Intern
        ("CAND-005", "Aryan Shah",        "aryan@email.com",        "INT-001", "intern",     "shortlisted", 78,
         "Final year CS. CGPA 9.1. Built sentiment analysis project. Kaggle competitions. GitHub active.",
         json.dumps({"skills": 30, "projects": 28, "education": 18, "communication": 2}), "2025-01-16"),
        ("CAND-006", "Ishita Mishra",     "ishita@email.com",       "INT-001", "intern",     "offered",     84,
         "3rd year. ML specialization. Built image classifier for college project. 2 hackathon wins. Strong Python.",
         json.dumps({"skills": 34, "projects": 28, "education": 18, "communication": 4}), "2025-01-17"),
        ("CAND-007", "Dev Chopra",        "dev@email.com",           "INT-001", "intern",     "rejected",    42,
         "2nd year student. Basic Python only. No projects. No GitHub.",
         json.dumps({"skills": 16, "projects": 14, "education": 10, "communication": 2}), "2025-01-18"),
        # CON-001 DevOps
        ("CAND-008", "Manoj Pillai",      "manoj@email.com",        "CON-001", "contract",   "shortlisted", 88,
         "7 years DevOps. Expert Kubernetes, Terraform, AWS. Completed 4 cloud migrations. Available immediately.",
         json.dumps({"skills": 44, "experience": 32, "availability": 12}), "2025-01-21"),
        ("CAND-009", "Sunita Bose",       "sunita@email.com",        "CON-001", "contract",   "interview",   79,
         "5 years SRE at e-commerce company. Strong Kubernetes and monitoring. 2 week notice.",
         json.dumps({"skills": 40, "experience": 27, "availability": 12}), "2025-01-22"),
        # FRL-001 UI/UX
        ("CAND-010", "Neha Jain",         "neha@email.com",          "FRL-001", "freelance",  "shortlisted", 90,
         "Freelance designer 6 years. Portfolio: 20+ mobile apps. Dribbble top 100. Client rating 4.9/5.",
         json.dumps({"portfolio": 42, "skills": 33, "communication": 15}), "2025-02-02"),
        # LDR-001 VP Engineering
        ("CAND-011", "Suresh Krishnan",   "suresh@email.com",       "LDR-001", "leadership", "interview",   85,
         "15 years. Led 60-person eng org at unicorn startup. P&L owner $5M budget. Scaled 0 to 1M users.",
         json.dumps({"leadership_exp": 32, "domain_expertise": 26, "strategic_thinking": 20, "culture_fit": 7}), "2025-02-06"),
        ("CAND-012", "Kavitha Nambiar",   "kavitha@email.com",      "LDR-001", "leadership", "applied",     77,
         "12 years. Managed 25 engineers. Strong system design. Built 3 products from scratch.",
         json.dumps({"leadership_exp": 27, "domain_expertise": 24, "strategic_thinking": 19, "culture_fit": 7}), "2025-02-07"),
    ]
    cur.executemany(
        "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?)",
        candidates
    )

    conn.commit()
    conn.close()
    print("✅ HR Nexus database seeded successfully.")


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────

def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    seed()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at: {DB_PATH}")
