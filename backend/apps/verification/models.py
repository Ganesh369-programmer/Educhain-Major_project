import uuid
from django.db import models
from django.conf import settings
from apps.credentials.models import Credential


class VerificationResult(models.TextChoices):
    VALID = 'VALID', 'Valid'
    REVOKED = 'REVOKED', 'Revoked'
    INVALID = 'INVALID', 'Invalid'
    NOT_FOUND = 'NOT_FOUND', 'Not Found'


class VerificationRecord(models.Model):
    """
    Audit log of verification attempts per docs/DATABASE_SCHEMA.md.
    Records every verification query (public anonymous or authenticated verifier).
    If a query searches for a nonexistent or invalid credential ID,
    credential is set to null with result=NOT_FOUND to maintain a complete security audit log.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verification_records',
    )
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verification_records',
    )
    result = models.CharField(
        max_length=20,
        choices=VerificationResult.choices,
    )
    verified_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=45, blank=True, null=True)

    class Meta:
        db_table = 'verification_records'
        verbose_name = 'verification record'
        verbose_name_plural = 'verification records'
        ordering = ['-verified_at']

    def __str__(self):
        cred_str = str(self.credential_id) if self.credential_id else "None"
        return f"Verification({cred_str}, result={self.result}, at={self.verified_at})"
