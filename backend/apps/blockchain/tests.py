import os
from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserRole
from apps.institutions.models import Institution, InstitutionStatus, InstitutionType
from apps.blockchain.models import (
    BlockchainTransaction,
    BlockchainAction,
    BlockchainTxStatus,
)
from apps.blockchain.services import BlockchainService
from apps.blockchain.exceptions import BlockchainError, BlockchainRevertError


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return f'Bearer {refresh.access_token}'


class BlockchainModelTests(TestCase):
    def test_create_blockchain_transaction(self):
        tx = BlockchainTransaction.objects.create(
            tx_hash='0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
            action=BlockchainAction.APPROVE_ISSUER,
            status=BlockchainTxStatus.CONFIRMED,
            gas_used=45000,
        )
        self.assertIsNotNone(tx.id)
        self.assertEqual(tx.status, BlockchainTxStatus.CONFIRMED)
        self.assertEqual(tx.gas_used, 45000)
        self.assertIn('APPROVE_ISSUER', str(tx))


class BlockchainServiceUnitTests(TestCase):
    def test_missing_admin_key_raises_blockchain_error(self):
        with patch.dict(os.environ, {'PLATFORM_ADMIN_PRIVATE_KEY': ''}):
            with self.assertRaises(BlockchainError) as ctx:
                BlockchainService.approve_issuer(
                    wallet_address='0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1',
                    name='Test Inst',
                    trust_tier=1,
                )
            self.assertIn('PLATFORM_ADMIN_PRIVATE_KEY', str(ctx.exception.detail))

    def test_invalid_contract_address_raises_blockchain_error(self):
        with patch.dict(os.environ, {'CONTRACT_ADDRESS': '0xinvalid'}):
            with self.assertRaises(BlockchainError):
                BlockchainService.approve_issuer(
                    wallet_address='0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1',
                    name='Test Inst',
                    trust_tier=1,
                )

    def test_unreachable_node_raises_blockchain_error(self):
        with patch.dict(os.environ, {'BLOCKCHAIN_RPC_URL': 'http://127.0.0.1:9999'}):
            with self.assertRaises(BlockchainError):
                BlockchainService.approve_issuer(
                    wallet_address='0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1',
                    name='Test Inst',
                    trust_tier=1,
                )


class IssuerAuthorizationIntegrationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='admin@educhain.local',
            password='Password123!',
        )
        # Using a valid Ganache test account
        self.inst_wallet = '0x22d491Bde2303f2f43325b2108D26f1eAbA1e32b'
        self.institution = Institution.objects.create(
            name='National Institute of Technology',
            institution_type=InstitutionType.UNIVERSITY,
            official_email_domain='nit.edu',
            registration_number='NIT-001',
            proof_document='nit/proof.pdf',
            wallet_address=self.inst_wallet,
            status=InstitutionStatus.PENDING,
        )
        self.approve_url = f'/api/v1/institutions/{self.institution.id}/approve/'

    def test_1_approve_fails_safely_when_admin_wallet_unconfigured(self):
        """
        Negative case: Admin wallet missing/unconfigured.
        Transaction must fail with 502 BLOCKCHAIN_ERROR, and Institution DB status must remain PENDING.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        with patch.dict(os.environ, {'PLATFORM_ADMIN_PRIVATE_KEY': ''}):
            response = self.client.post(
                self.approve_url,
                {'trust_tier': 1},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
            self.assertEqual(response.data['code'], 'BLOCKCHAIN_ERROR')

            # Verify Institution DB status is uncorrupted
            self.institution.refresh_from_db()
            self.assertEqual(self.institution.status, InstitutionStatus.PENDING)
            self.assertIsNone(self.institution.trust_tier)
            self.assertIsNone(self.institution.reviewed_by)
            self.assertIsNone(self.institution.reviewed_at)

    def test_2_approve_happy_path_end_to_end(self):
        """
        Happy path: Approval executes on-chain, updates DB status to APPROVED,
        logs BlockchainTransaction, and wallet is authorized on-chain.
        """
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.admin))
        response = self.client.post(
            self.approve_url,
            {'trust_tier': 1},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], InstitutionStatus.APPROVED)
        tx_hash = response.data.get('tx_hash')
        self.assertIsNotNone(tx_hash)
        self.assertTrue(tx_hash.startswith('0x'))

        # Verify DB status updated
        self.institution.refresh_from_db()
        self.assertEqual(self.institution.status, InstitutionStatus.APPROVED)
        self.assertEqual(self.institution.trust_tier, 1)
        self.assertEqual(self.institution.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(self.institution.reviewed_at)

        # Verify BlockchainTransaction logged per docs/DATABASE_SCHEMA.md
        tx_log = BlockchainTransaction.objects.filter(tx_hash=tx_hash).first()
        self.assertIsNotNone(tx_log)
        self.assertEqual(tx_log.action, BlockchainAction.APPROVE_ISSUER)
        self.assertEqual(tx_log.related_object_id, self.institution.id)
        self.assertEqual(tx_log.status, BlockchainTxStatus.CONFIRMED)
        self.assertGreater(tx_log.gas_used, 0)

        # Verify on-chain whitelist status via isAuthorizedIssuer
        # Explicit consistency check: after approval, institution.wallet_address (refreshed from DB)
        # is the SAME address that BlockchainService.is_authorized_issuer() confirms as True.
        self.institution.refresh_from_db()
        is_authorized = BlockchainService.is_authorized_issuer(self.institution.wallet_address)
        self.assertTrue(
            is_authorized,
            f"Expected refreshed institution.wallet_address ({self.institution.wallet_address}) to be authorized on-chain"
        )
        self.assertEqual(self.institution.registered_wallet_address, self.inst_wallet)
        self.assertFalse(BlockchainService.is_authorized_issuer(self.institution.registered_wallet_address))
