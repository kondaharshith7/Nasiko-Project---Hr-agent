"""
HR Nexus — HR Data Query Tools (Module 2)
Covers: employee queries, department info, salary, HR dashboard.
"""
import json
from langchain_core.tools import tool
from database import get_conn, dict_row, dict_rows


# ══════════════════════════════════════════════════════════════════
# TOOL: GET ALL EMPLOYEES
# ══════════════════════════════════════════════════════════════════
@tool
def get_all_employees(department: str = "", role_filter: str = "") -> str:
    """
    List all employees with their department, role, and salary.
    Optionally filter by department or role.
    Call this when HR wants to see the employee list or headcount.

    Args:
        department: Filter by department name e.g. 'Engineering', or '' for all
        role_filter: Filter by role keyword e.g. 'Developer', or ''
    """
    conn = get_conn()
    try:
        query = "SELECT * FROM employees WHERE 1=1"
        params = []
        if department:
            query += " AND LOWER(department) LIKE LOWER(?)"
            params.append(f"%{department}%")
        if role_filter:
            query += " AND LOWER(role) LIKE LOWER(?)"
            params.append(f"%{role_filter}%")
        query += " ORDER BY department, name"

        employees = dict_rows(conn.execute(query, params).fetchall())

        # Group by department
        by_dept: dict = {}
        for e in employees:
            d = e["department"]
            if d not in by_dept:
                by_dept[d] = []
            by_dept[d].append({
                "id":         e["id"],
                "name":       e["name"],
                "email":      e["email"],
                "role":       e["role"],
                "hire_date":  e["hire_date"],
                "salary_lpa": f"₹{e['salary']/100000:.1f}L"
            })

        return json.dumps({
            "total_employees": len(employees),
            "departments":     list(by_dept.keys()),
            "by_department":   by_dept
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET SALARY DETAILS
# ══════════════════════════════════════════════════════════════════
@tool
def get_salary_details(employee_name: str = "", department: str = "") -> str:
    """
    Get salary information for a specific employee or entire department.
    Shows individual salary, department totals, and averages.
    Call this for payroll queries, salary reviews, or budget analysis.

    Args:
        employee_name: Employee name for individual query, or '' for team view
        department: Department name for department-level view, or ''
    """
    conn = get_conn()
    try:
        query = "SELECT name, department, role, salary FROM employees WHERE 1=1"
        params = []
        if employee_name:
            query += " AND LOWER(name) LIKE LOWER(?)"
            params.append(f"%{employee_name}%")
        if department:
            query += " AND LOWER(department) LIKE LOWER(?)"
            params.append(f"%{department}%")
        query += " ORDER BY department, salary DESC"

        rows = dict_rows(conn.execute(query, params).fetchall())

        if not rows:
            return "No matching employees found."

        # Compute dept summaries
        dept_stats: dict = {}
        for r in rows:
            d = r["department"]
            if d not in dept_stats:
                dept_stats[d] = {"total": 0, "count": 0, "employees": []}
            dept_stats[d]["total"]   += r["salary"]
            dept_stats[d]["count"]   += 1
            dept_stats[d]["employees"].append({
                "name":       r["name"],
                "role":       r["role"],
                "salary_lpa": f"₹{r['salary']/100000:.1f}L",
                "salary_monthly": f"₹{r['salary']//12:,}"
            })

        result = {
            "total_employees": len(rows),
            "total_payroll_lpa": f"₹{sum(r['salary'] for r in rows)/100000:.1f}L",
            "department_breakdown": {
                d: {
                    "headcount":       v["count"],
                    "total_payroll":   f"₹{v['total']/100000:.1f}L/yr",
                    "average_salary":  f"₹{(v['total']//v['count'])/100000:.1f}L/yr",
                    "employees":       v["employees"]
                }
                for d, v in dept_stats.items()
            }
        }
        return json.dumps(result, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET HR SUMMARY / DASHBOARD
# ══════════════════════════════════════════════════════════════════
@tool
def get_hr_summary() -> str:
    """
    Get a complete HR dashboard overview: headcount by department,
    hiring pipeline summary, leave stats, attendance, salary totals.
    Call this when HR asks for an overview, dashboard, or full HR summary.
    """
    conn = get_conn()
    try:
        from datetime import date
        today = date.today().isoformat()
        month = today[:7]

        # Headcount
        total_emp = conn.execute("SELECT COUNT(*) as c FROM employees").fetchone()["c"]
        dept_counts = dict_rows(conn.execute(
            "SELECT department, COUNT(*) as c FROM employees GROUP BY department ORDER BY c DESC"
        ).fetchall())

        # Hiring pipeline
        pipeline = dict_rows(conn.execute(
            "SELECT status, COUNT(*) as c FROM candidates GROUP BY status ORDER BY c DESC"
        ).fetchall())

        # Leave stats (this month)
        on_leave_today = conn.execute(
            "SELECT COUNT(DISTINCT employee_id) as c FROM attendance_log WHERE date=? AND status='on_leave'",
            (today,)
        ).fetchone()["c"]

        low_bal = conn.execute(
            "SELECT COUNT(*) as c FROM leave_balances WHERE annual_remaining < 5"
        ).fetchone()["c"]

        # Attendance this month
        absent_month = conn.execute(
            "SELECT COUNT(DISTINCT employee_id) as c FROM attendance_log WHERE date LIKE ? AND status='absent'",
            (f"{month}%",)
        ).fetchone()["c"]

        # Payroll
        payroll = conn.execute("SELECT SUM(salary) as total FROM employees").fetchone()["total"] or 0

        # Active jobs
        active_jobs = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status='active'").fetchone()["c"]

        return json.dumps({
            "📊 HEADCOUNT": {
                "total_employees":     total_emp,
                "by_department":       {r["department"]: r["c"] for r in dept_counts}
            },
            "💼 HIRING PIPELINE": {
                "active_job_openings": active_jobs,
                "pipeline":            {r["status"]: r["c"] for r in pipeline}
            },
            "🏖️ LEAVE STATUS": {
                "on_leave_today":      on_leave_today,
                "employees_low_balance": low_bal,
            },
            "📅 ATTENDANCE (THIS MONTH)": {
                "distinct_absences":   absent_month,
            },
            "💰 PAYROLL": {
                "annual_payroll":      f"₹{payroll/10000000:.2f}Cr",
                "monthly_payroll":     f"₹{(payroll//12)/100000:.1f}L"
            }
        }, indent=2)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# TOOL: GET EMPLOYEES BY DEPARTMENT
# ══════════════════════════════════════════════════════════════════
@tool
def get_employees_by_department(department: str) -> str:
    """
    Get all employees in a specific department with their details.
    Call this when HR asks about a specific team or department.

    Args:
        department: Department name e.g. 'Engineering', 'Marketing', 'Finance'
    """
    conn = get_conn()
    try:
        rows = dict_rows(conn.execute(
            """SELECT e.*, lb.annual_remaining, lb.sick_remaining
               FROM employees e
               LEFT JOIN leave_balances lb ON e.id=lb.employee_id
               WHERE LOWER(e.department) LIKE LOWER(?)
               ORDER BY e.name""",
            (f"%{department}%",)
        ).fetchall())

        if not rows:
            return f"No employees found in department: {department}"

        return json.dumps({
            "department":      rows[0]["department"],
            "headcount":       len(rows),
            "team_payroll_lpa": f"₹{sum(r['salary'] for r in rows)/100000:.1f}L",
            "employees": [{
                "id":              r["id"],
                "name":            r["name"],
                "email":           r["email"],
                "role":            r["role"],
                "hire_date":       r["hire_date"],
                "salary_lpa":      f"₹{r['salary']/100000:.1f}L",
                "annual_leave_remaining": r["annual_remaining"],
                "sick_leave_remaining":   r["sick_remaining"],
            } for r in rows]
        }, indent=2)
    finally:
        conn.close()
