from django.utils import timezone
from rest_framework import generics, status, serializers
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, APIException

from apps.accounts.models import UserRole
from apps.blockchain.services import BlockchainService
from apps.institutions.models import Institution, InstitutionStatus, IssuerProfile
from apps.institutions.serializers import (
    InstitutionRegisterSerializer,
    InstitutionSerializer,
    ApproveInstitutionSerializer,
    RejectInstitutionSerializer,
)
from apps.institutions.permissions import (
    IsIssuer,
    IsAdmin,
    IsAdminOrOwnInstitution,
    IsAdminOrListOwnInstitution,
)


class InstitutionRegisterView(generics.CreateAPIView):
    permission_classes = [IsIssuer]
    serializer_class = InstitutionRegisterSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if IssuerProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                {"detail": "This issuer user has already registered an institution."}
            )
        institution = serializer.save(status=InstitutionStatus.PENDING)
        IssuerProfile.objects.create(
            user=user,
            institution=institution,
            is_primary_contact=True,
        )
        return institution


class InstitutionListView(generics.ListAPIView):
    permission_classes = [IsAdminOrListOwnInstitution]
    serializer_class = InstitutionSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Institution.objects.all()
        status_filter = self.request.query_params.get('status')
        type_filter = self.request.query_params.get('institution_type')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if type_filter:
            qs = qs.filter(institution_type=type_filter)
        if user.role == UserRole.ISSUER:
            own_ids = IssuerProfile.objects.filter(
                user=user
            ).values_list('institution_id', flat=True)
            qs = qs.filter(id__in=list(own_ids))
        return qs


class InstitutionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrOwnInstitution]
    serializer_class = InstitutionSerializer
    lookup_field = 'pk'
    lookup_url_kwarg = 'id'

    def get_queryset(self):
        return Institution.objects.all()

    def get_object(self):
        try:
            obj = Institution.objects.get(pk=self.kwargs['id'])
        except Institution.DoesNotExist:
            raise NotFound("Institution not found.")
        self.check_object_permissions(self.request, obj)
        return obj


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "State conflict."
    default_code = "CONFLICT"


class ApproveInstitutionView(generics.GenericAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ApproveInstitutionSerializer

    def post(self, request, *args, **kwargs):
        try:
            institution = Institution.objects.get(pk=kwargs['id'])
        except Institution.DoesNotExist:
            raise NotFound("Institution not found.")

        if institution.status != InstitutionStatus.PENDING:
            raise ConflictError({
                "detail": f"Institution has already been reviewed (status={institution.status}).",
                "code": "CONFLICT",
            })

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trust_tier = serializer.validated_data['trust_tier']

        # Model A: Custodial wallet generation
        # If the institution does not already have a custodial key, generate an Ethereum keypair
        # and encrypt+store the private key using Fernet.
        # The custodial wallet is generated and saved FIRST to the database, ensuring that
        # the freshly-updated institution.wallet_address is the single source of truth passed
        # to approve_issuer() for on-chain whitelisting and used for all subsequent signing.
        if not institution.encrypted_private_key:
            institution.generate_custodial_wallet()
            institution.save()
            institution.refresh_from_db()

        # Phase 5: Trigger on-chain approveIssuer() call with the whitelisted wallet address.
        # DB status is updated ONLY if the on-chain call succeeds.
        tx_hash = BlockchainService.approve_issuer(
            wallet_address=institution.wallet_address,
            name=institution.name,
            trust_tier=trust_tier,
            related_object_id=institution.id,
        )

        institution.status = InstitutionStatus.APPROVED
        institution.trust_tier = trust_tier
        institution.reviewed_by = request.user
        institution.reviewed_at = timezone.now()
        institution.rejection_reason = None
        institution.save()

        return Response({
            "id": str(institution.id),
            "status": institution.status,
            "wallet_address": institution.wallet_address,
            "registered_wallet_address": institution.registered_wallet_address,
            "tx_hash": tx_hash,
        }, status=status.HTTP_200_OK)


class RejectInstitutionView(generics.GenericAPIView):
    permission_classes = [IsAdmin]
    serializer_class = RejectInstitutionSerializer

    def post(self, request, *args, **kwargs):
        try:
            institution = Institution.objects.get(pk=kwargs['id'])
        except Institution.DoesNotExist:
            raise NotFound("Institution not found.")

        if institution.status != InstitutionStatus.PENDING:
            raise ConflictError({
                "detail": f"Institution has already been reviewed (status={institution.status}).",
                "code": "CONFLICT",
            })

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        institution.status = InstitutionStatus.REJECTED
        institution.rejection_reason = reason
        institution.trust_tier = None
        institution.reviewed_by = request.user
        institution.reviewed_at = timezone.now()
        institution.save()

        return Response({
            "id": str(institution.id),
            "status": institution.status,
        }, status=status.HTTP_200_OK)
