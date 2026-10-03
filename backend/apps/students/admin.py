from django.contrib import admin
from apps.students.models import StudentProfile


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'roll_number', 'wallet_address', 'public_profile_enabled', 'created_at')
    list_filter = ('public_profile_enabled',)
    search_fields = ('full_name', 'user__email', 'roll_number', 'wallet_address')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
