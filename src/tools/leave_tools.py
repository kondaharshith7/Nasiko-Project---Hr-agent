"""
HR Nexus — Leave & Attendance Tools (Module 1)
Covers: leave balance, apply leave, attendance, team availability,
        absence patterns, burnout risk, weekly digest.
"""
import json
from datetime import datetime, timedelta
from langchain_core.tools import tool
from database import get_conn, dict_row, dict_rows


# ══════════════════════════════════════════════════════════════════
# TOOL: CHECK LEAVE BALANCE
# ══════════════════════════════════════════════════════════════════
@tool
def check_leave_balance(employee_name: str) -> str:
    """
    Check current leave balance for any employee.
    Shows annual and sick leave used vs remaining. Flags low balances.
    Call this whenever someone asks about leave balance or before processing a leave request.

    Args:
        employee_name: Full or partial name of the employee e.g. 'Anjali Singh'
    """
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT e.*, lb.annual_used, lb.annual_remaining, lb.sick_used, lb.sick_remaining
               FROM employees e
               JOIN leave_balances lb ON e.id = lb.employee_id
               WHERE LOWER(e.name) LIKE LOWER(?)""",
            (f"%{employee_name}%",)
        ).fetchone()

        if not row:
            return f"Employee '{employee_name}' not found in the system."

        r = dict_row(row)
        total_annual = r["annual_used"] + r["annual_remaining"]
        pct = round(r["annual_remaining"] / total_annual * 100) if total_annual else 0
        warnings = []
        if r["annual_remaining"] < 5:
            warnings.append(f"⚠️ CRITICAL: Only {r['annual_remaining']} annual days left.")
        elif pct < 30:
            warnings.append(f"⚠️ LOW: {r['annual_remaining']} days ({pct}%) remaining.")

        return json.dumps({
            "employee": r["name"],
            "department": r["department"],
            "role": r["role"],
            "annual_leave": {
                "total": total_annual,
                "used": r["annual_used"],
                "remaining": r["annual_remaining"],
                "percent_remaining": f"{pct}%"
            },
            "sick_leave": {
                "used": r["sick_used"],
                "remaining": r["sick_remaining"]
            },
            "warnings": warnings or ["Balance is healthy."]
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: APPLY FOR LEAVE
# ══════════════════════════════════════════════════════════════════
@tool
def apply_for_leave(
    employee_name: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str
) -> str:
    """
    Submit and process a leave request for an employee.
    Checks balance, deducts days, logs attendance, and returns approval status.
    Call this when an employee wants to apply for leave or when HR needs to record approved leave.

    Args:
        employee_name: Full name of the employee
        leave_type: 'annual' or 'sick'
        start_date: YYYY-MM-DD format
        end_date: YYYY-MM-DD format
        reason: Reason for the leave
    """
    conn = get_conn()
    try:
        emp = conn.execute(
            "SELECT e.*, lb.* FROM employees e JOIN leave_balances lb ON e.id=lb.employee_id WHERE LOWER(e.name) LIKE LOWER(?)",
            (f"%{employee_name}%",)
        ).fetchone()

        if not emp:
            return f"Employee '{employee_name}' not found."

        emp = dict_row(emp)
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end   = datetime.strptime(end_date, "%Y-%m-%d").date()
        num_days = sum(1 for i in range((end - start).days + 1)
                       if (start + timedelta(days=i)).weekday() < 5)

        bal_key  = "annual_remaining" if leave_type == "annual" else "sick_remaining"
        used_key = "annual_used"      if leave_type == "annual" else "sick_used"

        if emp[bal_key] < num_days:
            return json.dumps({
                "status":    "REJECTED",
                "reason":    f"Insufficient balance. {emp['name']} has {emp[bal_key]} {leave_type} days remaining but requested {num_days} working days.",
                "balance":   emp[bal_key],
                "requested": num_days
            }, indent=2)

        # Update balance
        conn.execute(
            f"UPDATE leave_balances SET {bal_key}={bal_key}-?, {used_key}={used_key}+? WHERE employee_id=?",
            (num_days, num_days, emp["id"])
        )

        # Log each day in attendance
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                conn.execute(
                    "INSERT OR REPLACE INTO attendance_log (employee_id,name,date,status,leave_type,notes) VALUES (?,?,?,?,?,?)",
                    (emp["id"], emp["name"], str(cur), "on_leave", leave_type, reason)
                )
            cur += timedelta(days=1)

        conn.commit()

        return json.dumps({
            "status":            "APPROVED ✅",
            "employee":          emp["name"],
            "department":        emp["department"],
            "leave_type":        leave_type,
            "from":              start_date,
            "to":                end_date,
            "working_days":      num_days,
            "remaining_balance": emp[bal_key] - num_days,
            "reason":            reason,
            "message":           f"Leave approved and recorded for {emp['name']}. {emp['name']} has {emp[bal_key] - num_days} {leave_type} days remaining after this leave."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: MARK ATTENDANCE
# ══════════════════════════════════════════════════════════════════
@tool
def mark_attendance(employee_name: str, date_str: str, status: str, notes: str = "") -> str:
    """
    Mark or update attendance for an employee on a specific date.
    Status must be: present, absent, late, half_day.
    Call this to log daily attendance or correct attendance records.

    Args:
        employee_name: Full name of the employee
        date_str: Date in YYYY-MM-DD format
        status: One of 'present', 'absent', 'late', 'half_day'
        notes: Optional notes
    """
    valid = ["present", "absent", "late", "half_day"]
    if status not in valid:
        return f"Invalid status '{status}'. Use one of: {valid}"

    conn = get_conn()
    try:
        emp = conn.execute(
            "SELECT * FROM employees WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{employee_name}%",)
        ).fetchone()

        if not emp:
            return f"Employee '{employee_name}' not found."

        emp = dict_row(emp)
        existing = conn.execute(
            "SELECT id FROM attendance_log WHERE employee_id=? AND date=?",
            (emp["id"], date_str)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE attendance_log SET status=?, notes=? WHERE id=?",
                (status, notes, existing["id"])
            )
            action = "Updated"
        else:
            conn.execute(
                "INSERT INTO attendance_log (employee_id,name,date,status,leave_type,notes) VALUES (?,?,?,?,?,?)",
                (emp["id"], emp["name"], date_str, status, "", notes)
            )
            action = "Marked"

        conn.commit()
        return f"✅ {action} attendance for {emp['name']} on {date_str}: **{status}**" + (f" — {notes}" if notes else "")
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET TEAM AVAILABILITY
# ══════════════════════════════════════════════════════════════════
@tool
def get_team_availability(date_str: str, department: str = "") -> str:
    """
    Get full team availability for a given date, optionally filtered by department.
    Shows who is present, on leave, absent, or has no record.
    Call this when HR asks who is available or who is absent on a given date.

    Args:
        date_str: Date in YYYY-MM-DD format (use today's date if not specified)
        department: Optional department filter e.g. 'Engineering' or '' for all
    """
    conn = get_conn()
    try:
        query = "SELECT * FROM employees"
        params = []
        if department:
            query += " WHERE LOWER(department) LIKE LOWER(?)"
            params.append(f"%{department}%")

        employees = dict_rows(conn.execute(query, params).fetchall())

        present, on_leave, absent, no_record = [], [], [], []
        for emp in employees:
            rec = conn.execute(
                "SELECT status, leave_type FROM attendance_log WHERE employee_id=? AND date=?",
                (emp["id"], date_str)
            ).fetchone()

            tag = f"{emp['name']} ({emp['department']})"
            if not rec:
                no_record.append(tag)
            elif rec["status"] in ["present", "late", "half_day"]:
                suffix = f" [{rec['status']}]" if rec["status"] != "present" else ""
                present.append(tag + suffix)
            elif rec["status"] == "on_leave":
                on_leave.append(f"{tag} — {rec['leave_type']} leave")
            elif rec["status"] == "absent":
                absent.append(tag)

        total = len(employees)
        available_pct = round(len(present) / total * 100) if total else 0

        return json.dumps({
            "date":           date_str,
            "department":     department or "All Departments",
            "total_employees": total,
            "availability_rate": f"{available_pct}%",
            "present":        present,
            "on_leave":       on_leave,
            "absent":         absent,
            "no_record":      no_record,
            "summary":        f"{len(present)} present, {len(on_leave)} on leave, {len(absent)} absent, {len(no_record)} unrecorded out of {total} total."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: DETECT ABSENCE PATTERNS
# ══════════════════════════════════════════════════════════════════
@tool
def detect_absence_patterns(employee_name: str) -> str:
    """
    Analyze an employee's attendance history to find concerning patterns:
    Monday/Friday absences, weekend extensions, high-frequency absences.
    Returns a risk rating (NONE / LOW / MEDIUM / HIGH) with specific findings.
    Call this when HR suspects absenteeism or wants to review someone's attendance pattern.

    Args:
        employee_name: Full name of the employee to analyze
    """
    conn = get_conn()
    try:
        absences = dict_rows(conn.execute(
            "SELECT date FROM attendance_log WHERE LOWER(name) LIKE LOWER(?) AND status='absent' ORDER BY date",
            (f"%{employee_name}%",)
        ).fetchall())

        emp = conn.execute(
            "SELECT name, department FROM employees WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{employee_name}%",)
        ).fetchone()

        if not emp:
            return f"Employee '{employee_name}' not found."

        emp = dict_row(emp)

        if not absences:
            return json.dumps({
                "employee": emp["name"],
                "risk_level": "NONE",
                "total_absences": 0,
                "message": "No unplanned absences on record. 🟢"
            }, indent=2)

        monday = friday = pre_wknd = post_wknd = 0
        monthly: dict = {}
        for r in absences:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
            wd = d.weekday()
            mk = d.strftime("%Y-%m")
            if wd == 0: monday += 1
            if wd == 4: friday += 1
            if (d - timedelta(days=1)).weekday() == 6: post_wknd += 1
            if (d + timedelta(days=1)).weekday() == 5: pre_wknd += 1
            monthly[mk] = monthly.get(mk, 0) + 1

        total  = len(absences)
        score  = 0
        patterns = []

        if total >= 3 and monday / total >= 0.4:
            patterns.append(f"MONDAY PATTERN: {monday}/{total} absences are Mondays ({int(monday/total*100)}%)")
            score += 3
        if total >= 3 and friday / total >= 0.4:
            patterns.append(f"FRIDAY PATTERN: {friday}/{total} absences are Fridays ({int(friday/total*100)}%)")
            score += 3
        if pre_wknd + post_wknd >= 3:
            patterns.append(f"WEEKEND EXTENSION: {pre_wknd + post_wknd} absences adjacent to weekends")
            score += 2
        spike_months = [m for m, c in monthly.items() if c >= 3]
        if spike_months:
            patterns.append(f"MONTHLY SPIKE: High absences in {', '.join(spike_months)}")
            score += 2
        if total >= 6:
            patterns.append(f"HIGH FREQUENCY: {total} total unplanned absences")
            score += 2

        risk = "HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW" if score >= 1 else "NONE"
        icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟠", "NONE": "🟢"}[risk]

        return json.dumps({
            "employee":         emp["name"],
            "department":       emp["department"],
            "risk_level":       f"{icon} {risk}",
            "total_absences":   total,
            "patterns_detected": patterns or ["No specific patterns found."],
            "monthly_breakdown": monthly,
            "recommendation":   (
                "Immediate HR meeting recommended. Document formally."
                if risk == "HIGH" else
                "Monitor closely. Informal check-in recommended."
                if risk == "MEDIUM" else
                "No action required but keep monitoring."
            )
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: FLAG ABSENTEEISM RISKS (TEAM-WIDE)
# ══════════════════════════════════════════════════════════════════
@tool
def flag_absenteeism_risks(department: str = "") -> str:
    """
    Scan all employees (or a specific department) for absenteeism risks.
    Returns a ranked list of employees with high unplanned absences.
    Call this when HR wants a team-wide attendance risk report.

    Args:
        department: Optional department filter, or '' for all departments
    """
    conn = get_conn()
    try:
        query = "SELECT DISTINCT name FROM employees"
        params = []
        if department:
            query += " WHERE LOWER(department) LIKE LOWER(?)"
            params.append(f"%{department}%")

        names = [r["name"] for r in conn.execute(query, params).fetchall()]
        risks = []
        for name in names:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM attendance_log WHERE LOWER(name) LIKE LOWER(?) AND status='absent'",
                (f"%{name}%",)
            ).fetchone()["c"]
            if count > 0:
                risks.append({"name": name, "absences": count})

        risks.sort(key=lambda x: x["absences"], reverse=True)
        high   = [r for r in risks if r["absences"] >= 5]
        medium = [r for r in risks if 3 <= r["absences"] < 5]
        low    = [r for r in risks if r["absences"] < 3]

        return json.dumps({
            "scope":         department or "All Departments",
            "high_risk":     [f"{r['name']} ({r['absences']} absences) 🔴" for r in high],
            "medium_risk":   [f"{r['name']} ({r['absences']} absences) 🟡" for r in medium],
            "low_risk":      [f"{r['name']} ({r['absences']} absence)" for r in low],
            "recommendation": f"Run detailed pattern analysis on {len(high)} high-risk employees."
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GENERATE ATTENDANCE REPORT
# ══════════════════════════════════════════════════════════════════
@tool
def generate_attendance_report(employee_name: str = "", month: str = "") -> str:
    """
    Generate a detailed monthly attendance report for one employee or the whole team.
    Shows present/absent/leave breakdown per person.
    Call this when HR asks for attendance reports or monthly summaries.

    Args:
        employee_name: Employee name, or '' for all employees
        month: Month in YYYY-MM format, or '' for the current month
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = get_conn()
    try:
        query = """
            SELECT e.name, e.department, a.status, COUNT(*) as cnt
            FROM attendance_log a
            JOIN employees e ON e.id = a.employee_id
            WHERE a.date LIKE ?
        """
        params: list = [f"{month}%"]
        if employee_name:
            query += " AND LOWER(e.name) LIKE LOWER(?)"
            params.append(f"%{employee_name}%")
        query += " GROUP BY e.name, e.department, a.status ORDER BY e.name"

        rows = dict_rows(conn.execute(query, params).fetchall())

        # Aggregate by employee
        emp_data: dict = {}
        for r in rows:
            n = r["name"]
            if n not in emp_data:
                emp_data[n] = {"name": n, "dept": r["department"],
                               "present": 0, "absent": 0, "on_leave": 0, "late": 0, "half_day": 0}
            s = r["status"]
            if s in emp_data[n]:
                emp_data[n][s] += r["cnt"]

        report = []
        for emp in emp_data.values():
            total_days = sum([emp["present"], emp["absent"], emp["on_leave"], emp["late"], emp["half_day"]])
            working = emp["present"] + emp["late"] + emp["half_day"]
            pct = round(working / total_days * 100) if total_days else 0
            report.append({
                "employee":      emp["name"],
                "department":    emp["dept"],
                "present":       emp["present"],
                "late":          emp["late"],
                "half_day":      emp["half_day"],
                "absent":        emp["absent"],
                "on_leave":      emp["on_leave"],
                "total_days":    total_days,
                "attendance_pct": f"{pct}%",
                "status":        "⚠️ Below 80%" if pct < 80 else "✅ Good"
            })

        return json.dumps({
            "report_month":  month,
            "total_employees": len(report),
            "employees":     report,
            "summary":       f"Report generated for {month}. {sum(1 for r in report if '⚠️' in r['status'])} employees below 80% attendance."
        }, indent=2)
    finally:
        conn.close()
