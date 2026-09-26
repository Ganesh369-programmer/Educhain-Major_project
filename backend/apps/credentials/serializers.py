from rest_framework import serializers
from apps.credentials.models import Credential, CredentialStatus, CredentialShare


class CredentialCreateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=CredentialStatus.choices,
        required=False,
        default=CredentialStatus.PENDING,
    )

    class Meta:
        model = Credential
        fields = (
            'id',
            'student',
            'institution',
            'credential_type',
            'title',
            'issue_date',
            'document_hash',
            'ipfs_cid',
            'status',
            'tx_hash',
        )
        read_only_fields = ('id',)

    def validate_status(self, value):
        if value not in CredentialStatus.values:
            raise serializers.ValidationError(
                f"status must be one of: {', '.join(CredentialStatus.values)}"
            )
        return value

    def validate_document_hash(self, value):
        if not value or len(value) != 66 or not value.startswith('0x'):
            raise serializers.ValidationError(
                "document_hash must be a 66-character 0x-prefixed SHA-256 hex string."
            )
        return value

    def validate(self, attrs):
        # TODO: Phase 8 — at this point in the flow, hash the uploaded document
        # to produce document_hash, upload the document to IPFS to get ipfs_cid,
        # and submit the on-chain issueCredential() call via blockchain.services.
        # Right now (Phase 6) we simply store whatever the caller provided so
        # the DB layer can be exercised by tests.
        document_hash = attrs.get('document_hash')
        if document_hash and Credential.objects.filter(
            document_hash__iexact=document_hash
        ).exists():
            raise serializers.ValidationError(
                {"document_hash": "A credential with this document hash already exists."}
            )
        return attrs

    def to_representation(self, instance):
        return {
            'id': str(instance.id),
            'status': instance.status,
        }


class CredentialSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    student = serializers.SerializerMethodField()
    institution = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Credential
        fields = (
            'id',
            'student',
            'institution',
            'credential_type',
            'title',
            'issue_date',
            'document_hash',
            'ipfs_cid',
            'status',
            'tx_hash',
            'revoked_at',
            'revocation_reason',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    def get_student(self, obj):
        return str(obj.student_id)

    def get_institution(self, obj):
        return str(obj.institution_id)


class CredentialShareSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    credential = serializers.SerializerMethodField()

    class Meta:
        model = CredentialShare
        fields = (
            'id',
            'credential',
            'share_token',
            'visible_fields',
            'expires_at',
            'created_at',
        )
        read_only_fields = fields

    def get_credential(self, obj):
        return str(obj.credential_id)
