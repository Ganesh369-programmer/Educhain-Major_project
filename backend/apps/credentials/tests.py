from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User, UserRole
from apps.credentials.models import (
    Credential,
    CredentialStatus,
    CredentialShare,
    StudentProfile,
)
from apps.institutions.models import (
    Institution,
    InstitutionStatus,
    InstitutionType,
)


def make_student(email='alice@student.educhain.local'):
    user = User.objects.create_user(
        email=email,
        password='Password123!',
        role=UserRole.STUDENT,
    )
    return StudentProfile.objects.create(
        user=user,
        full_name='Alice Student',
    )


def make_institution():
    return Institution.objects.create(
        name='State University',
        institution_type=InstitutionType.UNIVERSITY,
        official_email_domain='stateu.edu',
        registration_number='AICTE-EXAMPLE-001',
        proof_document='stateu/proof.pdf',
        wallet_address='0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
        status=InstitutionStatus.APPROVED,
    )


def make_credential(student, institution, **overrides):
    defaults = {
        'credential_type': 'Degree',
        'title': 'B.E. Computer Engineering',
        'issue_date': date(2026, 5, 15),
        'document_hash': '0x' + 'a' * 64,
        'ipfs_cid': 'QmExampleCIDForTestDocument0000000000000',
    }
    defaults.update(overrides)
    return Credential.objects.create(
        student=student,
        institution=institution,
        **defaults,
    )


class CredentialDefaultStatusTests(TestCase):
    def test_new_credential_defaults_to_pending(self):
        student = make_student()
        institution = make_institution()
        credential = make_credential(student, institution)
        self.assertEqual(credential.status, CredentialStatus.PENDING)

    def test_status_explicit_active_saves_correctly(self):
        student = make_student()
        institution = make_institution()
        credential = make_credential(
            student,
            institution,
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + '1' * 64,
        )
        credential.refresh_from_db()
        self.assertEqual(credential.status, CredentialStatus.ACTIVE)
        self.assertIsNotNone(credential.tx_hash)

    def test_status_explicit_revoked_saves_correctly(self):
        student = make_student()
        institution = make_institution()
        credential = make_credential(
            student,
            institution,
            status=CredentialStatus.REVOKED,
            revocation_reason='Credential found to be fraudulent.',
        )
        credential.refresh_from_db()
        self.assertEqual(credential.status, CredentialStatus.REVOKED)
        self.assertIsNotNone(credential.revocation_reason)


class CredentialDocumentHashUniquenessTests(TestCase):
    def test_duplicate_document_hash_rejected_at_db_level(self):
        student_a = make_student('a@student.educhain.local')
        student_b = make_student('b@student.educhain.local')
        institution = make_institution()
        shared_hash = '0x' + 'ff' * 32
        make_credential(student_a, institution, document_hash=shared_hash)
        with self.assertRaises(IntegrityError):
            Credential.objects.create(
                student=student_b,
                institution=institution,
                credential_type='Certificate',
                title='Another Credential',
                issue_date=date(2026, 6, 1),
                document_hash=shared_hash,
                ipfs_cid='QmDifferentCIDButSameHash',
            )

    def test_distinct_document_hashes_are_allowed(self):
        student = make_student()
        institution = make_institution()
        cred1 = make_credential(
            student,
            institution,
            document_hash='0x' + '01' * 32,
            title='Credential One',
        )
        cred2 = make_credential(
            student,
            institution,
            document_hash='0x' + '02' * 32,
            title='Credential Two',
        )
        self.assertNotEqual(cred1.document_hash, cred2.document_hash)
        self.assertEqual(Credential.objects.filter(student=student).count(), 2)


class CredentialStatusValidValuesTests(TestCase):
    def test_invalid_status_string_rejected_by_validation(self):
        student = make_student()
        institution = make_institution()
        credential = make_credential(student, institution)
        credential.status = 'NOT_A_REAL_STATUS'
        with self.assertRaises(ValidationError):
            credential.full_clean()

    def test_all_three_valid_statuses_accepted(self):
        student = make_student()
        institution = make_institution()
        for valid_status in (CredentialStatus.PENDING, CredentialStatus.ACTIVE, CredentialStatus.REVOKED):
            credential = make_credential(
                student,
                institution,
                document_hash='0x' + valid_status.lower().ljust(64, '0')[:64],
                status=valid_status,
            )
            credential.full_clean()
            credential.refresh_from_db()
            self.assertEqual(credential.status, valid_status)

    def test_status_text_choices_have_exactly_three_values(self):
        self.assertEqual(
            set(CredentialStatus.values),
            {'PENDING', 'ACTIVE', 'REVOKED'},
        )


class CredentialShareBasicTests(TestCase):
    def test_share_links_to_credential_and_preserves_visible_fields(self):
        student = make_student()
        institution = make_institution()
        credential = make_credential(student, institution)
        share = CredentialShare.objects.create(
            credential=credential,
            share_token='share-token-abc-123-unique',
            visible_fields=['title', 'issue_date', 'institution'],
        )
        share.refresh_from_db()
        self.assertEqual(share.credential_id, credential.id)
        self.assertEqual(len(share.visible_fields), 3)
        self.assertIn('title', share.visible_fields)

    def test_duplicate_share_token_rejected(self):
        student = make_student()
        institution = make_institution()
        cred1 = make_credential(
            student,
            institution,
            document_hash='0x' + 'cc' * 32,
        )
        cred2 = make_credential(
            student,
            institution,
            document_hash='0x' + 'dd' * 32,
        )
        shared_token = 'same-token-twice'
        CredentialShare.objects.create(
            credential=cred1,
            share_token=shared_token,
            visible_fields=[],
        )
        with self.assertRaises(IntegrityError):
            CredentialShare.objects.create(
                credential=cred2,
                share_token=shared_token,
                visible_fields=['title'],
            )


class CredentialSerializerValidationTests(TestCase):
    def test_create_serializer_rejects_duplicate_document_hash(self):
        from apps.credentials.serializers import CredentialCreateSerializer

        student = make_student()
        institution = make_institution()
        dup_hash = '0x' + '77' * 32
        make_credential(student, institution, document_hash=dup_hash)

        serializer = CredentialCreateSerializer(
            data={
                'student': str(student.id),
                'institution': str(institution.id),
                'credential_type': 'Degree',
                'title': 'Duplicate Attempt',
                'issue_date': '2026-05-15',
                'document_hash': dup_hash,
                'ipfs_cid': 'QmDupAttempt0000000000000000000000',
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('document_hash', serializer.errors)

    def test_create_serializer_rejects_bad_document_hash_format(self):
        from apps.credentials.serializers import CredentialCreateSerializer

        student = make_student()
        institution = make_institution()

        serializer = CredentialCreateSerializer(
            data={
                'student': str(student.id),
                'institution': str(institution.id),
                'credential_type': 'Degree',
                'title': 'Bad Hash Attempt',
                'issue_date': '2026-05-15',
                'document_hash': 'not-a-valid-hash',
                'ipfs_cid': 'QmBadHash0000000000000000000000000',
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('document_hash', serializer.errors)

    def test_detail_serializer_returns_read_only_fields(self):
        from apps.credentials.serializers import CredentialSerializer

        student = make_student()
        institution = make_institution()
        credential = make_credential(
            student,
            institution,
            status=CredentialStatus.ACTIVE,
            tx_hash='0x' + 'ee' * 32,
        )
        data = CredentialSerializer(credential).data
        self.assertEqual(data['status'], CredentialStatus.ACTIVE)
        self.assertEqual(data['title'], 'B.E. Computer Engineering')
        self.assertIn('document_hash', data)
        self.assertIn('created_at', data)
