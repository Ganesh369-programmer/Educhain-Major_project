import os
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserRole
from apps.institutions.models import (
    Institution,
    InstitutionStatus,
    InstitutionType,
    IssuerProfile,
)


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return f'Bearer {refresh.access_token}'


def make_proof_file(name='proof.pdf'):
    return SimpleUploadedFile(
        name,
        b'%PDF-1.4 fake proof document content',
        content_type='application/pdf',
    )


class InstitutionRegistrationTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('institution_register')
        self.issuer = User.objects.create_user(
            email='issuer@stateu.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.student = User.objects.create_user(
            email='student@educhain.local',
            password='Password123!',
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_superuser(
            email='admin@educhain.local',
            password='Password123!',
        )
        self.valid_payload = {
            'name': 'State University',
            'institution_type': InstitutionType.UNIVERSITY,
            'official_website': 'https://stateu.edu',
            'official_email_domain': 'stateu.edu',
            'registration_number': 'AICTE-12345',
            'gst_number': '27AABCU9603R1ZM',
            'wallet_address': '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
        }

    def test_unauthenticated_rejected(self):
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'UNAUTHENTICATED')

    def test_student_role_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.student))
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'FORBIDDEN')

    def test_admin_role_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_issuer_registration_success(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], InstitutionStatus.PENDING)
        self.assertIn('id', response.data)

        institution = Institution.objects.get(pk=response.data['id'])
        self.assertEqual(institution.name, 'State University')
        self.assertEqual(institution.status, InstitutionStatus.PENDING)
        self.assertIsNone(institution.trust_tier)
        self.assertIsNone(institution.reviewed_by)
        self.assertIsNone(institution.reviewed_at)

        profile = IssuerProfile.objects.get(user=self.issuer)
        self.assertEqual(profile.institution_id, institution.id)
        self.assertTrue(profile.is_primary_contact)

    def test_issuer_cannot_register_twice(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        second_payload = {
            **self.valid_payload,
            'name': 'Another Institute',
            'registration_number': 'AICTE-99999',
            'wallet_address': '0x4B20993Bc481177ec7E8f571ceCaE8A9e22C02db',
        }
        response = self.client.post(
            self.register_url,
            {**second_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')
        self.assertEqual(
            IssuerProfile.objects.filter(user=self.issuer).count(),
            1,
        )

    def test_duplicate_wallet_address_rejected(self):
        Institution.objects.create(
            name='Existing Institute',
            institution_type=InstitutionType.COMPANY,
            official_email_domain='existing.com',
            registration_number='REG-EXIST-001',
            proof_document='existing/proof.pdf',
            wallet_address=self.valid_payload['wallet_address'],
        )
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_duplicate_registration_number_rejected(self):
        Institution.objects.create(
            name='Existing Institute 2',
            institution_type=InstitutionType.NGO,
            official_email_domain='existing2.com',
            registration_number=self.valid_payload['registration_number'],
            proof_document='existing2/proof.pdf',
            wallet_address='0x78731D3Ca6b7E34aC0F824c42a7cC18A495cabaB',
        )
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        response = self.client.post(
            self.register_url,
            {**self.valid_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_invalid_wallet_address_format_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        bad_payload = {**self.valid_payload, 'wallet_address': 'not-an-address'}
        response = self.client.post(
            self.register_url,
            {**bad_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_non_checksummed_wallet_also_invalid(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        bad_payload = {
            **self.valid_payload,
            'wallet_address': '0xab5801a7d398351b8be11c439e05c5b3259aec9b',
        }
        response = self.client.post(
            self.register_url,
            {**bad_payload, 'proof_document': make_proof_file()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_missing_proof_document_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        response = self.client.post(
            self.register_url,
            self.valid_payload,
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')


class InstitutionDetailAndListTests(APITestCase):
    def setUp(self):
        self.issuer1 = User.objects.create_user(
            email='issuer1@uni-a.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.issuer2 = User.objects.create_user(
            email='issuer2@uni-b.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.student = User.objects.create_user(
            email='student@educhain.local',
            password='Password123!',
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_superuser(
            email='admin@educhain.local',
            password='Password123!',
        )

        self.inst_a = Institution.objects.create(
            name='University A',
            institution_type=InstitutionType.UNIVERSITY,
            official_email_domain='uni-a.edu',
            registration_number='UNI-A-001',
            proof_document='inst_a/proof.pdf',
            wallet_address='0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
            status=InstitutionStatus.PENDING,
        )
        IssuerProfile.objects.create(
            user=self.issuer1,
            institution=self.inst_a,
            is_primary_contact=True,
        )

        self.inst_b = Institution.objects.create(
            name='University B',
            institution_type=InstitutionType.PRIVATE_TRAINING_INSTITUTE,
            official_email_domain='uni-b.edu',
            registration_number='UNI-B-002',
            proof_document='inst_b/proof.pdf',
            wallet_address='0x4B20993Bc481177ec7E8f571ceCaE8A9e22C02db',
            status=InstitutionStatus.APPROVED,
            trust_tier=1,
            reviewed_by=self.admin,
        )
        IssuerProfile.objects.create(
            user=self.issuer2,
            institution=self.inst_b,
            is_primary_contact=True,
        )

        self.detail_a_url = reverse('institution_detail', kwargs={'id': self.inst_a.id})
        self.detail_b_url = reverse('institution_detail', kwargs={'id': self.inst_b.id})
        self.list_url = reverse('institution_list')

    def test_admin_sees_all_institutions_in_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [str(item['id']) for item in response.data]
        self.assertIn(str(self.inst_a.id), ids)
        self.assertIn(str(self.inst_b.id), ids)
        self.assertEqual(len(response.data), 2)

    def test_admin_can_view_each_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        a = self.client.get(self.detail_a_url)
        b = self.client.get(self.detail_b_url)
        self.assertEqual(a.status_code, status.HTTP_200_OK)
        self.assertEqual(a.data['name'], 'University A')
        self.assertEqual(a.data['status'], InstitutionStatus.PENDING)
        self.assertEqual(b.status_code, status.HTTP_200_OK)
        self.assertEqual(b.data['status'], InstitutionStatus.APPROVED)
        self.assertEqual(b.data['trust_tier'], 1)

    def test_issuer_sees_only_own_institution_in_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer1))
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [str(item['id']) for item in response.data]
        self.assertIn(str(self.inst_a.id), ids)
        self.assertNotIn(str(self.inst_b.id), ids)
        self.assertEqual(len(response.data), 1)

    def test_issuer_can_view_own_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer1))
        response = self.client.get(self.detail_a_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'University A')
        self.assertEqual(response.data['status'], InstitutionStatus.PENDING)
        self.assertIsNone(response.data['trust_tier'])

    def test_issuer_cannot_view_other_institution_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer1))
        response = self.client.get(self.detail_b_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'FORBIDDEN')

    def test_issuer2_sees_only_own(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer2))
        response = self.client.get(self.list_url)
        ids = [str(item['id']) for item in response.data]
        self.assertNotIn(str(self.inst_a.id), ids)
        self.assertIn(str(self.inst_b.id), ids)

    def test_student_cannot_access_list_or_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.student))
        list_resp = self.client.get(self.list_url)
        detail_resp = self.client.get(self.detail_a_url)
        self.assertEqual(list_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_filter_by_status(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        pending_resp = self.client.get(self.list_url, {'status': InstitutionStatus.PENDING})
        approved_resp = self.client.get(self.list_url, {'status': InstitutionStatus.APPROVED})
        self.assertEqual(len(pending_resp.data), 1)
        self.assertEqual(str(pending_resp.data[0]['id']), str(self.inst_a.id))
        self.assertEqual(len(approved_resp.data), 1)
        self.assertEqual(str(approved_resp.data[0]['id']), str(self.inst_b.id))

    def test_nonexistent_institution_404(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        fake_uuid = '00000000-0000-0000-0000-000000000000'
        url = reverse('institution_detail', kwargs={'id': fake_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 'NOT_FOUND')

    def test_pending_status_reflected_in_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.get(self.detail_a_url)
        self.assertEqual(response.data['status'], InstitutionStatus.PENDING)
        self.assertIsNone(response.data['trust_tier'])
        self.assertIsNone(response.data['reviewed_at'])

    def test_approved_status_reflected_in_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer2))
        response = self.client.get(self.detail_b_url)
        self.assertEqual(response.data['status'], InstitutionStatus.APPROVED)
        self.assertEqual(response.data['trust_tier'], 1)
        self.assertEqual(str(response.data['reviewed_by']), str(self.admin.id))


class InstitutionApprovalTests(APITestCase):
    def setUp(self):
        self.issuer = User.objects.create_user(
            email='issuer@college.edu',
            password='Password123!',
            role=UserRole.ISSUER,
        )
        self.student = User.objects.create_user(
            email='student@educhain.local',
            password='Password123!',
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_superuser(
            email='admin@educhain.local',
            password='Password123!',
        )

        self.inst_pending = Institution.objects.create(
            name='Pending College',
            institution_type=InstitutionType.PRIVATE_TRAINING_INSTITUTE,
            official_email_domain='college.edu',
            registration_number='COL-001',
            proof_document='college/proof.pdf',
            wallet_address='0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
            status=InstitutionStatus.PENDING,
        )
        IssuerProfile.objects.create(
            user=self.issuer,
            institution=self.inst_pending,
            is_primary_contact=True,
        )

        self.inst_reviewed = Institution.objects.create(
            name='Already Approved',
            institution_type=InstitutionType.UNIVERSITY,
            official_email_domain='approved.edu',
            registration_number='APR-002',
            proof_document='approved/proof.pdf',
            wallet_address='0x4B20993Bc481177ec7E8f571ceCaE8A9e22C02db',
            status=InstitutionStatus.APPROVED,
            trust_tier=2,
            reviewed_by=self.admin,
        )

        self.approve_url = reverse(
            'institution_approve', kwargs={'id': self.inst_pending.id}
        )
        self.approve_reviewed_url = reverse(
            'institution_approve', kwargs={'id': self.inst_reviewed.id}
        )
        self.reject_url = reverse(
            'institution_reject', kwargs={'id': self.inst_pending.id}
        )
        self.reject_reviewed_url = reverse(
            'institution_reject', kwargs={'id': self.inst_reviewed.id}
        )
        self.detail_url = reverse(
            'institution_detail', kwargs={'id': self.inst_pending.id}
        )

    def test_non_admin_cannot_approve(self):
        for user in (self.issuer, self.student):
            self.client.credentials(HTTP_AUTHORIZATION=auth_header(user))
            response = self.client.post(
                self.approve_url,
                {'trust_tier': 1},
                format='json',
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_403_FORBIDDEN,
                f'User {user.role} should be forbidden from approving',
            )
            self.assertEqual(response.data['code'], 'FORBIDDEN')

    def test_non_admin_cannot_reject(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        response = self.client.post(
            self.reject_url,
            {'reason': 'Documents insufficient'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_success_updates_status_and_trust_tier(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.approve_url,
            {'trust_tier': 1},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], InstitutionStatus.APPROVED)
        self.assertIsNotNone(response.data['tx_hash'])
        self.assertTrue(response.data['tx_hash'].startswith('0x'))

        self.inst_pending.refresh_from_db()
        self.assertEqual(self.inst_pending.status, InstitutionStatus.APPROVED)
        self.assertEqual(self.inst_pending.trust_tier, 1)
        self.assertEqual(self.inst_pending.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(self.inst_pending.reviewed_at)
        self.assertIsNone(self.inst_pending.rejection_reason)

    def test_approve_invalid_trust_tier_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.approve_url,
            {'trust_tier': 99},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_approve_already_reviewed_conflict(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.approve_reviewed_url,
            {'trust_tier': 2},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'CONFLICT')

    def test_reject_success_sets_rejection_reason(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        reason = 'Proof document is not legible and registration number does not match records.'
        response = self.client.post(
            self.reject_url,
            {'reason': reason},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], InstitutionStatus.REJECTED)

        self.inst_pending.refresh_from_db()
        self.assertEqual(self.inst_pending.status, InstitutionStatus.REJECTED)
        self.assertIsNone(self.inst_pending.trust_tier)
        self.assertEqual(self.inst_pending.rejection_reason, reason)
        self.assertEqual(self.inst_pending.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(self.inst_pending.reviewed_at)

    def test_reject_empty_reason_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.reject_url,
            {'reason': ''},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')

    def test_reject_already_reviewed_conflict(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.reject_reviewed_url,
            {'reason': 'No good'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'CONFLICT')

    def test_rejected_institution_shows_reason_in_detail(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        reason = 'Insufficient documentation'
        self.client.post(
            self.reject_url,
            {'reason': reason},
            format='json',
        )
        detail_resp = self.client.get(self.detail_url)
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data['status'], InstitutionStatus.REJECTED)
        self.assertEqual(detail_resp.data['rejection_reason'], reason)
        self.assertIsNone(detail_resp.data['trust_tier'])

    def test_approved_institution_reflected_in_issuer_detail_get(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        self.client.post(
            self.approve_url,
            {'trust_tier': 2},
            format='json',
        )
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.issuer))
        detail_resp = self.client.get(self.detail_url)
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data['status'], InstitutionStatus.APPROVED)
        self.assertEqual(detail_resp.data['trust_tier'], 2)

    def test_nonexistent_institution_approve_404(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        fake_uuid = '00000000-0000-0000-0000-000000000000'
        url = reverse('institution_approve', kwargs={'id': fake_uuid})
        response = self.client.post(url, {'trust_tier': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 'NOT_FOUND')


class CustodialWalletEncryptionTests(APITestCase):
    def setUp(self):
        self.raw_test_pk = '0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d'
        self.institution = Institution.objects.create(
            name='Test Tech University',
            institution_type=InstitutionType.UNIVERSITY,
            official_email_domain='testtech.edu',
            registration_number='TECH-777',
            proof_document='proofs/tech.pdf',
            wallet_address='0x90F79bf6EB2c4f870365E785982E1f101E93b906',
            status=InstitutionStatus.PENDING,
        )

    def test_encrypted_private_key_is_ciphertext_not_plaintext(self):
        """
        Confirms Institution.encrypted_private_key, when read directly via the DB/ORM,
        is genuinely Fernet ciphertext and NOT equal to or containing the raw private key.
        """
        self.institution.set_private_key(self.raw_test_pk)
        self.institution.save(update_fields=['encrypted_private_key'])

        # Reload directly from database to test persistence layer
        reloaded = Institution.objects.get(id=self.institution.id)

        # 1. Stored field must not be empty
        self.assertTrue(bool(reloaded.encrypted_private_key))
        # 2. Must not equal the raw key
        self.assertNotEqual(reloaded.encrypted_private_key, self.raw_test_pk)
        # 3. Must not contain the raw key string anywhere inside ciphertext
        self.assertNotIn(self.raw_test_pk, reloaded.encrypted_private_key)
        self.assertNotIn(self.raw_test_pk.replace('0x', ''), reloaded.encrypted_private_key)
        # 4. Decrypting in-memory recovers the original raw private key
        self.assertEqual(reloaded.get_decrypted_private_key(), self.raw_test_pk)

    def test_generate_custodial_wallet_roundtrip(self):
        """
        Confirms a generated custodial wallet creates a valid Ethereum keypair,
        stores the private key as ciphertext, and the decrypted key round-trips
        and matches the custodial wallet address.
        """
        from eth_account import Account

        original_address = self.institution.wallet_address
        new_address = self.institution.generate_custodial_wallet()
        self.institution.save()

        # Reload directly from DB
        reloaded = Institution.objects.get(id=self.institution.id)

        self.assertEqual(reloaded.registered_wallet_address, original_address)
        self.assertEqual(reloaded.wallet_address, new_address)
        self.assertTrue(reloaded.wallet_address.startswith('0x'))
        self.assertEqual(len(reloaded.wallet_address), 42)

        # Ciphertext check
        self.assertTrue(bool(reloaded.encrypted_private_key))
        decrypted_pk = reloaded.get_decrypted_private_key()
        self.assertIsNotNone(decrypted_pk)
        self.assertNotEqual(reloaded.encrypted_private_key, decrypted_pk)

        # Derived address from decrypted private key must match wallet_address
        account = Account.from_key(decrypted_pk)
        self.assertEqual(account.address.lower(), reloaded.wallet_address.lower())

    def test_blockchain_service_get_issuer_private_key_retrieval(self):
        """
        Confirms BlockchainService.get_issuer_private_key() successfully looks up
        an institution by its wallet address and decrypts its custodial key.
        """
        from apps.blockchain.services import BlockchainService

        self.institution.set_private_key(self.raw_test_pk)
        self.institution.save(update_fields=['encrypted_private_key'])

        key = BlockchainService.get_issuer_private_key(self.institution.wallet_address)
        self.assertEqual(key, self.raw_test_pk)

    def test_blockchain_service_get_issuer_private_key_fails_if_no_key(self):
        """
        Confirms BlockchainService.get_issuer_private_key() raises BlockchainError
        when the institution has no encrypted key stored or doesn't exist.
        """
        from apps.blockchain.services import BlockchainService
        from apps.blockchain.exceptions import BlockchainError

        # Inst has no encrypted key yet
        with self.assertRaises(BlockchainError):
            BlockchainService.get_issuer_private_key(self.institution.wallet_address)

        # Nonexistent wallet address
        with self.assertRaises(BlockchainError):
            BlockchainService.get_issuer_private_key('0x0000000000000000000000000000000000000000')
