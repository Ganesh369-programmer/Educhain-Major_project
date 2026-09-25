import re
from rest_framework import serializers
from apps.institutions.models import Institution, InstitutionType, InstitutionStatus, IssuerProfile


def validate_checksummed_ethereum_address(value):
    if not value or not isinstance(value, str):
        raise serializers.ValidationError("Wallet address is required.")
    if not re.match(r'^0x[a-fA-F0-9]{40}$', value):
        raise serializers.ValidationError(
            "Invalid Ethereum address format. Must be a 42-character checksummed address starting with 0x."
        )
    body = value[2:]
    letters = [c for c in body if c.isalpha()]
    if letters:
        if all(c.islower() for c in letters):
            raise serializers.ValidationError(
                "Wallet address must be EIP-55 checksummed with mixed-case letters; all lowercase is not valid."
            )
        if all(c.isupper() for c in letters):
            raise serializers.ValidationError(
                "Wallet address must be EIP-55 checksummed with mixed-case letters; all uppercase is not valid."
            )
    return value


class InstitutionRegisterSerializer(serializers.ModelSerializer):
    wallet_address = serializers.CharField(
        max_length=42,
        required=True,
        validators=[validate_checksummed_ethereum_address],
    )
    institution_type = serializers.ChoiceField(
        choices=InstitutionType.choices,
        required=True,
    )
    proof_document = serializers.FileField(required=True)

    class Meta:
        model = Institution
        fields = (
            'id',
            'name',
            'institution_type',
            'official_website',
            'official_email_domain',
            'registration_number',
            'gst_number',
            'proof_document',
            'wallet_address',
        )
        read_only_fields = ('id',)

    def validate(self, attrs):
        wallet_address = attrs.get('wallet_address')
        if wallet_address and Institution.objects.filter(
            wallet_address__iexact=wallet_address
        ).exists():
            raise serializers.ValidationError(
                {"wallet_address": "This wallet address is already registered."}
            )
        registration_number = attrs.get('registration_number')
        if registration_number and Institution.objects.filter(
            registration_number=registration_number
        ).exists():
            raise serializers.ValidationError(
                {"registration_number": "This registration number is already registered."}
            )
        return attrs

    def to_representation(self, instance):
        return {
            'id': str(instance.id),
            'status': instance.status,
        }


class InstitutionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = (
            'id',
            'name',
            'institution_type',
            'official_website',
            'official_email_domain',
            'registration_number',
            'gst_number',
            'proof_document',
            'wallet_address',
            'status',
            'trust_tier',
            'reviewed_by',
            'reviewed_at',
            'rejection_reason',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    def get_reviewed_by(self, obj):
        if obj.reviewed_by:
            return str(obj.reviewed_by.id)
        return None


class ApproveInstitutionSerializer(serializers.Serializer):
    trust_tier = serializers.IntegerField(required=True, min_value=1, max_value=3)

    def validate_trust_tier(self, value):
        if value not in (1, 2, 3):
            raise serializers.ValidationError("trust_tier must be 1, 2, or 3.")
        return value


class RejectInstitutionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)
