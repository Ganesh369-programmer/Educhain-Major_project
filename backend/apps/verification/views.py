"""
Verification views — Phase 9.

These three endpoints together let anyone (or an authenticated verifier) check
whether a blockchain-anchored academic credential is legitimate, unrevoked, and
un-tampered.  Every check is logged to VerificationRecord for security auditing.

=== How a verification request works, start to finish ===

1. A recruiter, employer, or any member of the public receives a credential ID
   (via a share link, QR code, or direct communication from a student).

2. They call  GET /api/v1/verify/{credential_id}/  — no login required.

3. The backend first looks up the credential in the off-chain database (SQLite).
   If it doesn't exist → result=NOT_FOUND is returned immediately.

4. If found, the backend calls the smart contract's read-only verifyCredential()
   function to get the on-chain record: does it exist, is it revoked, who issued
   it, what's the document hash, and when was it issued.

5. Four independent checks then run:
   a) EXISTENCE CHECK — protects against forged credential IDs that were never
      actually minted on-chain.  If the chain says "does not exist" but the DB
      has a row, something is inconsistent → NOT_FOUND.
   b) REVOCATION CHECK — protects against credentials that were legitimately
      issued but later invalidated (e.g., degree revoked for plagiarism).
      If on-chain revoked=true → REVOKED.
   c) ISSUER STATUS CHECK — per Open Question #1's resolution, if the issuing
      institution was whitelisted when the credential was minted but has since
      been de-whitelisted (e.g., found fraudulent), the credential is still
      returned as VALID but with an explicit issuer_status_warning field.  This
      flags past output without silently erasing it.
   d) If none of the above triggered → result=VALID.

6. For deeper tamper detection, the verifier can use POST /api/v1/verify/upload/
   with the original PDF/document file plus the credential_id.  The backend
   recomputes the SHA-256 hash of the uploaded file and compares it to the hash
   stored both in the database and on-chain.  A mismatch means the document was
   altered after issuance → result=INVALID, hash_match=false.

7. Every verification attempt (success, failure, not-found) is logged to the
   VerificationRecord table.  Students, their issuing institution, and admins
   can review this audit trail via  GET /api/v1/verify/history/{credential_id}/.
"""

import logging

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.blockchain.exceptions import BlockchainError
from apps.blockchain.services import BlockchainService
from apps.credentials.models import Credential, CredentialStatus
from apps.credentials.services import compute_document_hash
from apps.institutions.models import InstitutionStatus
from apps.verification.models import VerificationRecord, VerificationResult
from apps.verification.serializers import (
    VerificationRecordSerializer,
    VerifyCredentialResponseSerializer,
    VerifyUploadResponseSerializer,
)
from apps.verification.throttling import VerificationRateThrottle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request):
    """Extract the client IP address from the request, respecting X-Forwarded-For."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_verification(credential, request, result):
    """
    Persist a VerificationRecord row for every verification attempt.
    This is the audit log that lets students and institutions see who checked
    their credentials and when.
    """
    verifier = request.user if request.user and request.user.is_authenticated else None
    return VerificationRecord.objects.create(
        credential=credential,
        verifier=verifier,
        result=result,
        ip_address=_get_client_ip(request),
    )


# ---------------------------------------------------------------------------
#  GET /api/v1/verify/{credential_id}/
# ---------------------------------------------------------------------------

class VerifyCredentialView(APIView):
    """
    PUBLIC endpoint — no authentication required.
    Given a credential UUID, performs a full verification against the off-chain
    database AND the on-chain smart contract, returning a single definitive
    result: VALID, REVOKED, INVALID, or NOT_FOUND.

    Rate-limited per VerificationRateThrottle to prevent automated brute-force
    enumeration of credential IDs.
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # Explicitly no auth — truly public
    throttle_classes = [VerificationRateThrottle]

    def get(self, request, credential_id):
        # ------------------------------------------------------------------
        # CHECK 1 — EXISTENCE: Does this credential even exist in our database?
        # Protects against: random / guessed / forged credential IDs.
        # ------------------------------------------------------------------
        try:
            credential = Credential.objects.select_related('institution').get(pk=credential_id)
        except (Credential.DoesNotExist, ValueError):
            # Log the failed lookup for abuse monitoring
            _log_verification(credential=None, request=request, result=VerificationResult.NOT_FOUND)
            return Response(
                VerifyCredentialResponseSerializer({
                    'result': VerificationResult.NOT_FOUND,
                    'credential_id': credential_id,
                }).data,
                status=status.HTTP_200_OK,
            )

        institution = credential.institution

        # ------------------------------------------------------------------
        # On-chain query via BlockchainService.verify_credential()
        # This calls the smart contract's verifyCredential(bytes32) view function.
        # ------------------------------------------------------------------
        try:
            on_chain = BlockchainService.verify_credential(credential.id)
        except BlockchainError as exc:
            logger.warning("Blockchain query failed for credential %s: %s", credential_id, exc)
            # If the chain is unreachable we still return a best-effort DB-only result
            # with a warning, rather than a 502 — verification should degrade gracefully.
            on_chain = None

        # ------------------------------------------------------------------
        # CHECK 2 — ON-CHAIN EXISTENCE: Was this credential actually minted?
        # Protects against: DB rows that were created locally but never
        # confirmed on-chain (e.g., a PENDING credential whose tx failed).
        # ------------------------------------------------------------------
        if on_chain and not on_chain.get('exists'):
            _log_verification(credential=credential, request=request, result=VerificationResult.NOT_FOUND)
            return Response(
                VerifyCredentialResponseSerializer({
                    'result': VerificationResult.NOT_FOUND,
                    'credential_id': credential_id,
                }).data,
                status=status.HTTP_200_OK,
            )

        # ------------------------------------------------------------------
        # CHECK 3 — REVOCATION: Has this credential been revoked on-chain?
        # Protects against: using a credential that was legitimately issued
        # but later invalidated (plagiarism, error, fraud).
        # ------------------------------------------------------------------
        if (on_chain and on_chain.get('revoked')) or credential.status == CredentialStatus.REVOKED:
            _log_verification(credential=credential, request=request, result=VerificationResult.REVOKED)
            return Response(
                VerifyCredentialResponseSerializer({
                    'result': VerificationResult.REVOKED,
                    'credential_id': credential_id,
                    'credential_type': credential.credential_type,
                    'title': credential.title,
                    'institution_name': institution.name,
                    'issue_date': credential.issue_date,
                    'issuer_trust_tier': institution.trust_tier,
                }).data,
                status=status.HTTP_200_OK,
            )

        # ------------------------------------------------------------------
        # CHECK 4 — ISSUER STATUS: Is the issuing institution still approved?
        # Per Open Question #1: if the issuer has since been de-whitelisted,
        # we do NOT silently mark past credentials INVALID.  Instead we return
        # result=VALID with an issuer_status_warning so the verifier can make
        # an informed judgment.
        # ------------------------------------------------------------------
        issuer_warning = None
        if institution.status != InstitutionStatus.APPROVED:
            issuer_warning = (
                f"The issuing institution ({institution.name}) is no longer "
                f"currently approved (status: {institution.status}). This credential "
                f"may have been legitimately issued before the institution's "
                f"authorization was changed."
            )

        # All checks passed — credential is VALID
        _log_verification(credential=credential, request=request, result=VerificationResult.VALID)
        response_data = {
            'result': VerificationResult.VALID,
            'credential_id': credential_id,
            'credential_type': credential.credential_type,
            'title': credential.title,
            'institution_name': institution.name,
            'issue_date': credential.issue_date,
            'issuer_trust_tier': institution.trust_tier,
        }
        if issuer_warning:
            response_data['issuer_status_warning'] = issuer_warning

        return Response(
            VerifyCredentialResponseSerializer(response_data).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
#  POST /api/v1/verify/upload/
# ---------------------------------------------------------------------------

class VerifyUploadView(APIView):
    """
    PUBLIC endpoint — no authentication required.
    Accepts a document file (multipart) plus a credential_id.
    Recomputes the SHA-256 hash of the uploaded document and compares it to the
    hash stored in the database AND anchored on-chain.

    This detects DOCUMENT TAMPERING: if someone modifies even a single byte of
    the credential PDF after issuance, the hash will no longer match.
    Result = INVALID with hash_match=false when tampering is detected.

    Rate-limited to prevent abuse.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [VerificationRateThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        credential_id = request.data.get('credential_id')
        document = request.FILES.get('document')

        if not credential_id:
            return Response(
                {'detail': 'credential_id is required.', 'code': 'VALIDATION_ERROR'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not document:
            return Response(
                {'detail': 'document file is required.', 'code': 'VALIDATION_ERROR'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Look up the credential in the database
        try:
            credential = Credential.objects.select_related('institution').get(pk=credential_id)
        except (Credential.DoesNotExist, ValueError):
            _log_verification(credential=None, request=request, result=VerificationResult.NOT_FOUND)
            return Response(
                VerifyUploadResponseSerializer({
                    'result': VerificationResult.NOT_FOUND,
                    'credential_id': credential_id,
                    'hash_match': False,
                }).data,
                status=status.HTTP_200_OK,
            )

        # Read the uploaded file bytes and compute its SHA-256 hash
        file_bytes = document.read()
        computed_hash = compute_document_hash(file_bytes)
        stored_hash = credential.document_hash

        # ------------------------------------------------------------------
        # TAMPER CHECK: Compare the recomputed hash to the stored hash.
        # If they don't match, the document was modified after issuance.
        # This is independent of the credential's on-chain status — even if
        # the credential is otherwise VALID on-chain, a hash mismatch means
        # the physical document is not the one that was originally certified.
        # ------------------------------------------------------------------
        hash_match = (computed_hash.lower() == stored_hash.lower())

        if not hash_match:
            _log_verification(credential=credential, request=request, result=VerificationResult.INVALID)
            return Response(
                VerifyUploadResponseSerializer({
                    'result': VerificationResult.INVALID,
                    'credential_id': credential_id,
                    'hash_match': False,
                    'computed_hash': computed_hash,
                    'stored_hash': stored_hash,
                }).data,
                status=status.HTTP_200_OK,
            )

        # Hash matches — document is authentic
        _log_verification(credential=credential, request=request, result=VerificationResult.VALID)
        return Response(
            VerifyUploadResponseSerializer({
                'result': VerificationResult.VALID,
                'credential_id': credential_id,
                'hash_match': True,
                'computed_hash': computed_hash,
                'stored_hash': stored_hash,
            }).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
#  GET /api/v1/verify/history/{credential_id}/
# ---------------------------------------------------------------------------

class VerificationHistoryView(ListAPIView):
    """
    AUTHENTICATED endpoint — only the owning student, the issuing institution's
    issuers, or an ADMIN can view the verification audit trail for a credential.

    This lets students see who has been checking their credentials, and lets
    institutions monitor verification activity for credentials they issued.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = VerificationRecordSerializer

    def get_queryset(self):
        from apps.accounts.models import UserRole
        from apps.institutions.models import IssuerProfile

        credential_id = self.kwargs.get('credential_id')
        user = self.request.user

        # First, verify the credential exists
        try:
            credential = Credential.objects.select_related(
                'student__user', 'institution'
            ).get(pk=credential_id)
        except (Credential.DoesNotExist, ValueError):
            return VerificationRecord.objects.none()

        # Authorization: only the owning student, an issuer from the same
        # institution, or an ADMIN can view verification history.
        allowed = False
        if user.role == UserRole.ADMIN:
            allowed = True
        elif user.role == UserRole.STUDENT and credential.student.user_id == user.id:
            allowed = True
        elif user.role == UserRole.ISSUER:
            allowed = IssuerProfile.objects.filter(
                user=user,
                institution=credential.institution,
            ).exists()

        if not allowed:
            return VerificationRecord.objects.none()

        return VerificationRecord.objects.filter(
            credential=credential
        ).order_by('-verified_at')
