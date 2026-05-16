"""
HR Nexus — Email CV Intake (Module 5)

HOW IT WORKS:
  1. check_email_inbox      — polls Gmail IMAP for unread emails with CV attachments
                              extracts PDF/DOCX/TXT → plain text
                              calls GPT-4o to parse text → structured JSON profile
                              saves profile to cv_profiles table
                              scores candidate against the job automatically
                              sends acknowledgement to applicant
                              sends summary report to HR

  2. get_cv_json_profile    — returns the full structured JSON profile for any candidate
                              (name, skills, education, experience, projects, github, etc.)

  3. email_intake_report    — emails HR a full ranked leaderboard for a job
                              with all CV profiles, scores, and approve/reject instructions

FILES CHANGED (Nasiko guide compliance):
  ✅ tools/email_intake.py  — NEW file, all logic here
  ✅ tools/__init__.py      — add imports (allowed)
  ✅ agent.py               — add tools + update prompt (allowed)
  ✅ database.py            — add cv_profiles table (allowed)
  ✅ Dockerfile             — add pypdf + python-docx (allowed)
  ❌ __main__.py            — NOT touched
  ❌ models.py              — NOT touched
"""

import os
import json
import imaplib
import email as _email_lib
import io
import logging
from datetime import date, datetime
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from database import get_conn, dict_row, dict_rows
from utils import send_email, email_cfg

logger = logging.getLogger("hr-nexus.email-intake")

# ─────────────────────────────────────────────────────────────────
# SCORING CRITERIA (mirrors recruitment_tools.py)
# ─────────────────────────────────────────────────────────────────

CATEGORY_CRITERIA = {
    "intern":     {"shortlist_threshold": 55,
                   "weights": {"skills": 40, "projects": 30, "education": 20, "communication": 10},
                   "focus": "learning potential, college projects, hackathons. NEVER penalise no experience."},
    "full_time":  {"shortlist_threshold": 65,
                   "weights": {"skills": 35, "experience": 30, "projects": 20, "education": 15},
                   "focus": "skills depth and measurable work experience impact"},
    "contract":   {"shortlist_threshold": 70,
                   "weights": {"skills": 50, "experience": 35, "availability": 15},
                   "focus": "exact skill match and immediate availability"},
    "freelance":  {"shortlist_threshold": 65,
                   "weights": {"portfolio": 45, "skills": 35, "communication": 20},
                   "focus": "portfolio quality and client communication"},
    "leadership": {"shortlist_threshold": 75,
                   "weights": {"leadership_exp": 35, "domain_expertise": 30, "strategic_thinking": 25, "culture_fit": 10},
                   "focus": "team size led, P&L ownership, strategic vision"},
}


# ─────────────────────────────────────────────────────────────────
# PDF / DOCX / TXT EXTRACTOR
# ─────────────────────────────────────────────────────────────────

def _extract_text(raw_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, DOCX, or TXT bytes."""
    fname = filename.lower()

    if fname.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
            text   = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
            if len(text) < 30:
                return "ERROR: PDF is a scanned image — no selectable text found. Ask candidate to send a text-based PDF."
            return text
        except ImportError:
            return "ERROR: pypdf not installed. Add pypdf>=3.0.0 to Dockerfile."
        except Exception as e:
            return f"ERROR: Could not read PDF '{filename}': {e}"

    if fname.endswith((".docx", ".doc")):
        try:
            import docx
            doc  = docx.Document(io.BytesIO(raw_bytes))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return text or "ERROR: DOCX is empty or uses unsupported formatting."
        except ImportError:
            return "ERROR: python-docx not installed. Add python-docx>=1.0.0 to Dockerfile."
        except Exception as e:
            return f"ERROR: Could not read DOCX '{filename}': {e}"

    if fname.endswith(".txt"):
        try:
            return raw_bytes.decode("utf-8", errors="replace").strip()
        except Exception as e:
            return f"ERROR: Could not decode text file: {e}"

    return f"ERROR: Unsupported file type '{filename}'. Candidate must send PDF, DOCX, or TXT."


# ─────────────────────────────────────────────────────────────────
# CV TEXT → STRUCTURED JSON PROFILE  (GPT-4o)
# ─────────────────────────────────────────────────────────────────

def _parse_cv_to_json(cv_text: str, sender_email: str) -> dict:
    """Ask GPT-4o to extract structured fields from raw CV text."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    prompt = f"""You are an expert HR analyst. Extract structured information from this CV.
Use the sender email if no email is found in the CV text.

CV TEXT:
{cv_text[:6000]}

Return ONLY valid JSON (no markdown, no backticks):
{{
  "name": "full name or 'Unknown'",
  "email": "email from CV, or use: {sender_email}",
  "phone": "phone number or ''",
  "location": "city/country or ''",
  "skills": ["skill1", "skill2", "skill3"],
  "education": [
    {{
      "degree": "B.Tech Computer Science",
      "institution": "IIT Bombay",
      "year": "2023",
      "grade": "8.5 CGPA"
    }}
  ],
  "experience_years": 0,
  "work_experience": [
    {{
      "title": "Software Engineer",
      "company": "TechCorp",
      "duration": "2 years",
      "description": "Built REST APIs, reduced latency by 40%"
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "description": "What it does and impact",
      "tech": ["Python", "React"]
    }}
  ],
  "certifications": ["AWS Certified", "Google ML Certificate"],
  "github": "https://github.com/username or ''",
  "portfolio": "https://portfolio.com or ''",
  "languages": ["English", "Hindi"],
  "summary": "2-3 sentence professional summary of this candidate based on their CV"
}}"""

    try:
        raw = llm.invoke(prompt).content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        logger.error(f"CV parse error: {e}")
        return {
            "name": "Unknown", "email": sender_email, "phone": "",
            "location": "", "skills": [], "education": [],
            "experience_years": 0, "work_experience": [], "projects": [],
            "certifications": [], "github": "", "portfolio": "",
            "languages": [], "summary": "Could not parse CV automatically.",
            "parse_error": str(e),
        }


# ─────────────────────────────────────────────────────────────────
# AI SCORER  (GPT-4o — uses structured profile + raw text)
# ─────────────────────────────────────────────────────────────────

def _score_cv(profile: dict, cv_text: str, job: dict) -> dict:
    """Score the CV against the job using category-specific criteria."""
    category  = job["category"]
    criteria  = CATEGORY_CRITERIA.get(category, CATEGORY_CRITERIA["full_time"])
    threshold = criteria["shortlist_threshold"]

    try:
        skills = json.loads(job["required_skills"]) if job.get("required_skills") else []
    except Exception:
        skills = []

    llm    = ChatOpenAI(model="gpt-4o", temperature=0)
    prompt = f"""You are a senior technical recruiter. Score this candidate honestly and objectively.

JOB DETAILS:
Title          : {job['title']}
Category       : {category.upper()}
Required Skills: {', '.join(skills)}
Job Description: {(job.get('description') or '')[:500]}
Category Focus : {criteria['focus']}
Scoring Weights: {json.dumps(criteria['weights'])}
Shortlist if   : score >= {threshold}

CANDIDATE STRUCTURED PROFILE:
{json.dumps({k: v for k, v in profile.items() if k != 'summary'}, indent=2)[:3000]}

RAW CV TEXT (first 2000 chars for context):
{cv_text[:2000]}

Score each dimension from the weights. Return ONLY valid JSON:
{{
  "total_score": <integer 0-100>,
  "breakdown": {{"<dimension>": <score out of its weight>, ...}},
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "strengths": ["strength1", "strength2"],
  "gaps": ["gap1"],
  "red_flags": [],
  "recommendation": "shortlist" or "reject",
  "one_line_verdict": "concise 1-sentence explanation"
}}"""

    try:
        raw = llm.invoke(prompt).content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        result["threshold"] = threshold
        result["category"]  = category
        return result
    except Exception as e:
        return {
            "total_score": 0, "threshold": threshold, "category": category,
            "breakdown": {}, "matched_skills": [], "missing_skills": [],
            "strengths": [], "gaps": [], "red_flags": [f"Scoring error: {e}"],
            "recommendation": "reject", "one_line_verdict": "Could not score automatically.",
        }


# ─────────────────────────────────────────────────────────────────
# GMAIL IMAP POLLER
# ─────────────────────────────────────────────────────────────────

def _fetch_unread_emails(subject_keyword: str = "") -> list[dict]:
    """Connect to Gmail via IMAP, fetch unread emails, mark as read."""
    cfg = email_cfg()
    if not cfg["sender"] or not cfg["password"]:
        logger.warning("SENDER_EMAIL / SENDER_PASSWORD not set — cannot poll inbox.")
        return []

    results = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(cfg["sender"], cfg["password"])
        mail.select("inbox")

        query = f'(UNSEEN SUBJECT "{subject_keyword}")' if subject_keyword else "UNSEEN"
        _, ids = mail.search(None, query)
        msg_ids = ids[0].split()
        logger.info(f"IMAP: {len(msg_ids)} unread email(s) found")

        for mid in msg_ids:
            _, data = mail.fetch(mid, "(RFC822)")
            msg     = _email_lib.message_from_bytes(data[0][1])

            sender  = _email_lib.utils.parseaddr(msg.get("From", ""))[1]
            subject = msg.get("Subject", "No Subject")
            body    = ""
            attachments = []

            for part in msg.walk():
                ctype = part.get_content_type()
                disp  = str(part.get("Content-Disposition", ""))

                if ctype == "text/plain" and "attachment" not in disp:
                    try:
                        body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        pass
                elif "attachment" in disp or part.get_filename():
                    fname   = part.get_filename() or "attachment"
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append({"filename": fname, "bytes": payload})

            results.append({
                "sender": sender, "subject": subject,
                "body": body.strip(), "attachments": attachments,
            })
            mail.store(mid, "+FLAGS", "\\Seen")   # mark as read

        mail.logout()
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP login failed: {e}")
    except Exception as e:
        logger.error(f"IMAP error: {e}")

    return results


# ─────────────────────────────────────────────────────────────────
# SAVE PROFILE + CANDIDATE TO DATABASE
# ─────────────────────────────────────────────────────────────────

def _save_profile_and_candidate(
    profile: dict, score_result: dict, job: dict,
    sender_email: str, attachment_name: str, cv_text: str
) -> str:
    """Save the JSON profile and scored candidate to the database. Returns candidate_id."""
    conn = get_conn()
    try:
        # Generate IDs
        count    = conn.execute("SELECT COUNT(*) as c FROM candidates").fetchone()["c"]
        cand_id  = f"CAND-{count + 100:03d}"
        prof_id  = f"PROF-{cand_id}"

        # Save candidate
        conn.execute(
            "INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                cand_id,
                profile.get("name", "Unknown"),
                profile.get("email", sender_email),
                job["id"],
                job["category"],
                "shortlisted" if score_result["recommendation"] == "shortlist" else "rejected",
                score_result["total_score"],
                cv_text[:3000],
                json.dumps(score_result.get("breakdown", {})),
                date.today().isoformat(),
            )
        )

        # Save full JSON profile
        conn.execute(
            """INSERT OR REPLACE INTO cv_profiles
               (id, candidate_id, job_id, sender_email, attachment_name, received_on,
                name, phone, skills, education, experience_years, work_experience,
                projects, certifications, github, portfolio, summary, raw_text, full_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                prof_id,
                cand_id,
                job["id"],
                sender_email,
                attachment_name,
                date.today().isoformat(),
                profile.get("name", "Unknown"),
                profile.get("phone", ""),
                json.dumps(profile.get("skills", [])),
                json.dumps(profile.get("education", [])),
                profile.get("experience_years", 0),
                json.dumps(profile.get("work_experience", [])),
                json.dumps(profile.get("projects", [])),
                json.dumps(profile.get("certifications", [])),
                profile.get("github", ""),
                profile.get("portfolio", ""),
                profile.get("summary", ""),
                cv_text[:5000],
                json.dumps(profile),
            )
        )
        conn.commit()
        return cand_id
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════
# TOOL 1 — CHECK EMAIL INBOX
# ═════════════════════════════════════════════════════════════════

@tool
def check_email_inbox(job_id: str, subject_keyword: str = "") -> str:
    """
    Poll the HR Gmail inbox for unread emails containing CV attachments.

    For EVERY unread email found this tool automatically:
      1. Downloads the PDF / DOCX / TXT attachment
      2. Extracts all text from the file
      3. Sends text to GPT-4o → parses into a structured JSON profile
         (name, email, skills, education, experience, projects, GitHub, etc.)
      4. Saves the JSON profile to the cv_profiles database table
      5. Scores the candidate against the job using category-specific criteria
      6. Saves the scored candidate to the candidates table
      7. Sends acknowledgement email to the applicant
      8. Emails HR a summary of all CVs processed this session

    Call when HR asks:
      "Check emails for new CVs for INT-001"
      "Any new applications received for FT-001?"
      "Process incoming CVs for this job"

    Args:
        job_id:           Job to score against e.g. 'FT-001', 'INT-001'
        subject_keyword:  Optional subject filter e.g. 'Python Developer'
                          Leave empty to process ALL unread emails with attachments
    """
    conn = get_conn()
    try:
        job = dict_row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        conn.close()

    if not job:
        conn2 = get_conn()
        try:
            available = [r["id"] for r in dict_rows(conn2.execute("SELECT id FROM jobs WHERE status='active'").fetchall())]
        finally:
            conn2.close()
        return json.dumps({
            "status": "error",
            "message": f"Job '{job_id}' not found.",
            "available_jobs": available,
        })

    cfg = email_cfg()
    if not cfg["sender"] or not cfg["password"]:
        return json.dumps({
            "status": "error",
            "message": (
                "Gmail credentials not set. Add these to your .env file:\n"
                "  SENDER_EMAIL=yourname@gmail.com\n"
                "  SENDER_PASSWORD=xxxx xxxx xxxx xxxx  (Gmail App Password)\n"
                "Then run: docker compose down -v && docker compose up --build"
            ),
        })

    emails = _fetch_unread_emails(subject_keyword)

    if not emails:
        return json.dumps({
            "status": "success",
            "message": "No new unread emails found in the inbox.",
            "job_id": job_id,
            "processed": 0,
        })

    processed = []
    skipped   = []

    for em in emails:
        sender  = em["sender"]
        subject = em["subject"]

        # Find first usable CV attachment
        cv_att = None
        for att in em["attachments"]:
            if att["filename"].lower().endswith((".pdf", ".docx", ".doc", ".txt")):
                cv_att = att
                break

        if not cv_att:
            skipped.append({"sender": sender, "subject": subject,
                            "reason": "No PDF/DOCX/TXT attachment found."})
            send_email(
                sender,
                f"Re: {subject} — CV Not Received",
                f"""Hello,

Thank you for your interest in the {job['title']} position.

We received your email but could not find a CV attachment.
Please reply with your CV attached as a PDF, DOCX, or TXT file.

Best regards,
HR Team""",
            )
            continue

        # ── Extract text ──────────────────────────────────────────
        cv_text = _extract_text(cv_att["bytes"], cv_att["filename"])
        if cv_text.startswith("ERROR:"):
            skipped.append({"sender": sender, "subject": subject, "reason": cv_text})
            continue

        # ── Parse to JSON profile ─────────────────────────────────
        profile = _parse_cv_to_json(cv_text, sender)

        # ── Score against job ─────────────────────────────────────
        score_result = _score_cv(profile, cv_text, job)

        # ── Save to database ──────────────────────────────────────
        cand_id = _save_profile_and_candidate(
            profile, score_result, job, sender, cv_att["filename"], cv_text
        )

        # ── Acknowledgement to applicant ──────────────────────────
        first_name = (profile.get("name") or "Applicant").split()[0]
        send_email(
            profile.get("email", sender),
            f"Application Received — {job['title']}",
            f"""Dear {first_name},

Thank you for applying for the {job['title']} position.

Your CV has been received and is currently under review by our team.

━━━━━━━━━━━━━━━━━━━━━━━━━
Application ID : {cand_id}
Position       : {job['title']}
Received       : {date.today().strftime('%B %d, %Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━

We will contact you within 5 business days if you are shortlisted.

Best regards,
HR Team""",
        )

        verdict = "✅ SHORTLISTED" if score_result["recommendation"] == "shortlist" else "❌ REJECTED"
        processed.append({
            "candidate_id":   cand_id,
            "name":           profile.get("name", "Unknown"),
            "email":          profile.get("email", sender),
            "attachment":     cv_att["filename"],
            "score":          score_result["total_score"],
            "threshold":      score_result["threshold"],
            "verdict":        verdict,
            "matched_skills": score_result.get("matched_skills", []),
            "missing_skills": score_result.get("missing_skills", []),
            "one_line":       score_result.get("one_line_verdict", ""),
        })

    # ── Email HR session summary ──────────────────────────────────
    if processed and cfg.get("hr_email"):
        rows = "\n".join([
            f"  {i+1}. {c['name']} | {c['score']}/100 | {c['verdict']}\n"
            f"     File    : {c['attachment']}\n"
            f"     Matched : {', '.join(c['matched_skills'][:4]) or 'None'}\n"
            f"     Missing : {', '.join(c['missing_skills'][:3]) or 'None'}\n"
            f"     Verdict : {c['one_line']}"
            for i, c in enumerate(processed)
        ])
        send_email(
            cfg["hr_email"],
            f"📥 {len(processed)} New CV(s) Processed — {job['title']} ({job_id})",
            f"""HR Team,

{len(processed)} CV(s) processed from inbox for {job['title']} ({job_id}):

{rows}

Skipped (no attachment or parse error): {len(skipped)}

Ask the agent:
  "Show CV profile for CAND-XXX" — see full structured JSON profile
  "Send intake report for {job_id}"  — full ranked leaderboard
  "Screen all candidates for {job_id}" — move to approval queue

— HR Nexus Email Intake""",
        )

    return json.dumps({
        "status":         "success",
        "job_id":         job_id,
        "job_title":      job["title"],
        "emails_found":   len(emails),
        "processed":      len(processed),
        "skipped":        len(skipped),
        "skipped_details": skipped,
        "candidates":     processed,
        "next_step": (
            f"Processed {len(processed)} CV(s). "
            "Use 'send intake report for " + job_id + "' to email HR a full ranked report, "
            "or 'screen all candidates for " + job_id + "' to auto-process shortlisting."
        ),
    }, indent=2)


# ═════════════════════════════════════════════════════════════════
# TOOL 2 — GET CV JSON PROFILE
# ═════════════════════════════════════════════════════════════════

@tool
def get_cv_json_profile(candidate_id: str) -> str:
    """
    Return the complete structured JSON profile extracted from a candidate's CV.

    Shows everything parsed from their CV:
      name, email, phone, location, skills, education (degree/institution/grade),
      work experience (title/company/duration/description), projects (name/tech/impact),
      certifications, GitHub, portfolio URL, professional summary.

    Also shows their AI score, matched/missing skills, strengths, and hiring verdict.

    Call when HR asks:
      "Show me the full profile for CAND-101"
      "What is the education background of this candidate?"
      "What projects has CAND-005 built?"
      "Show CV details for this candidate"

    Args:
        candidate_id: e.g. 'CAND-101'
    """
    conn = get_conn()
    try:
        cand = dict_row(conn.execute(
            "SELECT c.*, j.title as job_title FROM candidates c "
            "LEFT JOIN jobs j ON c.job_id=j.id WHERE c.id=?",
            (candidate_id,)
        ).fetchone())

        if not cand:
            return json.dumps({"status": "error",
                               "message": f"Candidate '{candidate_id}' not found."})

        prof = dict_row(conn.execute(
            "SELECT * FROM cv_profiles WHERE candidate_id=?", (candidate_id,)
        ).fetchone())

        score_breakdown = {}
        try:
            score_breakdown = json.loads(cand["score_breakdown"]) if cand["score_breakdown"] else {}
        except Exception:
            pass

        if prof:
            # Parse JSON fields back out
            def safe_json(val):
                try:
                    return json.loads(val) if val else []
                except Exception:
                    return []

            profile_data = {
                "name":             prof["name"],
                "email":            prof["sender_email"],
                "phone":            prof["phone"],
                "location":         "",
                "summary":          prof["summary"],
                "skills":           safe_json(prof["skills"]),
                "education":        safe_json(prof["education"]),
                "experience_years": prof["experience_years"],
                "work_experience":  safe_json(prof["work_experience"]),
                "projects":         safe_json(prof["projects"]),
                "certifications":   safe_json(prof["certifications"]),
                "github":           prof["github"],
                "portfolio":        prof["portfolio"],
                "cv_source":        "email",
                "attachment":       prof["attachment_name"],
                "received_on":      prof["received_on"],
            }
        else:
            profile_data = {
                "name":        cand["name"],
                "email":       cand["email"],
                "cv_source":   "manual",
                "note":        "No structured profile — candidate was added manually, not via email intake.",
            }

        return json.dumps({
            "status":          "success",
            "candidate_id":    candidate_id,
            "job":             cand.get("job_title", cand["job_id"]),
            "pipeline_status": cand["status"],
            "ai_score":        cand["score"],
            "score_breakdown": score_breakdown,
            "profile":         profile_data,
        }, indent=2)

    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════
# TOOL 3 — EMAIL INTAKE REPORT (full ranked leaderboard to HR)
# ═════════════════════════════════════════════════════════════════

@tool
def email_intake_report(job_id: str) -> str:
    """
    Email HR a complete ranked leaderboard of ALL candidates processed for a job,
    including their full structured profiles (education, skills, experience, projects).

    The report includes:
      - Ranked list sorted by score (highest first)
      - Each candidate's profile: education, top skills, experience, projects
      - Score, threshold, matched/missing skills, hiring verdict
      - Clear APPROVE / REJECT instructions
      - Pipeline stats: total, shortlisted, rejected, average score

    Call when HR asks:
      "Send me the intake report for INT-001"
      "Email the CV rankings for this job"
      "Send the full candidate summary to HR"

    Args:
        job_id: e.g. 'INT-001', 'FT-001'
    """
    conn = get_conn()
    try:
        job = dict_row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        if not job:
            return json.dumps({"status": "error", "message": f"Job '{job_id}' not found."})

        candidates = dict_rows(conn.execute(
            "SELECT * FROM candidates WHERE job_id=? ORDER BY score DESC", (job_id,)
        ).fetchall())

        if not candidates:
            return json.dumps({
                "status": "error",
                "message": f"No candidates found for {job_id}. Run check_email_inbox first.",
            })

        criteria  = CATEGORY_CRITERIA.get(job["category"], CATEGORY_CRITERIA["full_time"])
        threshold = criteria["shortlist_threshold"]

        shortlisted = [c for c in candidates if c["score"] >= threshold]
        rejected    = [c for c in candidates if c["score"] <  threshold]
        avg_score   = round(sum(c["score"] for c in candidates) / len(candidates), 1)

        # Build rows with profile details
        rows = []
        for rank, c in enumerate(candidates, 1):
            verdict = "✅ SHORTLIST" if c["score"] >= threshold else "❌ REJECT"
            prof    = dict_row(conn.execute(
                "SELECT * FROM cv_profiles WHERE candidate_id=?", (c["id"],)
            ).fetchone())

            edu_str = ""
            proj_str = ""
            if prof:
                try:
                    edu = json.loads(prof["education"] or "[]")
                    edu_str = "; ".join(
                        f"{e.get('degree','')} @ {e.get('institution','')} ({e.get('grade','')})"
                        for e in edu[:2]
                    )
                except Exception:
                    pass
                try:
                    projs = json.loads(prof["projects"] or "[]")
                    proj_str = ", ".join(p.get("name","") for p in projs[:3])
                except Exception:
                    pass

            try:
                breakdown = json.loads(c["score_breakdown"] or "{}")
            except Exception:
                breakdown = {}

            rows.append(
                f"{'─'*55}\n"
                f"Rank #{rank}  {verdict}\n"
                f"Name       : {c['name']}\n"
                f"Email      : {c['email']}\n"
                f"Candidate  : {c['id']}\n"
                f"Score      : {c['score']}/100  (threshold: {threshold})\n"
                f"Education  : {edu_str or 'N/A'}\n"
                f"Exp Years  : {prof['experience_years'] if prof else 'N/A'}\n"
                f"Projects   : {proj_str or 'N/A'}\n"
                f"GitHub     : {prof['github'] if prof and prof['github'] else 'N/A'}\n"
                f"Breakdown  : {json.dumps(breakdown)}\n"
                f"CV File    : {prof['attachment_name'] if prof else 'manual entry'}\n"
            )

        approve_instructions = "\n".join(
            f"  → Approve {c['name']} ({c['id']}): "
            f"'Schedule interview for {c['id']} on YYYY-MM-DD at HH:MM IST'"
            for c in shortlisted
        ) or "  No candidates met the shortlist threshold."

        report = f"""RECRUITMENT INTAKE REPORT
{'='*55}
Job       : {job['title']} ({job_id})
Category  : {job['category'].replace('_',' ').title()}
Date      : {date.today().strftime('%B %d, %Y')}
{'='*55}

PIPELINE SUMMARY
{'─'*55}
Total CVs processed : {len(candidates)}
Shortlisted         : {len(shortlisted)}
Rejected            : {len(rejected)}
Average score       : {avg_score}/100
Shortlist threshold : {threshold}/100

{'='*55}
RANKED CANDIDATES
{'='*55}
{"".join(rows)}

{'='*55}
NEXT ACTIONS — SHORTLISTED
{'='*55}
{approve_instructions}

ASK THE AGENT:
  "Show CV profile for CAND-XXX"  — full JSON profile
  "Screen all candidates for {job_id}"  — auto-process pipeline
  "Schedule interview for CAND-XXX on 2025-05-01 at 2PM IST"
  "Send offer letter to CAND-XXX with salary ₹8 LPA joining 2025-06-01"

— HR Nexus Email Intake System"""

        cfg = email_cfg()
        if not cfg.get("hr_email"):
            return json.dumps({
                "status":  "error",
                "message": "HR_EMAIL not set in .env — cannot send report.",
                "report_preview": report[:500],
            })

        send_email(
            cfg["hr_email"],
            f"📊 Intake Report — {job['title']} ({job_id}) — {len(candidates)} CVs",
            report,
        )

        return json.dumps({
            "status":        "success",
            "job_id":        job_id,
            "emailed_to":    cfg["hr_email"],
            "total":         len(candidates),
            "shortlisted":   len(shortlisted),
            "rejected":      len(rejected),
            "average_score": avg_score,
            "top_candidate": {
                "name":   candidates[0]["name"],
                "score":  candidates[0]["score"],
                "status": candidates[0]["status"],
            } if candidates else None,
            "message": f"Full ranked report emailed to {cfg['hr_email']}.",
        }, indent=2)

    finally:
        conn.close()
