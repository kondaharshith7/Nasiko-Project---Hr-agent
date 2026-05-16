from tools.leave_tools import (
    check_leave_balance,
    apply_for_leave,
    mark_attendance,
    get_team_availability,
    detect_absence_patterns,
    flag_absenteeism_risks,
    generate_attendance_report,
)
from tools.hr_data_tools import (
    get_all_employees,
    get_salary_details,
    get_hr_summary,
    get_employees_by_department,
)
from tools.jd_tools import (
    generate_job_description,
    format_jd_for_platform,
    get_salary_range,
)
from tools.recruitment_tools import (
    get_candidates,
    add_candidate,
    score_and_shortlist_candidate,
    screen_all_candidates,
    schedule_interview,
    generate_offer_letter,
    get_open_jobs,
    get_recruitment_dashboard,
    update_candidate_status,
)
from tools.email_intake import (
    check_email_inbox,
    get_cv_json_profile,
    email_intake_report,
)

ALL_TOOLS = [
    # Module 1 — Leave & Attendance
    check_leave_balance,
    apply_for_leave,
    mark_attendance,
    get_team_availability,
    detect_absence_patterns,
    flag_absenteeism_risks,
    generate_attendance_report,
    # Module 2 — HR Data
    get_all_employees,
    get_salary_details,
    get_hr_summary,
    get_employees_by_department,
    # Module 3 — JD Generator
    generate_job_description,
    format_jd_for_platform,
    get_salary_range,
    # Module 4 — Recruitment
    get_candidates,
    add_candidate,
    score_and_shortlist_candidate,
    screen_all_candidates,
    schedule_interview,
    generate_offer_letter,
    get_open_jobs,
    get_recruitment_dashboard,
    update_candidate_status,
    # Module 5 — Email CV Intake
    check_email_inbox,
    get_cv_json_profile,
    email_intake_report,
]
