"""
HR Nexus — JD Generator & Salary Benchmarking Tools (Module 3)
Covers: generate JD, salary ranges, platform formatting, list roles.
"""
import json
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# ── Salary knowledge base ──────────────────────────────────────────
SALARY_DB = {
    "python developer":       {"intern": "15-25k/mo", "junior": "8-15L",  "mid": "15-25L", "senior": "25-45L", "lead": "40-70L"},
    "react developer":        {"intern": "15-25k/mo", "junior": "7-14L",  "mid": "14-22L", "senior": "22-40L", "lead": "35-60L"},
    "data scientist":         {"intern": "20-35k/mo", "junior": "10-18L", "mid": "18-30L", "senior": "30-55L", "lead": "50-90L"},
    "ml engineer":            {"intern": "20-35k/mo", "junior": "12-20L", "mid": "20-35L", "senior": "35-60L", "lead": "55-95L"},
    "devops engineer":        {"intern": "15-25k/mo", "junior": "9-16L",  "mid": "16-28L", "senior": "28-50L", "lead": "45-80L"},
    "product manager":        {"intern": "20-35k/mo", "junior": "12-20L", "mid": "20-35L", "senior": "35-60L", "lead": "55-100L"},
    "fullstack developer":    {"intern": "15-25k/mo", "junior": "8-15L",  "mid": "15-25L", "senior": "25-45L", "lead": "40-70L"},
    "java developer":         {"intern": "15-25k/mo", "junior": "8-15L",  "mid": "15-25L", "senior": "25-45L", "lead": "40-70L"},
    "backend developer":      {"intern": "15-25k/mo", "junior": "8-15L",  "mid": "15-25L", "senior": "25-45L", "lead": "40-70L"},
    "frontend developer":     {"intern": "12-22k/mo", "junior": "7-13L",  "mid": "13-22L", "senior": "22-38L", "lead": "35-60L"},
    "ux designer":            {"intern": "15-25k/mo", "junior": "8-14L",  "mid": "14-22L", "senior": "22-40L", "lead": "35-65L"},
    "qa engineer":            {"intern": "12-20k/mo", "junior": "6-12L",  "mid": "12-20L", "senior": "20-35L", "lead": "30-55L"},
    "cloud architect":        {"junior": "18-28L",    "mid": "28-45L",    "senior": "45-80L", "lead": "70-120L"},
    "marketing manager":      {"intern": "12-20k/mo", "junior": "6-12L",  "mid": "12-22L", "senior": "22-40L", "lead": "35-70L"},
    "hr executive":           {"intern": "10-18k/mo", "junior": "5-9L",   "mid": "9-16L",  "senior": "16-28L", "lead": "25-45L"},
    "financial analyst":      {"intern": "15-25k/mo", "junior": "7-13L",  "mid": "13-22L", "senior": "22-38L", "lead": "35-60L"},
    "vp engineering":         {"lead": "80-180L"},
    "cto":                    {"lead": "100-250L"},
    "engineering manager":    {"lead": "50-100L"},
}

PLATFORMS = {
    "linkedin":     {"max_chars": 2000, "tone": "professional and engaging", "format": "paragraphs with clear sections"},
    "naukri":       {"max_chars": 2500, "tone": "detailed and keyword-rich", "format": "structured with skill keywords"},
    "indeed":       {"max_chars": 1500, "tone": "clear and concise",        "format": "bullet points preferred"},
    "internshala":  {"max_chars": 1200, "tone": "student-friendly",         "format": "structured for freshers/interns"},
    "wellfound":    {"max_chars": 1800, "tone": "startup-culture oriented", "format": "casual yet professional"},
}


# ══════════════════════════════════════════════════════════════════
# TOOL: GENERATE JOB DESCRIPTION
# ══════════════════════════════════════════════════════════════════
@tool
def generate_job_description(
    role_title: str,
    experience_level: str,
    employment_type: str,
    location: str,
    duration: str = "",
    key_skills: str = "",
    company_context: str = ""
) -> str:
    """
    Generate a complete, publish-ready job description from a simple HR request.
    Produces full JD with responsibilities, requirements, salary, and culture.
    Call this whenever HR wants to write a job post or open a new position.

    Args:
        role_title: Job title e.g. 'Senior Python Developer', 'ML Intern', 'VP Engineering'
        experience_level: 'intern', 'junior', 'mid', 'senior', or 'lead'
        employment_type: 'full_time', 'contract', 'internship', 'freelance', or 'leadership'
        location: Work location e.g. 'Bangalore (Hybrid)', 'Remote', 'Mumbai (On-site)'
        duration: Optional duration e.g. '6 months', 'permanent', '3-month contract'
        key_skills: Optional comma-separated skills to emphasize
        company_context: Optional brief company description
    """
    try:
        # Get salary range
        role_key = role_title.lower()
        salary_info = None
        for k, v in SALARY_DB.items():
            if k in role_key or any(w in role_key for w in k.split()):
                salary_info = v.get(experience_level, v.get("mid", "Competitive"))
                break

        llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        prompt = f"""You are an expert technical recruiter. Generate a complete, professional job description.

ROLE: {role_title}
EXPERIENCE LEVEL: {experience_level}
EMPLOYMENT TYPE: {employment_type}
LOCATION: {location}
DURATION: {duration or 'Not specified'}
KEY SKILLS TO EMPHASIZE: {key_skills or 'Derive from role'}
SALARY RANGE: {salary_info or 'Competitive, based on market'}
COMPANY CONTEXT: {company_context or 'A fast-growing tech company'}

Generate a structured JD with these EXACT sections:
1. About the Role (2-3 lines)
2. What You'll Do (5-6 bullet points)
3. What We're Looking For (5-6 bullet points)
4. Nice to Have (3-4 bullet points)
5. What We Offer (4-5 bullet points including salary range if provided)
6. About Us (2-3 lines)

Make it compelling, specific, and free of generic filler. Include real technical depth.
Do NOT use markdown headers with # — use plain section names followed by a colon.
"""

        jd_text = llm.invoke(prompt).content.strip()

        return json.dumps({
            "status":          "✅ JD Generated",
            "role":            role_title,
            "experience":      experience_level,
            "type":            employment_type,
            "location":        location,
            "salary_range":    salary_info or "Competitive",
            "job_description": jd_text,
            "next_steps":      "Use format_jd_for_platform to format for LinkedIn, Naukri, Indeed, Internshala, or Wellfound."
        }, indent=2)
    except Exception as e:
        return f"Error generating JD: {str(e)}"


# ══════════════════════════════════════════════════════════════════
# TOOL: FORMAT JD FOR PLATFORM
# ══════════════════════════════════════════════════════════════════
@tool
def format_jd_for_platform(jd_content: str, platform: str) -> str:
    """
    Reformat a job description for a specific job platform.
    Platforms: linkedin, naukri, indeed, internshala, wellfound.
    Call this after generate_job_description when HR wants to post on a specific platform.

    Args:
        jd_content: The job description text to reformat
        platform: One of 'linkedin', 'naukri', 'indeed', 'internshala', 'wellfound'
    """
    platform = platform.lower().strip()
    if platform not in PLATFORMS:
        return f"Unknown platform '{platform}'. Use: {list(PLATFORMS.keys())}"

    try:
        cfg = PLATFORMS[platform]
        llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
        prompt = f"""Reformat this job description for {platform.title()}.

Platform requirements:
- Max characters: {cfg['max_chars']}
- Tone: {cfg['tone']}
- Format: {cfg['format']}

Original JD:
{jd_content}

Optimize for {platform.title()}'s audience and algorithm. Keep all key information.
For Naukri: add keyword-dense skills section. For LinkedIn: add a strong opening hook.
For Internshala: emphasize learning and stipend. For Wellfound: highlight equity/culture.
"""

        formatted = llm.invoke(prompt).content.strip()
        return json.dumps({
            "platform":   platform.title(),
            "char_count": len(formatted),
            "max_chars":  cfg["max_chars"],
            "formatted_jd": formatted
        }, indent=2)
    except Exception as e:
        return f"Error formatting JD: {str(e)}"


# ══════════════════════════════════════════════════════════════════
# TOOL: GET SALARY RANGE
# ══════════════════════════════════════════════════════════════════
@tool
def get_salary_range(role_title: str, experience_level: str, location: str = "India") -> str:
    """
    Get market salary benchmarks for any role and experience level in India.
    Provides min, median, and max salary ranges for informed compensation decisions.
    Call this when HR wants to know what salary to offer or benchmark internally.

    Args:
        role_title: Job title e.g. 'Python Developer', 'Data Scientist', 'VP Engineering'
        experience_level: 'intern', 'junior' (0-3yr), 'mid' (3-6yr), 'senior' (6-10yr), 'lead' (10yr+)
        location: City/market e.g. 'Bangalore', 'Mumbai', 'Remote', 'India' (default)
    """
    role_key = role_title.lower()
    salary_info = None
    matched_role = None
    for k, v in SALARY_DB.items():
        if k in role_key or any(w in role_key for w in k.split()):
            salary_info = v
            matched_role = k
            break

    if not salary_info:
        return json.dumps({
            "note": f"No exact match for '{role_title}'. Showing general tech market data.",
            "general_ranges": {
                "intern":  "10-25k/month stipend",
                "junior":  "₹6-14L/year",
                "mid":     "₹14-28L/year",
                "senior":  "₹28-55L/year",
                "lead":    "₹50-100L/year"
            },
            "tip": "Ranges vary by company stage, tech stack, and candidate quality."
        }, indent=2)

    tier_range = salary_info.get(experience_level, "Not available for this level")
    all_levels  = salary_info

    location_multiplier = {
        "bangalore": 1.0, "mumbai": 0.95, "delhi": 0.90, "hyderabad": 0.85,
        "pune": 0.85, "chennai": 0.80, "remote": 0.90, "india": 1.0
    }
    loc_key = location.lower()
    mult = next((v for k, v in location_multiplier.items() if k in loc_key), 1.0)

    return json.dumps({
        "role":                role_title,
        "matched_profile":     matched_role,
        "experience_level":    experience_level,
        "location":            location,
        "location_adjustment": f"{mult*100:.0f}% of Bangalore benchmark",
        "salary_range":        tier_range,
        "all_levels":          all_levels,
        "recommendation":      f"Offer in the mid-to-upper range to attract strong candidates. Top candidates expect 20-30% above current CTC.",
        "tip":                 "Budget 10-15% additional for benefits, PF, insurance, and bonuses."
    }, indent=2)
