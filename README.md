# HR Nexus 🤖

**One unified AI-powered HR agent** — combining Leave Management, HR Analytics, JD Generation, and Recruitment Screening into a single intelligent assistant deployed on the Nasiko A2A platform.

---

## What It Does

HR Nexus merges three separate HR workflows into one coherent agent:

| Module | Capabilities |
|--------|-------------|
| 🏖️ **Leave & Attendance** | Check balances, apply leave, mark attendance, team availability, absence patterns, absenteeism risk flags |
| 🤖 **HR Data & Analytics** | Employee directory, salary info, dept headcount, full HR dashboard |
| 📝 **JD Generator** | Write full JDs for 50+ roles, salary benchmarks, format for LinkedIn/Naukri/Indeed |
| 📋 **Recruitment** | Score resumes, shortlist, schedule interviews, send offer letters, pipeline dashboard |

---

## Quick Start

```bash
# 1. Clone / unzip this project
cd hr-nexus

# 2. Create Docker network (one-time)
docker network create agents-net

# 3. Set up environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY (minimum required)

# 4. Build and run
docker-compose up --build
```

Agent runs at: **http://localhost:5000**

> **Note:** The database auto-seeds with 12 employees, 12 candidates, 5 jobs, and 60 days of attendance history on first run. No setup needed — start querying immediately.

---

## Test With curl

Basic test:
```bash
curl -X POST http://localhost:5000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Give me the full HR dashboard"}]
      }
    }
  }'
```

---

## Pre-Loaded Test Data

### Employees (12 total)
| ID | Name | Department | Role | Salary |
|----|------|-----------|------|--------|
| EMP001 | Anjali Singh | Engineering | Senior Python Developer | ₹18L |
| EMP002 | Rahul Mehta | Engineering | React Developer | ₹12L |
| EMP003 | Priya Sharma | Marketing | Marketing Manager | ₹14L |
| EMP004 | Karan Patel | HR | HR Executive | ₹9L |
| EMP005 | Sneha Nair | Engineering | DevOps Engineer | ₹16L |
| EMP006 | Arjun Verma | Finance | Financial Analyst | ₹11L |
| EMP007 | Divya Reddy | Engineering | QA Engineer | ₹10L |
| EMP008 | Rohan Das | Product | Product Manager | ₹20L |
| EMP009 | Meena Iyer | Marketing | Content Strategist | ₹8.5L |
| EMP010 | Vikram Joshi | Engineering | Backend Developer | ₹13.5L |
| EMP011 | Nisha Kapoor | Finance | Accounts Manager | ₹12.5L |
| EMP012 | Amit Tiwari | Engineering | ML Engineer | ₹17L |

### Active Job Openings
| Job ID | Title | Category |
|--------|-------|----------|
| FT-001 | Senior Python Developer | Full-Time |
| INT-001 | ML Intern | Intern |
| CON-001 | DevOps Contractor | Contract |
| FRL-001 | UI/UX Freelancer | Freelance |
| LDR-001 | VP Engineering | Leadership |

### Candidates (12 pre-loaded)
| ID | Name | Job | Status | Score |
|----|------|-----|--------|-------|
| CAND-001 | Rishi Gupta | FT-001 (Python Dev) | shortlisted | 82 |
| CAND-002 | Tanvi Patel | FT-001 | interview | 76 |
| CAND-005 | Aryan Shah | INT-001 (ML Intern) | shortlisted | 78 |
| CAND-006 | Ishita Mishra | INT-001 | offered | 84 |
| CAND-008 | Manoj Pillai | CON-001 (DevOps) | shortlisted | 88 |
| CAND-010 | Neha Jain | FRL-001 (UX) | shortlisted | 90 |
| CAND-011 | Suresh Krishnan | LDR-001 (VP Eng) | interview | 85 |

---

## Complete Test Query Guide

### 🏖️ Leave & Attendance Queries

```
Check leave balance for Anjali Singh
Check leave balance for Vikram Joshi
Apply 3 days annual leave for Rahul Mehta from 2025-04-10 to 2025-04-12, reason: family function
Apply sick leave for Priya Sharma from 2025-04-07 to 2025-04-08, reason: fever
Mark Karan Patel present today
Mark Vikram Joshi absent on 2025-04-07, notes: no notification
Show team availability for today
Show Engineering team availability for 2025-04-15
Generate attendance report for 2025-03
Detect absence patterns for Vikram Joshi
Detect absence patterns for Priya Sharma
Flag all absenteeism risks across the company
Flag absenteeism risks in Engineering
```

### 🤖 HR Data Queries

```
Give me a full HR summary dashboard
Show all employees
Show all Engineering employees
Show all Finance employees
Show salary details for everyone
What is the payroll for Engineering?
What is Anjali Singh's salary?
How many people are in each department?
```

### 📝 JD Generation & Salary Benchmarking

```
Write a JD for a Senior Python Developer, full-time, Bangalore (hybrid), senior level
Generate a job description for an ML Intern, 3-month internship, remote
Create a JD for a VP Engineering, leadership level, Bangalore, permanent
Write a JD for a DevOps Engineer, contract, senior level, Mumbai
What salary should we offer a mid-level Data Scientist in Bangalore?
What is the market salary for a senior React Developer?
What should we pay a junior ML engineer?
Format this JD for LinkedIn: [paste any JD text]
Format the senior Python Developer JD for Naukri
```

### 📋 Recruitment Queries

```
Show the recruitment dashboard
Show all open jobs
Show all shortlisted candidates
Show all candidates for FT-001
Show candidates in the interview stage
Show all intern candidates
Score and screen candidate CAND-004
Screen all applied candidates for FT-001
Schedule interview for CAND-001 on 2025-04-20 at 10:00 AM IST
Schedule interview for CAND-005 on 2025-04-21 at 2:00 PM IST
Generate offer letter for CAND-006 with salary 25,000/month, joining April 1
Generate offer letter for CAND-008 with salary 80L/year, joining March 15
Add new candidate: Name: Rohan Pillai, Email: rohan.p@email.com, Job: FT-001, Resume: 4 years Python/FastAPI, built fintech APIs, AWS certified, strong SQL
Update CAND-002 status to hired
```

### 🔗 Cross-Module Queries (shows unified power)

```
I need to hire a Python developer — write the JD and show me existing candidates for that role
Show me the HR dashboard and then flag any attendance risks
Anjali Singh wants to take leave next week — check her balance and team availability first
Give me a complete onboarding brief: who's on leave, open jobs, recent hires
```

---

## Deployment to Nasiko

### Upload ZIP Method
```bash
# From parent directory
zip -r hr-nexus.zip hr-nexus/ -x "*.pyc" "*/__pycache__/*" "*.env" "*/.git/*"
```

1. Go to Nasiko Dashboard → **Add Agent** → **Upload ZIP**
2. Upload `hr-nexus.zip`
3. Set environment variable: `OPENAI_API_KEY` (required)
4. Optional: Set email variables for real email sending
5. Monitor deployment — status changes to **Running** ✅

---

## Architecture

```
User Message
     │
     ▼
FastAPI A2A Server (/  POST, JSON-RPC 2.0)
     │
     ▼
HRNexusAgent (LangChain AgentExecutor + GPT-4o)
     │
     ├── Module 1: Leave & Attendance Tools (7 tools)
     │     └── SQLite DB (employees, leave_balances, attendance_log)
     │
     ├── Module 2: HR Data Tools (4 tools)
     │     └── SQLite DB (employees, salary)
     │
     ├── Module 3: JD Generator Tools (3 tools)
     │     └── OpenAI GPT-4o + Salary Knowledge Base
     │
     └── Module 4: Recruitment Tools (9 tools)
           └── SQLite DB (candidates, jobs) + OpenAI for scoring
```

**23 tools total** — all in one agent, one endpoint, one deployment.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ Yes | Powers AI features (JD generation, resume scoring) |
| `SENDER_EMAIL` | Optional | Gmail for sending emails |
| `SENDER_PASSWORD` | Optional | Gmail App Password |
| `HR_EMAIL` | Optional | HR manager's email address |
| `HR_NAME` | Optional | HR manager's display name |
| `GOOGLE_CALENDAR_ID` | Optional | Google Calendar for scheduling |

> Without email credentials, all emails are simulated and logged to console. The agent works fully — emails just won't be delivered to real inboxes.
