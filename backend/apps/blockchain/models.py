import uuid
from django.db import models


class BlockchainAction(models.TextChoices):
    APPROVE_ISSUER = 'APPROVE_ISSUER', 'Approve Issuer'
    REVOKE_ISSUER = 'REVOKE_ISSUER', 'Revoke Issuer'
    ISSUE_CREDENTIAL = 'ISSUE_CREDENTIAL', 'Issue Credential'
    REVOKE_CREDENTIAL = 'REVOKE_CREDENTIAL', 'Revoke Credential'


class BlockchainTxStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    FAILED = 'FAILED', 'Failed'


class BlockchainTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tx_hash = models.CharField(max_length=66, unique=True)
    action = models.CharField(
        max_length=50,
        choices=BlockchainAction.choices,
    )
    related_object_id = models.UUIDField(blank=True, null=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=BlockchainTxStatus.choices,
        default=BlockchainTxStatus.PENDING,
    )
    gas_used = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blockchain_transactions'
        verbose_name = 'blockchain transaction'
        verbose_name_plural = 'blockchain transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} - {self.tx_hash} ({self.status})"
