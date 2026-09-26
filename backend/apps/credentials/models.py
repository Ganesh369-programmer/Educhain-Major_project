import uuid
from django.db import models
from apps.accounts.models import User, UserRole
from apps.institutions.models import Institution


class StudentProfile(models.Model):
    # TODO: Move this model to apps/accounts/models.py in a later phase.
    # It belongs there per DATABASE_SCHEMA.md (one-to-one with User role=STUDENT).
    # Placed here temporarily because Phase 6 scope forbids touching apps/accounts
    # and the Credential model requires a working StudentProfile FK for tests.
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


class CredentialStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    ACTIVE = 'ACTIVE', 'Active'
    REVOKED = 'REVOKED', 'Revoked'


class Credential(models.Model):
    # Primary identifier — also used on-chain as the credentialId seed.
    # Auto-generated UUID4 so every credential has a globally unique id.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core ownership/issuance links — every credential belongs to exactly one
    # student (recipient) and was issued by exactly one institution.
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='credentials',
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name='issued_credentials',
    )

    # Descriptive metadata about the credential itself.
    # credential_type is a free-form category (Degree, Certificate, etc.)
    # title is the specific program or course name.
    credential_type = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    issue_date = models.DateField()

    # Integrity fields — these are the critical off-chain mirrors of on-chain data.
    # document_hash MUST be unique because it represents the SHA-256 fingerprint of
    # the actual issued document. If two credentials had the same hash, it would mean
    # the same physical document was issued twice (a replay / double-issuance attack).
    # Uniqueness at the DB layer catches accidental duplicates before they ever reach
    # the blockchain (which also enforces this via the contract).
    document_hash = models.CharField(max_length=66, unique=True, db_index=True)
    ipfs_cid = models.CharField(max_length=255)

    # Lifecycle state — PENDING = record created locally, not yet on-chain.
    # ACTIVE = successfully minted on chain.  REVOKED = issuer revoked on-chain.
    # Default PENDING because Phase 8 will flip it to ACTIVE after on-chain confirmation.
    status = models.CharField(
        max_length=20,
        choices=CredentialStatus.choices,
        default=CredentialStatus.PENDING,
        db_index=True,
    )

    # Blockchain transaction bookkeeping.
    # TODO: Phase 8 — populate tx_hash from the blockchain.issue_credential() receipt.
    # TODO: Phase 8 — populate revoked_at + revocation_reason from the revoke flow.
    tx_hash = models.CharField(max_length=66, blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    revocation_reason = models.TextField(blank=True, null=True)

    # Standard timestamps.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'credentials'
        verbose_name = 'credential'
        verbose_name_plural = 'credentials'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['institution']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.title} — {self.student.full_name} ({self.status})"


class CredentialShare(models.Model):
    # Primary identifier for the share record itself.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Every share points back to exactly one credential — a single credential can
    # be shared many times with different audiences / expiry windows.
    credential = models.ForeignKey(
        Credential,
        on_delete=models.CASCADE,
        related_name='shares',
    )

    # share_token is the public identifier used in the verification URL / QR code.
    # It must be unique so a verifier can always resolve exactly one share.
    share_token = models.CharField(max_length=255, unique=True, db_index=True)

    # Selective disclosure: JSON array of field names the student chose to expose
    # for this particular share. Example: ["title", "issue_date", "institution"]
    visible_fields = models.JSONField(default=list)

    # Optional auto-expiry — students can revoke a share earlier by deleting it,
    # but expires_at gives a hands-off self-expire mechanism.
    expires_at = models.DateTimeField(blank=True, null=True)

    # NOTE: CredentialShare has only created_at (no updated_at per DATABASE_SCHEMA.md),
    # since a share is immutable once created — to change it, generate a new share.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'credential_shares'
        verbose_name = 'credential share'
        verbose_name_plural = 'credential shares'
        ordering = ['-created_at']

    def __str__(self):
        return f"Share {self.share_token[:8]}… for {self.credential.title}"
