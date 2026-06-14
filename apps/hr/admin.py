from django.contrib import admin

from apps.hr.models import (
    AllowanceConfig,
    Appraisal,
    Attendance,
    CompanyProfile,
    DisciplinaryRecord,
    Employee,
    LeaveRequest,
    LeaveType,
    Payroll,
    PublicHoliday,
)

admin.site.register(LeaveType)
admin.site.register(Employee)
admin.site.register(Attendance)
admin.site.register(LeaveRequest)
admin.site.register(Payroll)
admin.site.register(AllowanceConfig)
admin.site.register(Appraisal)
admin.site.register(DisciplinaryRecord)
admin.site.register(PublicHoliday)
admin.site.register(CompanyProfile)
