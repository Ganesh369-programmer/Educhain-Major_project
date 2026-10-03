import uuid
from django.db import models
from apps.accounts.models import User, UserRole


class StudentProfile(models.Model):
    """
    Student profile model — the canonical record linking 1-to-1 with a User (role=STUDENT).
    Matches DATABASE_SCHEMA.md. Table name: student_profiles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='student_profile',
        limit_choices_to={'role': UserRole.STUDENT},
    )
    full_name = models.CharField(max_length=255)
    roll_number = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    wallet_address = models.CharField(max_length=42, blank=True, null=True)
    public_profile_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'student_profiles'
        verbose_name = 'student profile'
        verbose_name_plural = 'student profiles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.user.email})"
