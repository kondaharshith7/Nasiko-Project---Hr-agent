"""
HR Nexus — Recruitment & Screening Tools (Module 4)
Covers: candidate management, resume scoring, shortlisting,
        interview scheduling, offer letters, pipeline dashboard.
"""
import json
from datetime import datetime, date, timedelta
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from database import get_conn, dict_row, dict_rows
from utils import send_email, email_cfg


# ── Scoring criteria per category ─────────────────────────────────
CATEGORY_CRITERIA = {
    "intern":     {"shortlist_threshold": 55, "weights": {"skills": 40, "projects": 30, "education": 20, "communication": 10},
                   "interview_rounds": "1 Round — Technical basics + Culture fit (45 min)", "focus": "learning potential, college projects, hackathons"},
    "full_time":  {"shortlist_threshold": 65, "weights": {"skills": 35, "experience": 30, "projects": 20, "education": 15},
                   "interview_rounds": "2 Rounds — Technical (60 min) + HR (30 min)", "focus": "experience quality and measurable impact"},
    "contract":   {"shortlist_threshold": 70, "weights": {"skills": 50, "experience": 35, "availability": 15},
                   "interview_rounds": "1 Round — Skills assessment + Availability check (45 min)", "focus": "exact skill match and immediate availability"},
    "freelance":  {"shortlist_threshold": 65, "weights": {"portfolio": 45, "skills": 35, "communication": 20},
                   "interview_rounds": "1 Round — Portfolio review + Client scenario (45 min)", "focus": "portfolio quality and communication"},
    "leadership": {"shortlist_threshold": 75, "weights": {"leadership_exp": 35, "domain_expertise": 30, "strategic_thinking": 25, "culture_fit": 10},
                   "interview_rounds": "3 Rounds — Case study + Panel + Culture fit", "focus": "team leadership, P&L, strategic vision"},
}


# ══════════════════════════════════════════════════════════════════
# TOOL: GET CANDIDATES
# ══════════════════════════════════════════════════════════════════
@tool
def get_candidates(status_filter: str = "", job_id: str = "", category: str = "") -> str:
    """
    View candidates in the hiring pipeline, filterable by status, job, or category.
    Status options: applied, screened, shortlisted, interview, offered, hired, rejected.
    Call this to view the hiring pipeline, see who's shortlisted, or check candidate status.

    Args:
        status_filter: Filter by status e.g. 'shortlisted', 'interview', or '' for all
        job_id: Filter by job ID e.g. 'FT-001', or '' for all jobs
        category: Filter by category e.g. 'intern', 'full_time', or ''
    """
    conn = get_conn()
    try:
        query = """
            SELECT c.*, j.title as job_title, j.department
            FROM candidates c
            LEFT JOIN jobs j ON c.job_id = j.id
            WHERE 1=1
        """
        params = []
        if status_filter:
            query += " AND LOWER(c.status) LIKE LOWER(?)"
            params.append(f"%{status_filter}%")
        if job_id:
            query += " AND c.job_id = ?"
            params.append(job_id)
        if category:
            query += " AND LOWER(c.category) LIKE LOWER(?)"
            params.append(f"%{category}%")
        query += " ORDER BY c.score DESC, c.applied_date DESC"

        rows = dict_rows(conn.execute(query, params).fetchall())
        if not rows:
            return f"No candidates found matching the given filters."

        # Group by job
        by_job: dict = {}
        for c in rows:
            jt = c.get("job_title") or c["job_id"] or "Unknown"
            if jt not in by_job:
                by_job[jt] = []
            breakdown = {}
            try:
                breakdown = json.loads(c["score_breakdown"]) if c["score_breakdown"] else {}
            except Exception:
                pass
            by_job[jt].append({
                "id":           c["id"],
                "name":         c["name"],
                "email":        c["email"],
                "category":     c["category"],
                "status":       c["status"],
                "score":        c["score"],
                "score_breakdown": breakdown,
                "applied_date": c["applied_date"],
                "resume_summary": (c["resume_text"] or "")[:200] + "..." if c["resume_text"] and len(c["resume_text"]) > 200 else c["resume_text"]
            })

        return json.dumps({
            "total_candidates": len(rows),
            "filters_applied":  {"status": status_filter, "job": job_id, "category": category},
            "by_job":           by_job
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: ADD CANDIDATE
# ══════════════════════════════════════════════════════════════════
@tool
def add_candidate(
    name: str,
    email: str,
    job_id: str,
    resume_text: str
) -> str:
    """
    Add a new candidate to the hiring pipeline for a specific job.
    The candidate will start with status 'applied' and needs to be scored.
    Call this when a new resume is received or a candidate applies.

    Args:
        name: Candidate's full name
        email: Candidate's email address
        job_id: Job ID they are applying to e.g. 'FT-001', 'INT-001'
        resume_text: Full resume text / candidate profile description
    """
    conn = get_conn()
    try:
        job = dict_row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        if not job:
            return f"Job ID '{job_id}' not found. Use get_open_jobs to see available positions."

        # Check for duplicate
        existing = conn.execute(
            "SELECT id FROM candidates WHERE LOWER(email)=LOWER(?) AND job_id=?",
            (email, job_id)
        ).fetchone()
        if existing:
            return f"Candidate {name} ({email}) already applied to job {job_id}."

        # Generate ID
        count = conn.execute("SELECT COUNT(*) as c FROM candidates").fetchone()["c"]
        cand_id = f"CAND-{count+100:03d}"

        conn.execute(
            "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cand_id, name, email, job_id, job["category"], "applied",
             0, resume_text, "{}", date.today().isoformat())
        )
        conn.commit()

        return json.dumps({
            "status":    "✅ Candidate Added",
            "id":        cand_id,
            "name":      name,
            "job_id":    job_id,
            "job_title": job["title"],
            "category":  job["category"],
            "next_step": f"Use score_and_shortlist_candidate with candidate_id='{cand_id}' to screen them."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: SCORE AND SHORTLIST CANDIDATE
# ══════════════════════════════════════════════════════════════════
@tool
def score_and_shortlist_candidate(candidate_id: str) -> str:
    """
    AI-score a candidate's resume against the job requirements and auto-decide
    shortlist or reject based on category-specific thresholds.
    Returns detailed scoring breakdown with recommendation.
    Call this to screen any applied candidate.

    Args:
        candidate_id: Candidate ID e.g. 'CAND-001'
    """
    conn = get_conn()
    try:
        cand = dict_row(conn.execute(
            "SELECT c.*, j.title as job_title, j.required_skills, j.description FROM candidates c LEFT JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
            (candidate_id,)
        ).fetchone())
        if not cand:
            return f"Candidate '{candidate_id}' not found."

        category  = cand["category"]
        criteria  = CATEGORY_CRITERIA.get(category, CATEGORY_CRITERIA["full_time"])
        threshold = criteria["shortlist_threshold"]

        llm    = ChatOpenAI(model="gpt-4o", temperature=0)
        skills = json.loads(cand["required_skills"]) if cand["required_skills"] else []
        prompt = f"""You are a senior technical recruiter. Score this candidate objectively.

JOB: {cand['job_title']}
CATEGORY: {category}
REQUIRED SKILLS: {', '.join(skills)}
CATEGORY FOCUS: {criteria['focus']}
SCORING WEIGHTS: {json.dumps(criteria['weights'])}

CANDIDATE RESUME:
{cand['resume_text']}

Score each dimension from the weights above (e.g. if skills weight=35, score out of 35).
Return ONLY valid JSON:
{{
  "total_score": <int 0-100>,
  "breakdown": {{ "<dimension>": <score out of weight>, ... }},
  "strengths": ["strength1", "strength2"],
  "gaps": ["gap1", "gap2"],
  "recommendation": "shortlist" or "reject",
  "one_line_verdict": "concise explanation"
}}"""

        raw = llm.invoke(prompt).content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        result = json.loads(raw)

        score     = result["total_score"]
        decision  = "shortlisted" if score >= threshold else "rejected"

        conn.execute(
            "UPDATE candidates SET score=?, score_breakdown=?, status=? WHERE id=?",
            (score, json.dumps(result["breakdown"]), decision, candidate_id)
        )
        conn.commit()

        icon = "✅" if decision == "shortlisted" else "❌"
        return json.dumps({
            "candidate":      cand["name"],
            "job":            cand["job_title"],
            "category":       category,
            "score":          f"{score}/100",
            "threshold":      threshold,
            "decision":       f"{icon} {decision.upper()}",
            "breakdown":      result["breakdown"],
            "strengths":      result["strengths"],
            "gaps":           result["gaps"],
            "verdict":        result["one_line_verdict"],
            "interview_process": criteria["interview_rounds"] if decision == "shortlisted" else "N/A"
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: SCREEN ALL CANDIDATES FOR A JOB
# ══════════════════════════════════════════════════════════════════
@tool
def screen_all_candidates(job_id: str) -> str:
    """
    Batch-screen all unscored candidates for a specific job.
    Scores every 'applied' candidate and moves them to shortlisted or rejected.
    Auto-sends rejection emails to rejected candidates.
    Call this to process all applicants for a job in one shot.

    Args:
        job_id: Job ID to screen candidates for e.g. 'FT-001'
    """
    conn = get_conn()
    try:
        candidates = dict_rows(conn.execute(
            "SELECT id, name FROM candidates WHERE job_id=? AND status='applied'",
            (job_id,)
        ).fetchall())

        if not candidates:
            return f"No 'applied' candidates found for job {job_id}."

        results = {"shortlisted": [], "rejected": []}
        for cand in candidates:
            result_str = score_and_shortlist_candidate.invoke({"candidate_id": cand["id"]})
            result     = json.loads(result_str)
            decision   = result.get("decision", "")
            bucket     = "shortlisted" if "SHORTLISTED" in decision else "rejected"
            results[bucket].append({
                "name":   cand["name"],
                "score":  result.get("score"),
                "verdict": result.get("verdict")
            })

            # Auto-send rejection emails
            if bucket == "rejected":
                cand_full = dict_row(conn.execute(
                    "SELECT email FROM candidates WHERE id=?", (cand["id"],)
                ).fetchone())
                job = dict_row(conn.execute("SELECT title FROM jobs WHERE id=?", (job_id,)).fetchone())
                body = f"""Dear {cand['name']},

Thank you for your interest in the {job['title']} position at our company.

After careful review of your application, we regret to inform you that we will not be moving forward with your candidacy at this time.

We were impressed by your background and encourage you to apply for future openings that match your profile.

We wish you the best in your career journey.

Warm regards,
HR Team"""
                send_email(cand_full["email"], f"Application Update — {job['title']}", body)

        return json.dumps({
            "job_id":       job_id,
            "total_screened": len(candidates),
            "shortlisted":  results["shortlisted"],
            "rejected":     results["rejected"],
            "shortlisted_count": len(results["shortlisted"]),
            "rejected_count":    len(results["rejected"]),
            "summary": f"Screened {len(candidates)} candidates: {len(results['shortlisted'])} shortlisted, {len(results['rejected'])} rejected. Rejection emails sent automatically."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: SCHEDULE INTERVIEW
# ══════════════════════════════════════════════════════════════════
@tool
def schedule_interview(candidate_id: str, interview_date: str, interview_time: str) -> str:
    """
    Schedule an interview for a shortlisted candidate and send them a professional invite.
    Updates candidate status to 'interview' and logs the email.
    Call this when HR wants to invite a shortlisted candidate for an interview.

    Args:
        candidate_id: Candidate ID e.g. 'CAND-001'
        interview_date: Date in YYYY-MM-DD format
        interview_time: Time e.g. '2:00 PM IST' or '14:00 IST'
    """
    conn = get_conn()
    try:
        cand = dict_row(conn.execute(
            "SELECT c.*, j.title as job_title FROM candidates c LEFT JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
            (candidate_id,)
        ).fetchone())

        if not cand:
            return f"Candidate '{candidate_id}' not found."

        category = cand["category"]
        criteria = CATEGORY_CRITERIA.get(category, CATEGORY_CRITERIA["full_time"])
        cfg      = email_cfg()

        body = f"""Dear {cand['name']},

We are delighted to invite you for an interview for the {cand['job_title']} position!

Interview Details:
━━━━━━━━━━━━━━━━━
Date:    {interview_date}
Time:    {interview_time}
Format:  {criteria['interview_rounds']}
Mode:    Video call / In-person (as confirmed)

Please confirm your availability by replying to this email.

What to expect:
{criteria['interview_rounds']}

Preparation tips:
- Review your past projects and be ready to walk through your experience
- Prepare 2-3 examples of challenges you've solved
- Have questions ready for us about the role and team

We look forward to speaking with you!

Best regards,
HR Team | HR Nexus"""

        send_email(cand["email"], f"Interview Invitation — {cand['job_title']}", body)

        conn.execute(
            "UPDATE candidates SET status='interview' WHERE id=?",
            (candidate_id,)
        )
        conn.commit()

        return json.dumps({
            "status":     "✅ Interview Scheduled",
            "candidate":  cand["name"],
            "email":      cand["email"],
            "job":        cand["job_title"],
            "date":       interview_date,
            "time":       interview_time,
            "format":     criteria["interview_rounds"],
            "invite_sent": True
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GENERATE OFFER LETTER
# ══════════════════════════════════════════════════════════════════
@tool
def generate_offer_letter(
    candidate_id: str,
    offered_salary: str,
    joining_date: str,
    additional_benefits: str = ""
) -> str:
    """
    Generate and send a professional offer letter to a selected candidate.
    Tailored to the hiring category (intern/full_time/contract/leadership).
    Updates candidate status to 'offered'.
    Call this when HR decides to make an offer to a candidate.

    Args:
        candidate_id: Candidate ID e.g. 'CAND-001'
        offered_salary: Salary/stipend being offered e.g. '₹25L/year' or '₹20,000/month'
        joining_date: Expected joining date e.g. '2025-03-01' or 'March 1, 2025'
        additional_benefits: Optional benefits to mention e.g. 'Health insurance, WFH 3 days/week'
    """
    conn = get_conn()
    try:
        cand = dict_row(conn.execute(
            "SELECT c.*, j.title as job_title, j.department FROM candidates c LEFT JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
            (candidate_id,)
        ).fetchone())

        if not cand:
            return f"Candidate '{candidate_id}' not found."

        category = cand["category"]
        cfg      = email_cfg()
        today    = date.today().strftime("%B %d, %Y")

        # Category-specific offer text
        category_text = {
            "intern":     f"This internship is for a duration as discussed, with a monthly stipend of {offered_salary}.",
            "full_time":  f"This is a permanent full-time position with an annual CTC of {offered_salary}.",
            "contract":   f"This is a fixed-term contract role with compensation of {offered_salary}.",
            "freelance":  f"This is a project-based freelance engagement with compensation of {offered_salary}.",
            "leadership": f"This is a senior leadership position with an annual CTC of {offered_salary} plus performance bonuses.",
        }.get(category, f"Compensation: {offered_salary}")

        benefits_section = ""
        if additional_benefits:
            benefits_section = f"\n\nAdditional Benefits:\n{additional_benefits}"

        offer_body = f"""OFFER LETTER

Date: {today}

Dear {cand['name']},

We are thrilled to extend an offer of employment for the position of {cand['job_title']} at our organization.
After a thorough evaluation process, we believe you are an exceptional fit for our team.

OFFER DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Position:    {cand['job_title']}
Department:  {cand['department']}
Category:    {category.replace('_', ' ').title()}
{category_text}
Joining Date: {joining_date}{benefits_section}

CONDITIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. This offer is contingent on successful completion of background verification.
2. Please confirm your acceptance by replying to this email within 5 business days.
3. Any misrepresentation in your application may result in immediate termination.

We are confident you will be a valuable addition to our team and look forward to having you on board.

Please sign and return a copy of this letter to indicate your acceptance.

Warm regards,

{cfg['hr_name']}
Human Resources Department
HR Nexus System

________________________
Accepted by: ___________
Date: ___________"""

        send_email(cand["email"], f"Offer Letter — {cand['job_title']}", offer_body)
        conn.execute("UPDATE candidates SET status='offered' WHERE id=?", (candidate_id,))
        conn.commit()

        return json.dumps({
            "status":         "✅ Offer Letter Sent",
            "candidate":      cand["name"],
            "email":          cand["email"],
            "position":       cand["job_title"],
            "offered_salary": offered_salary,
            "joining_date":   joining_date,
            "category":       category,
            "letter_sent":    True,
            "next_step":      "Candidate must reply with acceptance. Update status to 'hired' once accepted."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET OPEN JOBS
# ══════════════════════════════════════════════════════════════════
@tool
def get_open_jobs() -> str:
    """
    List all active job openings with candidate counts and pipeline status.
    Call this when HR asks what positions are open or wants to see the jobs list.
    """
    conn = get_conn()
    try:
        jobs = dict_rows(conn.execute(
            "SELECT * FROM jobs WHERE status='active' ORDER BY created_date DESC"
        ).fetchall())

        result = []
        for job in jobs:
            pipeline = dict_rows(conn.execute(
                "SELECT status, COUNT(*) as c FROM candidates WHERE job_id=? GROUP BY status",
                (job["id"],)
            ).fetchall())
            pipeline_dict = {r["status"]: r["c"] for r in pipeline}
            total = sum(pipeline_dict.values())
            result.append({
                "job_id":       job["id"],
                "title":        job["title"],
                "category":     job["category"],
                "department":   job["department"],
                "required_skills": json.loads(job["required_skills"]) if job["required_skills"] else [],
                "created_date": job["created_date"],
                "total_applicants": total,
                "pipeline":     pipeline_dict
            })

        return json.dumps({
            "active_openings": len(result),
            "jobs":            result
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET RECRUITMENT DASHBOARD
# ══════════════════════════════════════════════════════════════════
@tool
def get_recruitment_dashboard() -> str:
    """
    Get a full recruitment pipeline overview: all jobs, candidate counts
    by stage, category breakdown, and hiring funnel metrics.
    Call this when HR wants a high-level view of the entire hiring process.
    """
    conn = get_conn()
    try:
        total_cands = conn.execute("SELECT COUNT(*) as c FROM candidates").fetchone()["c"]
        by_status   = dict_rows(conn.execute(
            "SELECT status, COUNT(*) as c FROM candidates GROUP BY status ORDER BY c DESC"
        ).fetchall())
        by_category = dict_rows(conn.execute(
            "SELECT category, COUNT(*) as c FROM candidates GROUP BY category"
        ).fetchall())
        top_scorers = dict_rows(conn.execute(
            """SELECT c.name, c.score, c.status, c.category, j.title as job
               FROM candidates c LEFT JOIN jobs j ON c.job_id=j.id
               WHERE c.score > 70
               ORDER BY c.score DESC LIMIT 5"""
        ).fetchall())
        open_jobs   = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status='active'").fetchone()["c"]
        hired       = conn.execute("SELECT COUNT(*) as c FROM candidates WHERE status='hired'").fetchone()["c"]

        # Funnel conversion
        applied      = next((r["c"] for r in by_status if r["status"] == "applied"), 0)
        shortlisted  = next((r["c"] for r in by_status if r["status"] == "shortlisted"), 0)
        interview    = next((r["c"] for r in by_status if r["status"] == "interview"), 0)
        offered      = next((r["c"] for r in by_status if r["status"] == "offered"), 0)

        return json.dumps({
            "📊 OVERVIEW": {
                "total_candidates":  total_cands,
                "active_jobs":       open_jobs,
                "total_hired":       hired,
            },
            "🔄 PIPELINE": {r["status"]: r["c"] for r in by_status},
            "📂 BY CATEGORY": {r["category"]: r["c"] for r in by_category},
            "🏆 TOP SCORERS": [
                f"{r['name']} ({r['job']}) — Score: {r['score']}, Status: {r['status']}"
                for r in top_scorers
            ],
            "📉 FUNNEL": {
                "applied":                applied,
                "shortlist_rate":         f"{round(shortlisted/max(applied,1)*100)}%",
                "interview_rate":         f"{round(interview/max(shortlisted,1)*100)}% of shortlisted",
                "offer_rate":             f"{round(offered/max(interview,1)*100)}% of interviewed",
            }
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: UPDATE CANDIDATE STATUS
# ══════════════════════════════════════════════════════════════════
@tool
def update_candidate_status(candidate_id: str, new_status: str) -> str:
    """
    Manually update a candidate's status in the pipeline.
    Valid statuses: applied, screened, shortlisted, interview, offered, hired, rejected.
    Call this to move candidates through stages or mark them as hired/rejected.

    Args:
        candidate_id: Candidate ID e.g. 'CAND-001'
        new_status: New status to set
    """
    valid = ["applied", "screened", "shortlisted", "interview", "offered", "hired", "rejected"]
    if new_status not in valid:
        return f"Invalid status. Use one of: {valid}"

    conn = get_conn()
    try:
        cand = dict_row(conn.execute(
            "SELECT c.name, j.title FROM candidates c LEFT JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
            (candidate_id,)
        ).fetchone())
        if not cand:
            return f"Candidate '{candidate_id}' not found."

        conn.execute("UPDATE candidates SET status=? WHERE id=?", (new_status, candidate_id))
        conn.commit()
        return f"✅ {cand['name']}'s status updated to **{new_status}** for {cand['title']}."
    finally:
        conn.close()
