import uuid
from django.db import models
from apps.accounts.models import User, UserRole


class InstitutionType(models.TextChoices):
    UNIVERSITY = 'UNIVERSITY', 'University'
    PRIVATE_TRAINING_INSTITUTE = 'PRIVATE_TRAINING_INSTITUTE', 'Private Training Institute'
    COMPANY = 'COMPANY', 'Company'
    NGO = 'NGO', 'NGO'


class InstitutionStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    institution_type = models.CharField(
        max_length=50,
        choices=InstitutionType.choices,
    )
    official_website = models.URLField(blank=True, null=True)
    official_email_domain = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=100)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    proof_document = models.FileField(upload_to='institution_proofs/')
    wallet_address = models.CharField(max_length=42, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=InstitutionStatus.choices,
        default=InstitutionStatus.PENDING,
        db_index=True,
    )
    trust_tier = models.PositiveSmallIntegerField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='reviewed_institutions',
        limit_choices_to={'role': UserRole.ADMIN},
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'institutions'
        verbose_name = 'institution'
        verbose_name_plural = 'institutions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.status})"


class IssuerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='issuer_profiles',
        limit_choices_to={'role': UserRole.ISSUER},
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name='issuer_profiles',
    )
    is_primary_contact = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'issuer_profiles'
        verbose_name = 'issuer profile'
        verbose_name_plural = 'issuer profiles'
        unique_together = [('user', 'institution')]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} @ {self.institution.name}"
