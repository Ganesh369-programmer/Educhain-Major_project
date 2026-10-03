"""
Tests for the verification app (Phase 9).

Test strategy:
  1. Negative cases FIRST (as requested): NOT_FOUND, REVOKED, INVALID (tampered doc), rate limiting.
  2. Happy path last: verify an ACTIVE credential → VALID.
  3. History endpoint: auth checks and data accuracy.
"""

import hashlib
import uuid
from datetime import date
from io import BytesIO
from unittest.mock import patch, MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserRole
from apps.credentials.models import Credential, CredentialStatus
from apps.credentials.services import compute_document_hash
from apps.institutions.models import (
    Institution,
    InstitutionStatus,
    InstitutionType,
    IssuerProfile,
)
from apps.students.models import StudentProfile
from apps.verification.models import VerificationRecord, VerificationResult


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return f'Bearer {refresh.access_token}'


def make_student(email='verify-student@test.local'):
    user = User.objects.create_user(
        email=email,
        password='Password123!',
        role=UserRole.STUDENT,
    )
    return StudentProfile.objects.create(user=user, full_name='Verification Student')


def make_institution(inst_status=InstitutionStatus.APPROVED, wallet='0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B', **kwargs):
    defaults = {
        'name': 'Verification University',
        'institution_type': InstitutionType.UNIVERSITY,
        'official_email_domain': 'verifyu.edu',
        'registration_number': f'VU-{uuid.uuid4().hex[:6]}',
        'proof_document': 'verifyu/proof.pdf',
        'wallet_address': wallet,
        'status': inst_status,
        'trust_tier': 1,
    }
    defaults.update(kwargs)
    return Institution.objects.create(**defaults)


# The "original" document bytes that a credential was issued for
ORIGINAL_DOCUMENT = b'%PDF-1.4 official transcript content for verification test'
ORIGINAL_HASH = compute_document_hash(ORIGINAL_DOCUMENT)

# A tampered version — even one extra byte changes the SHA-256
TAMPERED_DOCUMENT = b'%PDF-1.4 official transcript content for verification test -- MODIFIED'
TAMPERED_HASH = compute_document_hash(TAMPERED_DOCUMENT)


# ==========================================================================
#  Override throttle rates for testing so we don't get rate-limited in normal tests
# ==========================================================================
UNLIMITED_THROTTLE = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10000/day',
        'user': '10000/day',
        'verification': '10000/minute',
    },
}


@override_settings(REST_FRAMEWORK={**{
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}, **UNLIMITED_THROTTLE})
class VerifyCredentialNegativeTests(APITestCase):
    """
    Negative-case tests: NOT_FOUND, REVOKED, issuer-status warning.
    Run BEFORE the happy path — if these fail first, we catch regressions early.
    """

    def setUp(self):
        self.student = make_student('neg-student@test.local')
        self.institution = make_institution(wallet='0x1111111111111111111111111111111111111111')

        # An ACTIVE credential
        self.active_cred = Credential.objects.create(
            student=self.student,
            institution=self.institution,
            credential_type='Degree',
            title='B.Tech Computer Science',
            issue_date=date(2026, 6, 1),
            document_hash=ORIGINAL_HASH,
            ipfs_cid='QmTestCID000000000000000000000000000000000',
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + 'a' * 64,
        )

        # A REVOKED credential
        self.revoked_cred = Credential.objects.create(
            student=self.student,
            institution=self.institution,
            credential_type='Certificate',
            title='Data Science Diploma',
            issue_date=date(2025, 12, 15),
            document_hash='0x' + 'b' * 64,
            ipfs_cid='QmTestCID111111111111111111111111111111111',
            status=CredentialStatus.REVOKED,
            revocation_reason='Academic misconduct',
            tx_hash='0x' + 'c' * 64,
        )

    # ------------------------------------------------------------------
    # 1. Nonexistent credential_id → NOT_FOUND (not a 500 error)
    # ------------------------------------------------------------------
    def test_nonexistent_credential_returns_not_found(self):
        """
        A random UUID that doesn't match any credential should return
        result=NOT_FOUND with HTTP 200, never a 500 server error.
        """
        fake_id = '00000000-0000-0000-0000-000000000000'
        response = self.client.get(f'/api/v1/verify/{fake_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.NOT_FOUND)
        # Must have logged a VerificationRecord
        self.assertTrue(
            VerificationRecord.objects.filter(result=VerificationResult.NOT_FOUND).exists()
        )

    # ------------------------------------------------------------------
    # 2. Revoked credential → REVOKED result
    # ------------------------------------------------------------------
    @patch('apps.verification.views.BlockchainService.verify_credential')
    def test_revoked_credential_returns_revoked(self, mock_verify):
        """
        A credential with status=REVOKED (and on-chain revoked=true) should
        return result=REVOKED.
        """
        mock_verify.return_value = {
            'exists': True,
            'revoked': True,
            'issuer': '0x1111111111111111111111111111111111111111',
            'document_hash': self.revoked_cred.document_hash,
            'issued_on': 1700000000,
        }
        response = self.client.get(f'/api/v1/verify/{self.revoked_cred.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.REVOKED)
        self.assertEqual(response.data['title'], 'Data Science Diploma')
        # Must have logged a VerificationRecord
        self.assertTrue(
            VerificationRecord.objects.filter(
                credential=self.revoked_cred,
                result=VerificationResult.REVOKED,
            ).exists()
        )

    # ------------------------------------------------------------------
    # 3. Issuer status warning (institution no longer approved)
    # ------------------------------------------------------------------
    @patch('apps.verification.views.BlockchainService.verify_credential')
    def test_valid_credential_from_dewhitelisted_issuer_shows_warning(self, mock_verify):
        """
        Per Open Question #1: if the issuing institution is no longer approved,
        the credential should still show result=VALID but include an
        issuer_status_warning field.
        """
        # De-whitelist the institution
        self.institution.status = InstitutionStatus.REJECTED
        self.institution.save()

        mock_verify.return_value = {
            'exists': True,
            'revoked': False,
            'issuer': '0x1111111111111111111111111111111111111111',
            'document_hash': ORIGINAL_HASH,
            'issued_on': 1700000000,
        }
        response = self.client.get(f'/api/v1/verify/{self.active_cred.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.VALID)
        self.assertIn('issuer_status_warning', response.data)
        self.assertIn('no longer', response.data['issuer_status_warning'])

    # ------------------------------------------------------------------
    # 4. On-chain exists=false → NOT_FOUND
    # ------------------------------------------------------------------
    @patch('apps.verification.views.BlockchainService.verify_credential')
    def test_credential_not_on_chain_returns_not_found(self, mock_verify):
        """
        If the DB has a row but the chain says it doesn't exist
        (e.g., a PENDING credential whose on-chain tx never confirmed),
        result should be NOT_FOUND.
        """
        mock_verify.return_value = {
            'exists': False,
            'revoked': False,
            'issuer': '0x0000000000000000000000000000000000000000',
            'document_hash': '0x' + '0' * 64,
            'issued_on': 0,
        }
        response = self.client.get(f'/api/v1/verify/{self.active_cred.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.NOT_FOUND)


@override_settings(REST_FRAMEWORK={**{
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}, **UNLIMITED_THROTTLE})
class VerifyUploadTests(APITestCase):
    """
    Tests for POST /api/v1/verify/upload/ — document hash comparison.
    """

    def setUp(self):
        self.student = make_student('upload-student@test.local')
        self.institution = make_institution(wallet='0x2222222222222222222222222222222222222222')

        self.credential = Credential.objects.create(
            student=self.student,
            institution=self.institution,
            credential_type='Degree',
            title='M.Sc. Artificial Intelligence',
            issue_date=date(2026, 7, 1),
            document_hash=ORIGINAL_HASH,
            ipfs_cid='QmTestCIDUpload0000000000000000000000000',
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + 'd' * 64,
        )

    # ------------------------------------------------------------------
    # 3. Tampered document → INVALID, hash_match=false
    # ------------------------------------------------------------------
    def test_tampered_document_returns_invalid(self):
        """
        Uploading a modified document (different bytes) should return
        result=INVALID and hash_match=false — this is tamper detection.
        """
        tampered_file = SimpleUploadedFile(
            'tampered_transcript.pdf',
            TAMPERED_DOCUMENT,
            content_type='application/pdf',
        )
        response = self.client.post(
            '/api/v1/verify/upload/',
            {'credential_id': str(self.credential.id), 'document': tampered_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.INVALID)
        self.assertFalse(response.data['hash_match'])
        # Must have logged
        self.assertTrue(
            VerificationRecord.objects.filter(
                credential=self.credential,
                result=VerificationResult.INVALID,
            ).exists()
        )

    def test_valid_document_returns_valid(self):
        """
        Uploading the original, untampered document should return
        result=VALID and hash_match=true.
        """
        original_file = SimpleUploadedFile(
            'original_transcript.pdf',
            ORIGINAL_DOCUMENT,
            content_type='application/pdf',
        )
        response = self.client.post(
            '/api/v1/verify/upload/',
            {'credential_id': str(self.credential.id), 'document': original_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.VALID)
        self.assertTrue(response.data['hash_match'])

    def test_upload_nonexistent_credential_returns_not_found(self):
        """
        Upload against a nonexistent credential_id should return NOT_FOUND.
        """
        fake_id = '00000000-0000-0000-0000-000000000000'
        some_file = SimpleUploadedFile('some.pdf', b'whatever', content_type='application/pdf')
        response = self.client.post(
            '/api/v1/verify/upload/',
            {'credential_id': fake_id, 'document': some_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.NOT_FOUND)

    def test_upload_missing_credential_id_returns_400(self):
        some_file = SimpleUploadedFile('some.pdf', b'whatever', content_type='application/pdf')
        response = self.client.post(
            '/api/v1/verify/upload/',
            {'document': some_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_missing_file_returns_400(self):
        response = self.client.post(
            '/api/v1/verify/upload/',
            {'credential_id': str(self.credential.id)},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(REST_FRAMEWORK={**{
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}, **UNLIMITED_THROTTLE})
class VerifyHappyPathTests(APITestCase):
    """
    Happy path: verify an ACTIVE credential → result=VALID.
    """

    def setUp(self):
        self.student = make_student('happy-student@test.local')
        self.institution = make_institution(wallet='0x3333333333333333333333333333333333333333')
        self.credential = Credential.objects.create(
            student=self.student,
            institution=self.institution,
            credential_type='Degree',
            title='Bachelor of Engineering',
            issue_date=date(2026, 5, 15),
            document_hash='0x' + 'e' * 64,
            ipfs_cid='QmTestCIDHappy00000000000000000000000000',
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + 'f' * 64,
        )

    @patch('apps.verification.views.BlockchainService.verify_credential')
    def test_active_credential_returns_valid(self, mock_verify):
        """
        An ACTIVE credential with a confirmed on-chain record should
        return result=VALID with all non-PII metadata fields populated.
        """
        mock_verify.return_value = {
            'exists': True,
            'revoked': False,
            'issuer': '0x3333333333333333333333333333333333333333',
            'document_hash': self.credential.document_hash,
            'issued_on': 1700000000,
        }
        response = self.client.get(f'/api/v1/verify/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['result'], VerificationResult.VALID)
        # Non-PII fields are present
        self.assertEqual(response.data['credential_type'], 'Degree')
        self.assertEqual(response.data['title'], 'Bachelor of Engineering')
        self.assertEqual(response.data['institution_name'], 'Verification University')
        self.assertEqual(response.data['issuer_trust_tier'], 1)
        # No issuer_status_warning for an approved institution
        self.assertIsNone(response.data.get('issuer_status_warning'))
        # VerificationRecord logged
        self.assertEqual(
            VerificationRecord.objects.filter(
                credential=self.credential,
                result=VerificationResult.VALID,
            ).count(),
            1,
        )

    @patch('apps.verification.views.BlockchainService.verify_credential')
    def test_blockchain_unreachable_still_returns_result(self, mock_verify):
        """
        If the blockchain node is unreachable, verification should degrade
        gracefully rather than returning a 502.
        """
        from apps.blockchain.exceptions import BlockchainError
        mock_verify.side_effect = BlockchainError("Unable to connect to blockchain node")
        response = self.client.get(f'/api/v1/verify/{self.credential.id}/')
        # Should still return a result (VALID or best-effort) rather than 502
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(REST_FRAMEWORK={**{
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}, **UNLIMITED_THROTTLE})
class VerificationHistoryTests(APITestCase):
    """
    Tests for GET /api/v1/verify/history/{credential_id}/ — authenticated only.
    """

    def setUp(self):
        self.student_user = User.objects.create_user(
            email='hist-student@test.local', password='Password123!', role=UserRole.STUDENT,
        )
        self.student = StudentProfile.objects.create(user=self.student_user, full_name='History Student')

        self.issuer_user = User.objects.create_user(
            email='hist-issuer@test.local', password='Password123!', role=UserRole.ISSUER,
        )
        self.admin_user = User.objects.create_superuser(
            email='hist-admin@test.local', password='Password123!',
        )
        self.other_student_user = User.objects.create_user(
            email='other-student@test.local', password='Password123!', role=UserRole.STUDENT,
        )
        self.other_student = StudentProfile.objects.create(
            user=self.other_student_user, full_name='Other Student',
        )

        self.institution = make_institution(wallet='0x4444444444444444444444444444444444444444')
        IssuerProfile.objects.create(
            user=self.issuer_user,
            institution=self.institution,
            is_primary_contact=True,
        )

        self.credential = Credential.objects.create(
            student=self.student,
            institution=self.institution,
            credential_type='Degree',
            title='History Test Degree',
            issue_date=date(2026, 1, 1),
            document_hash='0x' + '1' * 64,
            ipfs_cid='QmTestCIDHistory000000000000000000000000',
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + '2' * 64,
        )

        # Create some verification records
        for result in [VerificationResult.VALID, VerificationResult.VALID, VerificationResult.NOT_FOUND]:
            VerificationRecord.objects.create(
                credential=self.credential,
                result=result,
                ip_address='127.0.0.1',
            )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(f'/api/v1/verify/history/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owning_student_can_view_history(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.student_user))
        response = self.client.get(f'/api/v1/verify/history/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_issuing_institution_issuer_can_view_history(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))
        response = self.client.get(f'/api/v1/verify/history/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_admin_can_view_history(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin_user))
        response = self.client.get(f'/api/v1/verify/history/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_other_student_gets_empty_history(self):
        """A student who does not own this credential should get an empty list."""
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.other_student_user))
        response = self.client.get(f'/api/v1/verify/history/{self.credential.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_nonexistent_credential_returns_empty(self):
        fake_id = '00000000-0000-0000-0000-000000000000'
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin_user))
        response = self.client.get(f'/api/v1/verify/history/{fake_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


class VerificationRateLimitTests(APITestCase):
    """
    Test that rate limiting actually triggers after the configured threshold.
    We patch the throttle rate directly because override_settings doesn't
    always propagate to DRF's cached api_settings during test execution.
    """

    def test_rate_limiting_triggers_after_threshold(self):
        """
        With a limit of 3/minute, the 4th request should return HTTP 429.
        This proves the VerificationRateThrottle is actually applied.
        """
        from django.core.cache import cache
        from apps.verification.throttling import VerificationRateThrottle

        # Clear any cached throttle state from previous tests
        cache.clear()

        # Directly set the rate on the throttle class so DRF picks it up
        original_rate = getattr(VerificationRateThrottle, 'rate', None)
        VerificationRateThrottle.rate = '3/minute'
        VerificationRateThrottle.num_requests = 3
        VerificationRateThrottle.duration = 60

        try:
            fake_id = '00000000-0000-0000-0000-000000000000'
            url = f'/api/v1/verify/{fake_id}/'

            # First 3 should succeed
            for i in range(3):
                response = self.client.get(url)
                self.assertIn(
                    response.status_code,
                    [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS],
                    f"Request {i+1} unexpected status: {response.status_code}",
                )

            # 4th should be rate-limited
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        finally:
            # Restore original rate
            if original_rate is not None:
                VerificationRateThrottle.rate = original_rate
            else:
                # Remove the directly-set rate so it falls back to settings
                if hasattr(VerificationRateThrottle, 'rate'):
                    del VerificationRateThrottle.rate
            # Clean up parsed values
            for attr in ('num_requests', 'duration'):
                if hasattr(VerificationRateThrottle, attr):
                    delattr(VerificationRateThrottle, attr)
            cache.clear()


class VerificationRecordModelTests(TestCase):
    """Basic model tests for VerificationRecord."""

    def test_create_verification_record(self):
        record = VerificationRecord.objects.create(
            result=VerificationResult.VALID,
            ip_address='192.168.1.1',
        )
        self.assertIsNotNone(record.id)
        self.assertEqual(record.result, VerificationResult.VALID)
        self.assertIsNotNone(record.verified_at)
        self.assertIn('VALID', str(record))

    def test_not_found_record_with_no_credential(self):
        record = VerificationRecord.objects.create(
            credential=None,
            result=VerificationResult.NOT_FOUND,
        )
        self.assertIsNone(record.credential)
        self.assertEqual(record.result, VerificationResult.NOT_FOUND)
