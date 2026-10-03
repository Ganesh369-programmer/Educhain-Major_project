"""
Serializers for the verification app (Phase 9).
These serialize only non-sensitive, publicly safe fields — never student PII.
"""

from rest_framework import serializers
from apps.verification.models import VerificationRecord, VerificationResult


class VerifyCredentialResponseSerializer(serializers.Serializer):
    """
    Response shape for GET /verify/{credential_id}/.
    Contains only non-PII fields that a public verifier needs to see.
    """
    result = serializers.ChoiceField(choices=VerificationResult.choices)
    credential_id = serializers.UUIDField()
    credential_type = serializers.CharField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_null=True)
    institution_name = serializers.CharField(required=False, allow_null=True)
    issue_date = serializers.DateField(required=False, allow_null=True)
    issuer_trust_tier = serializers.IntegerField(required=False, allow_null=True)
    # Per Open Question #1: if issuer's authorization was since revoked,
    # include an explicit warning rather than silently marking the credential INVALID.
    issuer_status_warning = serializers.CharField(required=False, allow_null=True)


class VerifyUploadRequestSerializer(serializers.Serializer):
    """
    Validates incoming POST /verify/upload/ multipart request.
    Expects a file upload and the credential_id to compare against.
    """
    credential_id = serializers.UUIDField()
    document = serializers.FileField()


class VerifyUploadResponseSerializer(serializers.Serializer):
    """
    Response shape for POST /verify/upload/.
    Shows whether the uploaded document's hash matches the stored/on-chain hash.
    """
    result = serializers.ChoiceField(choices=VerificationResult.choices)
    credential_id = serializers.UUIDField()
    hash_match = serializers.BooleanField()
    computed_hash = serializers.CharField(required=False, allow_null=True)
    stored_hash = serializers.CharField(required=False, allow_null=True)


class VerificationRecordSerializer(serializers.ModelSerializer):
    """
    Serializes VerificationRecord for the history endpoint.
    """
    class Meta:
        model = VerificationRecord
        fields = [
            'id', 'credential', 'verifier', 'result',
            'verified_at', 'ip_address',
        ]
        read_only_fields = fields
