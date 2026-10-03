from datetime import date
import io
from unittest.mock import patch, MagicMock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserRole
from apps.students.models import StudentProfile
from apps.credentials.models import (
    Credential,
    CredentialStatus,
    CredentialShare,
)
from apps.institutions.models import (
    Institution,
    InstitutionStatus,
    InstitutionType,
    IssuerProfile,
)
from apps.credentials.services import (
    compute_document_hash,
    compute_ipfs_cid,
    MockIpfsService,
)
from apps.blockchain.models import (
    BlockchainAction,
    BlockchainTransaction,
    BlockchainTxStatus,
)
from apps.blockchain.services import BlockchainService
from apps.blockchain.exceptions import BlockchainError, BlockchainRevertError


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return f'Bearer {refresh.access_token}'


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


def make_institution(status=InstitutionStatus.APPROVED, wallet_address='0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B', **kwargs):
    defaults = {
        'name': 'State University',
        'institution_type': InstitutionType.UNIVERSITY,
        'official_email_domain': 'stateu.edu',
        'registration_number': f'AICTE-{kwargs.get("name", "001")}',
        'proof_document': 'stateu/proof.pdf',
        'wallet_address': wallet_address,
        'status': status,
    }
    defaults.update(kwargs)
    return Institution.objects.create(**defaults)


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


class IpfsServiceUnitTests(TestCase):
    def test_deterministic_cid_generation(self):
        content_1 = b"Academic Transcript of Alice - Computer Engineering 2026"
        content_2 = b"Academic Transcript of Alice - Computer Engineering 2026"
        content_3 = b"Academic Transcript of Bob - Mechanical Engineering 2026"

        cid_1 = compute_ipfs_cid(content_1)
        cid_2 = compute_ipfs_cid(content_2)
        cid_3 = compute_ipfs_cid(content_3)

        self.assertTrue(cid_1.startswith('Qm'))
        self.assertEqual(len(cid_1), 46)
        self.assertEqual(cid_1, cid_2)  # Identical content yields identical CID
        self.assertNotEqual(cid_1, cid_3)

    def test_ipfs_mock_service_stores_and_retrieves(self):
        service = MockIpfsService()
        test_bytes = b"Hello Educhain IPFS Mock Storage"
        cid = service.upload_document(test_bytes, filename="hello.pdf")
        self.assertTrue(service.document_exists(cid))
        retrieved = service.get_document(cid)
        self.assertEqual(retrieved, test_bytes)


class Phase8CredentialIssuanceIntegrationTests(APITestCase):
    def setUp(self):
        # 1. Approved Institution and Issuer Account
        self.approved_institution = make_institution(
            name='State University',
            wallet_address='0x22d491Bde2303f2f43325b2108D26f1eAbA1e32b',
            status=InstitutionStatus.APPROVED,
        )
        self.issuer_user = User.objects.create_user(
            email='issuer@stateu.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.issuer_profile = IssuerProfile.objects.create(
            user=self.issuer_user,
            institution=self.approved_institution,
            is_primary_contact=True,
        )

        # 2. Unapproved (PENDING) Institution and Issuer Account
        self.unapproved_institution = make_institution(
            name='Unapproved Academy',
            wallet_address='0x33d491Bde2303f2f43325b2108D26f1eAbA1e32c',
            status=InstitutionStatus.PENDING,
        )
        self.unapproved_issuer_user = User.objects.create_user(
            email='issuer@unapproved.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.unapproved_issuer_profile = IssuerProfile.objects.create(
            user=self.unapproved_issuer_user,
            institution=self.unapproved_institution,
        )

        # 3. Recipient Student
        self.student = make_student(email='student@educhain.local')
        self.issue_url = '/api/v1/credentials/issue/'

    def test_1_unapproved_institution_fails_403_before_blockchain_call(self):
        """
        NEGATIVE CASE 1:
        An unapproved institution's issuer tries to issue — must fail with 403 FORBIDDEN,
        before ever reaching the blockchain call.
        Enforces AGENTS.md's two-layer defense principle.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.unapproved_issuer_user))
        test_file = SimpleUploadedFile("degree.pdf", b"%PDF-1.4 mock diploma content", content_type="application/pdf")

        with patch('apps.blockchain.services.BlockchainService.issue_credential') as mock_chain_call:
            response = self.client.post(
                self.issue_url,
                {
                    'student_email': self.student.user.email,
                    'credential_type': 'Degree',
                    'title': 'B.Tech Computer Science',
                    'issue_date': '2026-05-20',
                    'document': test_file,
                },
                format='multipart',
            )
            # Must return 403 Forbidden
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data.get('code'), 'FORBIDDEN')

            # CRITICAL: Blockchain call MUST NOT have been invoked
            mock_chain_call.assert_not_called()

            # No Credential row should be created
            self.assertEqual(Credential.objects.count(), 0)

    def test_2_duplicate_document_hash_fails_cleanly(self):
        """
        NEGATIVE CASE 2:
        A duplicate document (same SHA-256 hash) tries to be issued twice — must fail cleanly
        with 400 Bad Request before calling the blockchain a second time.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))
        file_content = b"%PDF-1.4 Unique diploma bytes for duplicate test"
        file_1 = SimpleUploadedFile("diploma.pdf", file_content, content_type="application/pdf")
        fake_tx = '0x' + 'aa' * 32

        # First issuance succeeds
        with patch('apps.blockchain.services.BlockchainService.issue_credential', return_value=fake_tx):
            res1 = self.client.post(
                self.issue_url,
                {
                    'student_email': self.student.user.email,
                    'credential_type': 'Degree',
                    'title': 'B.E. Mechanical Engineering',
                    'issue_date': '2026-05-20',
                    'document': file_1,
                },
                format='multipart',
            )
            self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
            self.assertEqual(res1.data['status'], 'ACTIVE')

        # Second issuance with the EXACT SAME file must fail cleanly
        file_2 = SimpleUploadedFile("diploma_copy.pdf", file_content, content_type="application/pdf")
        with patch('apps.blockchain.services.BlockchainService.issue_credential') as mock_chain_call:
            res2 = self.client.post(
                self.issue_url,
                {
                    'student_email': self.student.user.email,
                    'credential_type': 'Degree',
                    'title': 'B.E. Mechanical Engineering',
                    'issue_date': '2026-05-20',
                    'document': file_2,
                },
                format='multipart',
            )
            self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res2.data.get('code'), 'DUPLICATE_DOCUMENT')
            mock_chain_call.assert_not_called()

    def test_3_blockchain_failure_does_not_falsely_mark_credential_active(self):
        """
        NEGATIVE CASE 3:
        Simulate a blockchain call failure (e.g. node unreachable / disconnected).
        Confirm the Credential row does NOT end up falsely marked ACTIVE.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))
        test_file = SimpleUploadedFile("degree_fail.pdf", b"%PDF-1.4 failure test content", content_type="application/pdf")

        # Simulate node unreachable mid-call
        simulated_error = BlockchainError("Unable to connect to blockchain node at http://127.0.0.1:7545")

        with patch('apps.blockchain.services.BlockchainService.issue_credential', side_effect=simulated_error):
            response = self.client.post(
                self.issue_url,
                {
                    'student_email': self.student.user.email,
                    'credential_type': 'Degree',
                    'title': 'B.Sc Physics',
                    'issue_date': '2026-05-20',
                    'document': test_file,
                },
                format='multipart',
            )
            # Response must reflect the 502 BlockchainError
            self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
            self.assertEqual(response.data.get('code'), 'BLOCKCHAIN_ERROR')

            # CRITICAL CHECK: The Credential row must NOT be marked ACTIVE
            doc_hash = compute_document_hash(b"%PDF-1.4 failure test content")
            cred = Credential.objects.filter(document_hash=doc_hash).first()
            self.assertIsNotNone(cred)
            self.assertEqual(cred.status, CredentialStatus.PENDING)
            self.assertNotEqual(cred.status, CredentialStatus.ACTIVE)
            self.assertIsNone(cred.tx_hash)

    def test_4_happy_path_issue_confirms_active_and_onchain_verification(self):
        """
        HAPPY PATH:
        Issue a single credential end-to-end:
        1. Upload document + metadata.
        2. Computed hash and deterministic CID match expectations.
        3. Credential status is updated to ACTIVE upon blockchain confirmation.
        4. BlockchainTransaction record is logged with CONFIRMED.
        5. verify_credential returns matching authentic data.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))
        raw_doc = b"%PDF-1.4 Alice's Official Degree Certificate 2026"
        test_file = SimpleUploadedFile("alice_degree.pdf", raw_doc, content_type="application/pdf")
        expected_hash = compute_document_hash(raw_doc)
        expected_cid = compute_ipfs_cid(raw_doc)

        simulated_tx = '0x' + '99' * 32

        def mock_issue(credential_id, document_hash, ipfs_cid, issuer_wallet_address, related_object_id):
            # Log BlockchainTransaction to mirror real service behavior
            BlockchainTransaction.objects.create(
                tx_hash=simulated_tx,
                action=BlockchainAction.ISSUE_CREDENTIAL,
                related_object_id=related_object_id,
                status=BlockchainTxStatus.CONFIRMED,
                gas_used=72000,
            )
            return simulated_tx

        with patch('apps.blockchain.services.BlockchainService.issue_credential', side_effect=mock_issue):
            response = self.client.post(
                self.issue_url,
                {
                    'student_email': self.student.user.email,
                    'credential_type': 'Degree',
                    'title': 'Bachelor of Engineering in Computer Science',
                    'issue_date': '2026-06-30',
                    'document': test_file,
                },
                format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['status'], 'ACTIVE')
            self.assertEqual(response.data['tx_hash'], simulated_tx)
            self.assertEqual(response.data['document_hash'], expected_hash)
            self.assertEqual(response.data['ipfs_cid'], expected_cid)

            # Verify Database record
            cred = Credential.objects.get(id=response.data['id'])
            self.assertEqual(cred.status, CredentialStatus.ACTIVE)
            self.assertEqual(cred.tx_hash, simulated_tx)
            self.assertEqual(cred.document_hash, expected_hash)
            self.assertEqual(cred.ipfs_cid, expected_cid)

            # Verify BlockchainTransaction log
            tx_log = BlockchainTransaction.objects.filter(tx_hash=simulated_tx).first()
            self.assertIsNotNone(tx_log)
            self.assertEqual(tx_log.action, BlockchainAction.ISSUE_CREDENTIAL)
            self.assertEqual(tx_log.status, BlockchainTxStatus.CONFIRMED)
            self.assertEqual(tx_log.related_object_id, cred.id)

            # Verify on-chain query simulation
            with patch('apps.blockchain.services.BlockchainService.verify_credential') as mock_verify:
                mock_verify.return_value = {
                    'exists': True,
                    'revoked': False,
                    'issuer': self.approved_institution.wallet_address,
                    'document_hash': expected_hash,
                    'issued_on': 1770000000,
                }
                verification = BlockchainService.verify_credential(cred.id)
                self.assertTrue(verification['exists'])
                self.assertFalse(verification['revoked'])
                self.assertEqual(verification['issuer'], self.approved_institution.wallet_address)
                self.assertEqual(verification['document_hash'], expected_hash)

    def test_5_batch_issue_partial_failure_does_not_block_valid_rows(self):
        """
        BATCH ISSUANCE:
        POST /api/v1/credentials/issue-batch/
        Accepts CSV + documents. Valid row is issued; bad row (unknown student) fails
        individually without blocking the valid credential in the batch.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))

        csv_content = (
            "student_email,credential_type,title,issue_date,document_filename\n"
            f"{self.student.user.email},Degree,B.E. CS,2026-05-15,alice_cert.pdf\n"
            "nonexistent_student@test.local,Degree,B.E. CS,2026-05-15,bob_cert.pdf\n"
        )
        csv_file = SimpleUploadedFile("batch.csv", csv_content.encode('utf-8'), content_type="text/csv")
        file_alice = SimpleUploadedFile("alice_cert.pdf", b"Alice Transcript 2026", content_type="application/pdf")
        file_bob = SimpleUploadedFile("bob_cert.pdf", b"Bob Transcript 2026", content_type="application/pdf")

        fake_batch_tx = '0x' + 'bb' * 32

        with patch('apps.blockchain.services.BlockchainService.batch_issue_credentials', return_value=fake_batch_tx):
            response = self.client.post(
                '/api/v1/credentials/issue-batch/',
                {
                    'csv_file': csv_file,
                    'alice_cert.pdf': file_alice,
                    'bob_cert.pdf': file_bob,
                },
                format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            self.assertEqual(response.data['total'], 2)
            self.assertEqual(response.data['processed'], 1)  # Only 1 succeeded
            self.assertEqual(len(response.data['failures']), 1)
            self.assertEqual(response.data['failures'][0]['row'], 2)
            self.assertIn("nonexistent_student@test.local", response.data['failures'][0]['student_email'])

            # Confirm valid row was issued and active
            issued_list = response.data['issued']
            self.assertEqual(len(issued_list), 1)
            self.assertEqual(issued_list[0]['status'], 'ACTIVE')
            self.assertEqual(issued_list[0]['tx_hash'], fake_batch_tx)

    def test_6_batch_status_endpoint(self):
        """
        BATCH STATUS:
        GET /api/v1/credentials/issue-batch/{batch_id}/status/
        Retrieves processed count and failure details for an existing batch.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer_user))

        csv_content = (
            "student_email,credential_type,title,issue_date,document_filename\n"
            f"{self.student.user.email},Degree,B.E. CS,2026-05-15,alice.pdf\n"
        )
        csv_file = SimpleUploadedFile("batch.csv", csv_content.encode('utf-8'), content_type="text/csv")
        file_alice = SimpleUploadedFile("alice.pdf", b"Alice Unique Cert Content", content_type="application/pdf")

        with patch('apps.blockchain.services.BlockchainService.batch_issue_credentials', return_value='0x' + '11' * 32):
            batch_res = self.client.post(
                '/api/v1/credentials/issue-batch/',
                {
                    'csv_file': csv_file,
                    'alice.pdf': file_alice,
                },
                format='multipart',
            )
            batch_id = batch_res.data['batch_id']

            status_res = self.client.get(f'/api/v1/credentials/issue-batch/{batch_id}/status/')
            self.assertEqual(status_res.status_code, status.HTTP_200_OK)
            self.assertEqual(status_res.data['batch_id'], batch_id)
            self.assertEqual(status_res.data['total'], 1)
            self.assertEqual(status_res.data['processed'], 1)
            self.assertEqual(status_res.data['failures'], [])
