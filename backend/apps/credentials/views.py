"""
Credential views for Phase 8 — Blockchain Credential Issuance.

Implements:
- POST /api/v1/credentials/issue/ (single credential)
- POST /api/v1/credentials/issue-batch/ (batch CSV issuance)
- GET /api/v1/credentials/issue-batch/{batch_id}/status/ (batch status tracking)
- GET /api/v1/credentials/ (list credentials)
- GET /api/v1/credentials/{id}/ (credential detail)
"""

import csv
import io
import logging
import uuid
from datetime import datetime
from django.core.cache import cache
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from apps.accounts.models import User, UserRole
from apps.institutions.models import Institution, InstitutionStatus, IssuerProfile
from apps.students.models import StudentProfile
from apps.credentials.models import Credential, CredentialStatus, CredentialShare
from apps.credentials.services import (
    default_ipfs_service,
    compute_document_hash,
)
from apps.credentials.serializers import (
    CredentialSerializer,
    CredentialIssueRequestSerializer,
    BatchIssueRequestSerializer,
)
from apps.blockchain.services import BlockchainService

logger = logging.getLogger(__name__)


def resolve_student(student_email=None, student_id=None, student=None):
    """
    Resolves or initializes a StudentProfile based on provided email or UUID.
    """
    target_id = student_id or student
    if target_id:
        profile = StudentProfile.objects.filter(id=target_id).first()
        if profile:
            return profile

    if student_email:
        clean_email = student_email.strip().lower()
        profile = StudentProfile.objects.filter(user__email__iexact=clean_email).first()
        if profile:
            return profile
        
        # If user exists with role STUDENT, ensure a StudentProfile exists
        user = User.objects.filter(email__iexact=clean_email, role=UserRole.STUDENT).first()
        if user:
            profile, _ = StudentProfile.objects.get_or_create(
                user=user,
                defaults={'full_name': user.email.split('@')[0]},
            )
            return profile

    return None


class IssueCredentialView(generics.GenericAPIView):
    """
    POST /api/v1/credentials/issue/
    
    Accepts a document file and credential metadata from an approved ISSUER.
    
    --------------------------------------------------------------------------
    WHY THE HASH-THEN-STORE-THEN-CHAIN-WRITE ORDER MATTERS:
    --------------------------------------------------------------------------
    In blockchain systems, transactions are permanent, public, and cost gas fees.
    Therefore, the sequence of operations MUST strictly follow this exact order:
    
    1. HASH FIRST:
       We immediately compute the cryptographic SHA-256 fingerprint of the raw
       uploaded document. This allows us to check for duplicates and prevent replay
       attacks before doing any disk I/O, network transfers, or on-chain writes.
       If a duplicate is found, the request fails with zero side effects.
       
    2. STORE SECOND (IPFS):
       We upload the document to IPFS storage to obtain the content identifier (CID).
       The smart contract's `issueCredential(credentialId, documentHash, ipfsCID)`
       function takes `ipfsCID` as a required parameter. Without first uploading to
       IPFS, we would not have the CID to anchor on-chain. Furthermore, if storage
       fails (e.g. disk full or network error), the process aborts before any blockchain
       transaction is submitted, preventing orphaned on-chain records pointing to missing files.
       
    3. CHAIN-WRITE THIRD:
       Anchoring on-chain is the most critical and irreversible step. We only invoke
       the smart contract once the document is verified, unique, hashed, and safely
       stored. The database record is created in `PENDING` status first and is ONLY
       flipped to `ACTIVE` after the blockchain transaction receipt confirms success (`status == 1`).
       If the blockchain call reverts or the node is unreachable, the credential remains
       PENDING and is never falsely marked as ACTIVE.
    --------------------------------------------------------------------------
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = CredentialIssueRequestSerializer

    def post(self, request, *args, **kwargs):
        # 1. Role validation
        if request.user.role != UserRole.ISSUER:
            raise PermissionDenied({
                "detail": "Only users with the ISSUER role can issue credentials.",
                "code": "FORBIDDEN",
            })

        # 2. TWO-LAYER DEFENSE: Server-side check that institution is APPROVED
        # AGENTS.md Principle: Check approval status here before ever contacting the blockchain,
        # even though the smart contract's `onlyApprovedIssuer` modifier also enforces it.
        issuer_profile = IssuerProfile.objects.filter(user=request.user).select_related('institution').first()
        if not issuer_profile or not issuer_profile.institution:
            raise PermissionDenied({
                "detail": "No institution profile associated with this issuer account.",
                "code": "FORBIDDEN",
            })

        institution = issuer_profile.institution
        if institution.status != InstitutionStatus.APPROVED:
            raise PermissionDenied({
                "detail": f"Institution is not approved for credential issuance (status={institution.status}).",
                "code": "FORBIDDEN",
            })

        # 3. Payload validation
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 4. Resolve recipient student
        student = resolve_student(
            student_email=data.get('student_email'),
            student_id=data.get('student_id'),
            student=data.get('student'),
        )
        if not student:
            raise ValidationError({
                "student": "Target student profile could not be found with the provided student_email or student_id."
            })

        # 5. Extract document file
        doc_file = (
            request.FILES.get('document')
            or request.FILES.get('file')
            or request.FILES.get('document_file')
            or (next(iter(request.FILES.values())) if request.FILES else None)
        )
        if not doc_file:
            raise ValidationError({
                "document": "A credential document file (PDF/image) must be uploaded."
            })

        file_bytes = doc_file.read()
        if not file_bytes:
            raise ValidationError({"document": "Uploaded document file is empty."})

        # =====================================================================
        # STEP 1: COMPUTE HASH AND CHECK FOR DUPLICATES
        # =====================================================================
        document_hash = compute_document_hash(file_bytes)
        if Credential.objects.filter(document_hash__iexact=document_hash).exists():
            return Response(
                {
                    "detail": "A credential with this document hash has already been issued.",
                    "code": "DUPLICATE_DOCUMENT",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================================
        # STEP 2: STORE IN IPFS (MOCK SERVICE)
        # =====================================================================
        ipfs_cid = default_ipfs_service.upload_document(file_bytes, filename=doc_file.name)

        # =====================================================================
        # STEP 3: CREATE DATABASE RECORD WITH PENDING STATUS
        # =====================================================================
        credential = Credential.objects.create(
            student=student,
            institution=institution,
            credential_type=data['credential_type'],
            title=data['title'],
            issue_date=data['issue_date'],
            document_hash=document_hash,
            ipfs_cid=ipfs_cid,
            status=CredentialStatus.PENDING,
        )

        # =====================================================================
        # STEP 4: WRITE TO BLOCKCHAIN & AWAIT CONFIRMATION
        # =====================================================================
        try:
            tx_hash = BlockchainService.issue_credential(
                credential_id=credential.id,
                document_hash=document_hash,
                ipfs_cid=ipfs_cid,
                issuer_wallet_address=institution.wallet_address,
                related_object_id=credential.id,
            )
        except Exception as exc:
            # If the blockchain transaction fails or reverts, the Credential row
            # MUST remain PENDING — it is NEVER falsely marked ACTIVE.
            logger.error("Blockchain issuance transaction failed for Credential %s: %s", credential.id, exc)
            raise

        # =====================================================================
        # STEP 5: ONLY AFTER CONFIRMATION, MARK STATUS = ACTIVE
        # =====================================================================
        credential.status = CredentialStatus.ACTIVE
        credential.tx_hash = tx_hash
        credential.save(update_fields=['status', 'tx_hash', 'updated_at'])

        logger.info(
            "Credential %s successfully issued and confirmed on-chain (tx: %s)",
            credential.id,
            tx_hash,
        )

        return Response(
            {
                "id": str(credential.id),
                "status": credential.status,
                "tx_hash": tx_hash,
                "document_hash": credential.document_hash,
                "ipfs_cid": credential.ipfs_cid,
            },
            status=status.HTTP_201_CREATED,
        )


class IssueBatchCredentialView(generics.GenericAPIView):
    """
    POST /api/v1/credentials/issue-batch/
    
    Accepts a CSV + matching document files from an approved ISSUER.
    Validates per-row: bad rows report individual errors without blocking
    the rest of the batch. Valid rows are batched into a single on-chain transaction.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = BatchIssueRequestSerializer

    def post(self, request, *args, **kwargs):
        if request.user.role != UserRole.ISSUER:
            raise PermissionDenied({
                "detail": "Only users with the ISSUER role can perform batch credential issuance.",
                "code": "FORBIDDEN",
            })

        issuer_profile = IssuerProfile.objects.filter(user=request.user).select_related('institution').first()
        if not issuer_profile or not issuer_profile.institution:
            raise PermissionDenied({
                "detail": "No institution profile associated with this issuer account.",
                "code": "FORBIDDEN",
            })

        institution = issuer_profile.institution
        if institution.status != InstitutionStatus.APPROVED:
            raise PermissionDenied({
                "detail": f"Institution is not approved for credential issuance (status={institution.status}).",
                "code": "FORBIDDEN",
            })

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            raise ValidationError({"csv_file": "A CSV file is required."})

        try:
            content = csv_file.read().decode('utf-8-sig')
            reader = list(csv.DictReader(io.StringIO(content)))
        except Exception as exc:
            raise ValidationError({"csv_file": f"Failed to parse CSV file: {exc}"})

        if not reader:
            raise ValidationError({"csv_file": "CSV file contains no data rows."})

        batch_id = uuid.uuid4()
        failures = []
        valid_records = []
        row_num = 0

        # Collect uploaded document files map
        files_map = {}
        for key, f in request.FILES.items():
            if key != 'csv_file':
                files_map[key] = f
                files_map[f.name] = f
        
        doc_list = request.FILES.getlist('documents')

        for row in reader:
            row_num += 1
            student_email = row.get('student_email', '').strip()
            cred_type = row.get('credential_type', '').strip()
            title = row.get('title', '').strip()
            issue_date_str = row.get('issue_date', '').strip()
            doc_filename = row.get('document_filename', '').strip()

            if not student_email or not cred_type or not title or not issue_date_str:
                failures.append({
                    "row": row_num,
                    "student_email": student_email,
                    "reason": "Missing required fields (student_email, credential_type, title, issue_date).",
                })
                continue

            try:
                issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            except ValueError:
                failures.append({
                    "row": row_num,
                    "student_email": student_email,
                    "reason": f"Invalid issue_date format '{issue_date_str}'. Expected YYYY-MM-DD.",
                })
                continue

            student = resolve_student(student_email=student_email)
            if not student:
                failures.append({
                    "row": row_num,
                    "student_email": student_email,
                    "reason": f"Student with email '{student_email}' does not exist.",
                })
                continue

            # Match document file
            matched_file = None
            if doc_filename and doc_filename in files_map:
                matched_file = files_map[doc_filename]
            elif student_email in files_map:
                matched_file = files_map[student_email]
            elif f"{student_email}.pdf" in files_map:
                matched_file = files_map[f"{student_email}.pdf"]
            elif doc_list and (row_num - 1) < len(doc_list):
                matched_file = doc_list[row_num - 1]

            if not matched_file:
                failures.append({
                    "row": row_num,
                    "student_email": student_email,
                    "reason": "Matching document file not provided in upload.",
                })
                continue

            file_bytes = matched_file.read()
            doc_hash = compute_document_hash(file_bytes)

            if Credential.objects.filter(document_hash__iexact=doc_hash).exists():
                failures.append({
                    "row": row_num,
                    "student_email": student_email,
                    "reason": "Duplicate document hash (credential already issued).",
                })
                continue

            cid = default_ipfs_service.upload_document(file_bytes, filename=matched_file.name)

            cred = Credential.objects.create(
                student=student,
                institution=institution,
                credential_type=cred_type,
                title=title,
                issue_date=issue_date,
                document_hash=doc_hash,
                ipfs_cid=cid,
                status=CredentialStatus.PENDING,
            )
            valid_records.append(cred)

        # Batch on-chain execution for valid rows
        tx_hash = None
        if valid_records:
            try:
                tx_hash = BlockchainService.batch_issue_credentials(
                    credential_ids=[c.id for c in valid_records],
                    document_hashes=[c.document_hash for c in valid_records],
                    ipfs_cids=[c.ipfs_cid for c in valid_records],
                    issuer_wallet_address=institution.wallet_address,
                    related_object_id=batch_id,
                )
                for c in valid_records:
                    c.status = CredentialStatus.ACTIVE
                    c.tx_hash = tx_hash
                    c.save(update_fields=['status', 'tx_hash', 'updated_at'])
            except Exception as exc:
                logger.error("Batch issuance on-chain call failed: %s", exc)
                # Keep valid_records in PENDING status, record batch failure
                failures.append({
                    "row": "all_valid_rows",
                    "reason": f"Blockchain transaction failed: {exc}",
                })

        batch_result = {
            "batch_id": str(batch_id),
            "total": row_num,
            "processed": len([c for c in valid_records if c.status == CredentialStatus.ACTIVE]),
            "status": "COMPLETED" if not failures else "PARTIALLY_COMPLETED",
            "failures": failures,
            "issued": [
                {
                    "id": str(c.id),
                    "status": c.status,
                    "document_hash": c.document_hash,
                    "tx_hash": c.tx_hash,
                }
                for c in valid_records
                if c.status == CredentialStatus.ACTIVE
            ],
        }
        cache.set(f"batch_{batch_id}", batch_result, timeout=86400)

        return Response(batch_result, status=status.HTTP_202_ACCEPTED)


class BatchStatusView(generics.GenericAPIView):
    """
    GET /api/v1/credentials/issue-batch/{batch_id}/status/
    
    Returns the processed count, total, and per-row failures for a batch.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, batch_id, *args, **kwargs):
        cached = cache.get(f"batch_{batch_id}")
        if not cached:
            raise NotFound(f"Batch with ID '{batch_id}' not found or expired.")
        return Response({
            "batch_id": cached.get("batch_id"),
            "processed": cached.get("processed", 0),
            "total": cached.get("total", 0),
            "status": cached.get("status"),
            "failures": cached.get("failures", []),
        }, status=status.HTTP_200_OK)


class CredentialListView(generics.ListAPIView):
    """
    GET /api/v1/credentials/
    
    Lists credentials:
    - STUDENT: sees own credentials.
    - ISSUER: sees credentials issued by their institution.
    - ADMIN: sees all credentials.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CredentialSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Credential.objects.all()

        if user.role == UserRole.STUDENT:
            qs = qs.filter(student__user=user)
        elif user.role == UserRole.ISSUER:
            qs = qs.filter(institution__issuer_profiles__user=user)
        elif user.role != UserRole.ADMIN:
            return Credential.objects.none()

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())

        institution_id = self.request.query_params.get('institution_id')
        if institution_id:
            qs = qs.filter(institution_id=institution_id)

        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=student_id)

        return qs.order_by('-created_at')


class CredentialDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/credentials/{id}/
    
    Returns full credential record for owner student, issuing institution, or admin.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CredentialSerializer
    queryset = Credential.objects.all()
    lookup_field = 'id'

    def get_object(self):
        obj = super().get_object()
        user = self.request.user

        if user.role == UserRole.ADMIN:
            return obj
        if user.role == UserRole.STUDENT and obj.student.user_id == user.id:
            return obj
        if user.role == UserRole.ISSUER and IssuerProfile.objects.filter(user=user, institution=obj.institution).exists():
            return obj

        raise PermissionDenied("You do not have permission to view this credential.")
