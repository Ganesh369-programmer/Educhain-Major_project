"""
Blockchain service wrapper (web3.py).
This is the ONLY app/module that interacts directly with the Ethereum-compatible blockchain.
Handles issuer authorization on-chain (Phase 5) and credential issuance/verification (Phases 7/8).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Union, List
from uuid import UUID

from django.conf import settings
from web3 import Web3
from web3.exceptions import Web3Exception

from apps.blockchain.exceptions import BlockchainError, BlockchainRevertError
from apps.blockchain.models import (
    BlockchainAction,
    BlockchainTransaction,
    BlockchainTxStatus,
)

logger = logging.getLogger(__name__)

ABI_PATH = Path(__file__).resolve().parent / 'abi' / 'CredentialPlatform.json'


def to_bytes32(val: Union[str, bytes, UUID]) -> bytes:
    """
    Normalizes a UUID, hex string, or bytes into a 32-byte bytes object
    compatible with Solidity bytes32 parameters.
    """
    if isinstance(val, UUID):
        return bytes.fromhex(val.hex).rjust(32, b'\x00')
    if isinstance(val, bytes):
        if len(val) == 32:
            return val
        if len(val) < 32:
            return val.rjust(32, b'\x00')
        return val[:32]
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned.startswith('0x'):
            cleaned = cleaned[2:]
        try:
            parsed = UUID(cleaned)
            return bytes.fromhex(parsed.hex).rjust(32, b'\x00')
        except ValueError:
            pass
        try:
            raw = bytes.fromhex(cleaned)
            return raw.rjust(32, b'\x00') if len(raw) <= 32 else raw[:32]
        except ValueError:
            return Web3.keccak(text=val)
    raise ValueError(f"Cannot convert value of type {type(val)} to bytes32")


class BlockchainService:
    _cached_abi = None

    @classmethod
    def get_abi(cls) -> list:
        if cls._cached_abi is None:
            if not ABI_PATH.exists():
                raise BlockchainError(f"Contract ABI file not found at {ABI_PATH}")
            with open(ABI_PATH, 'r', encoding='utf-8') as f:
                cls._cached_abi = json.load(f)
        return cls._cached_abi

    @classmethod
    def get_rpc_url(cls) -> str:
        return (
            os.getenv('BLOCKCHAIN_RPC_URL')
            or getattr(settings, 'BLOCKCHAIN_RPC_URL', '')
            or 'http://127.0.0.1:7545'
        )

    @classmethod
    def get_chain_id(cls) -> int:
        raw = os.getenv('BLOCKCHAIN_CHAIN_ID') or getattr(settings, 'BLOCKCHAIN_CHAIN_ID', '1337')
        try:
            return int(raw)
        except (ValueError, TypeError):
            return 1337

    @classmethod
    def get_contract_address(cls) -> str:
        addr = os.getenv('CONTRACT_ADDRESS') or getattr(settings, 'CONTRACT_ADDRESS', '')
        if not addr:
            raise BlockchainError("CONTRACT_ADDRESS is not configured.")
        return addr

    @classmethod
    def get_admin_private_key(cls) -> str:
        # Strictly from environment variables per AGENTS.md and Phase 5 spec
        pk = os.getenv('PLATFORM_ADMIN_PRIVATE_KEY')
        if not pk or not str(pk).strip():
            raise BlockchainError("PLATFORM_ADMIN_PRIVATE_KEY environment variable is not configured.")
        return str(pk).strip()

    @classmethod
    def get_issuer_private_key(cls, wallet_address: str) -> str:
        """
        Retrieves the private key for an approved issuer's custodial wallet.
        Looks up the Institution by wallet_address (or registered_wallet_address)
        and decrypts its custodial private key in-memory.
        Never logs, returns over HTTP, or persists the raw key.
        """
        if not wallet_address:
            raise BlockchainError("wallet_address is required to retrieve issuer private key.")

        from apps.institutions.models import Institution
        from django.db.models import Q

        try:
            institution = Institution.objects.filter(
                Q(wallet_address__iexact=wallet_address) |
                Q(registered_wallet_address__iexact=wallet_address)
            ).first()
        except Exception as exc:
            raise BlockchainError(f"Database error looking up institution for {wallet_address}: {exc}")

        if not institution:
            raise BlockchainError(f"No institution found for wallet address {wallet_address}.")

        decrypted_pk = institution.get_decrypted_private_key()
        if not decrypted_pk:
            raise BlockchainError(
                f"No custodial private key found for institution {institution.name} ({wallet_address})."
            )

        return decrypted_pk

    @classmethod
    def get_web3(cls) -> Web3:
        rpc_url = cls.get_rpc_url()
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
            if not w3.is_connected():
                raise BlockchainError(f"Unable to connect to blockchain node at {rpc_url}")
            return w3
        except BlockchainError:
            raise
        except Exception as exc:
            logger.error("Blockchain RPC connection failure: %s", exc)
            raise BlockchainError(f"Blockchain RPC node unreachable: {exc}")

    @classmethod
    def get_contract(cls, w3: Optional[Web3] = None):
        w3 = w3 or cls.get_web3()
        raw_address = cls.get_contract_address()
        try:
            checksum_address = w3.to_checksum_address(raw_address)
        except Exception as exc:
            raise BlockchainError(f"Invalid contract address '{raw_address}': {exc}")
        abi = cls.get_abi()
        return w3.eth.contract(address=checksum_address, abi=abi)

    @classmethod
    def is_authorized_issuer(cls, wallet_address: str) -> bool:
        """
        Public/view check on whether an address is whitelisted on-chain.
        """
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)
        try:
            checksum_address = w3.to_checksum_address(wallet_address)
            return bool(contract.functions.isAuthorizedIssuer(checksum_address).call())
        except Exception as exc:
            logger.error("Error checking isAuthorizedIssuer for %s: %s", wallet_address, exc)
            raise BlockchainError(f"Failed to query issuer status on-chain: {exc}")

    @classmethod
    def approve_issuer(
        cls,
        wallet_address: str,
        name: str,
        trust_tier: int,
        related_object_id: Optional[UUID] = None,
    ) -> str:
        """
        Calls approveIssuer(issuerAddress, name, trustTier) on-chain using the platform admin wallet.
        Logs transaction to BlockchainTransaction model.
        Returns the transaction hash (str).
        """
        admin_pk = cls.get_admin_private_key()
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)

        try:
            admin_account = w3.eth.account.from_key(admin_pk)
        except Exception as exc:
            raise BlockchainError(f"Invalid PLATFORM_ADMIN_PRIVATE_KEY: {exc}")

        try:
            checksum_issuer = w3.to_checksum_address(wallet_address)
        except Exception as exc:
            raise BlockchainError(f"Invalid issuer wallet address '{wallet_address}': {exc}")

        try:
            tier_int = int(trust_tier)
        except (ValueError, TypeError):
            raise BlockchainError("Trust tier must be a valid integer.")

        fn_call = contract.functions.approveIssuer(checksum_issuer, str(name), tier_int)

        # Gas estimation and revert detection
        try:
            estimated_gas = fn_call.estimate_gas({'from': admin_account.address})
            gas_limit = int(estimated_gas * 1.25)
        except Exception as exc:
            err_str = str(exc)
            logger.warning("Gas estimation failed: %s", err_str)
            if "not platform admin" in err_str.lower() or "revert" in err_str.lower():
                raise BlockchainRevertError(f"Transaction reverted during estimation: {err_str}")
            # Retry once with fallback gas limit per spec
            gas_limit = 250000

        try:
            nonce = w3.eth.get_transaction_count(admin_account.address, 'pending')
            chain_id = cls.get_chain_id()
            gas_price = w3.eth.gas_price

            tx_dict = fn_call.build_transaction({
                'from': admin_account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
            })
            signed_tx = w3.eth.account.sign_transaction(tx_dict, private_key=admin_pk)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            tx_hash_bytes = w3.eth.send_raw_transaction(raw_tx)
            tx_hash = w3.to_hex(tx_hash_bytes)
        except (BlockchainError, BlockchainRevertError):
            raise
        except Exception as exc:
            logger.error("Failed to broadcast transaction: %s", exc)
            raise BlockchainError(f"Failed to broadcast transaction: {exc}")

        # Record pending transaction log
        tx_record = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            action=BlockchainAction.APPROVE_ISSUER,
            related_object_id=related_object_id,
            status=BlockchainTxStatus.PENDING,
        )

        # Wait for receipt confirmation
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=30)
            receipt_status = receipt.get('status') if isinstance(receipt, dict) else receipt.status
            gas_used = receipt.get('gasUsed') if isinstance(receipt, dict) else getattr(receipt, 'gasUsed', None)

            if receipt_status == 1:
                tx_record.status = BlockchainTxStatus.CONFIRMED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.info("Transaction %s confirmed (gas used: %s)", tx_hash, gas_used)
                return tx_hash
            else:
                tx_record.status = BlockchainTxStatus.FAILED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.error("Transaction %s reverted on-chain", tx_hash)
                raise BlockchainError("Transaction reverted on-chain.")
        except BlockchainError:
            raise
        except Exception as exc:
            tx_record.status = BlockchainTxStatus.FAILED
            tx_record.save(update_fields=['status'])
            logger.error("Error waiting for transaction receipt %s: %s", tx_hash, exc)
            raise BlockchainError(f"Transaction confirmation failed or timed out: {exc}")

    @classmethod
    def revoke_issuer(
        cls,
        wallet_address: str,
        related_object_id: Optional[UUID] = None,
    ) -> str:
        """
        Calls revokeIssuer(issuerAddress) on-chain using the platform admin wallet.
        """
        admin_pk = cls.get_admin_private_key()
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)

        try:
            admin_account = w3.eth.account.from_key(admin_pk)
            checksum_issuer = w3.to_checksum_address(wallet_address)
        except Exception as exc:
            raise BlockchainError(f"Invalid account or address: {exc}")

        fn_call = contract.functions.revokeIssuer(checksum_issuer)

        try:
            estimated_gas = fn_call.estimate_gas({'from': admin_account.address})
            gas_limit = int(estimated_gas * 1.25)
        except Exception as exc:
            err_str = str(exc)
            if "not platform admin" in err_str.lower() or "revert" in err_str.lower():
                raise BlockchainRevertError(f"Transaction reverted during estimation: {err_str}")
            gas_limit = 200000

        try:
            nonce = w3.eth.get_transaction_count(admin_account.address, 'pending')
            chain_id = cls.get_chain_id()
            gas_price = w3.eth.gas_price

            tx_dict = fn_call.build_transaction({
                'from': admin_account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
            })
            signed_tx = w3.eth.account.sign_transaction(tx_dict, private_key=admin_pk)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            tx_hash_bytes = w3.eth.send_raw_transaction(raw_tx)
            tx_hash = w3.to_hex(tx_hash_bytes)
        except (BlockchainError, BlockchainRevertError):
            raise
        except Exception as exc:
            raise BlockchainError(f"Failed to broadcast transaction: {exc}")

        tx_record = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            action=BlockchainAction.REVOKE_ISSUER,
            related_object_id=related_object_id,
            status=BlockchainTxStatus.PENDING,
        )

        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=30)
            receipt_status = receipt.get('status') if isinstance(receipt, dict) else receipt.status
            gas_used = receipt.get('gasUsed') if isinstance(receipt, dict) else getattr(receipt, 'gasUsed', None)

            if receipt_status == 1:
                tx_record.status = BlockchainTxStatus.CONFIRMED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                return tx_hash
            else:
                tx_record.status = BlockchainTxStatus.FAILED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                raise BlockchainError("Transaction reverted on-chain.")
        except BlockchainError:
            raise
        except Exception as exc:
            tx_record.status = BlockchainTxStatus.FAILED
            tx_record.save(update_fields=['status'])
            raise BlockchainError(f"Transaction confirmation failed: {exc}")

    @classmethod
    def issue_credential(
        cls,
        credential_id: Union[str, bytes, UUID],
        document_hash: Union[str, bytes],
        ipfs_cid: str,
        issuer_wallet_address: str,
        related_object_id: Optional[UUID] = None,
    ) -> str:
        """
        Calls issueCredential(credentialId, documentHash, ipfsCID) on-chain.
        Signed by the approved issuer's decrypted custodial private key.
        Logs transaction to BlockchainTransaction model.
        Returns the transaction hash (str).
        """
        signer_pk = cls.get_issuer_private_key(issuer_wallet_address)
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)

        try:
            issuer_account = w3.eth.account.from_key(signer_pk)
        except Exception as exc:
            raise BlockchainError(f"Invalid issuer private key: {exc}")

        cred_id_bytes = to_bytes32(credential_id)
        doc_hash_bytes = to_bytes32(document_hash)

        fn_call = contract.functions.issueCredential(
            cred_id_bytes,
            doc_hash_bytes,
            str(ipfs_cid),
        )

        try:
            estimated_gas = fn_call.estimate_gas({'from': issuer_account.address})
            gas_limit = int(estimated_gas * 1.25)
        except Exception as exc:
            err_str = str(exc)
            logger.warning("Gas estimation failed for issueCredential: %s", err_str)
            if "issuer not whitelisted" in err_str.lower():
                raise BlockchainRevertError("Issuer not whitelisted on-chain.")
            if "already exists" in err_str.lower():
                raise BlockchainRevertError("Credential already exists on-chain.")
            if "revert" in err_str.lower():
                raise BlockchainRevertError(f"Transaction reverted during estimation: {err_str}")
            gas_limit = 300000

        try:
            nonce = w3.eth.get_transaction_count(issuer_account.address, 'pending')
            chain_id = cls.get_chain_id()
            gas_price = w3.eth.gas_price

            tx_dict = fn_call.build_transaction({
                'from': issuer_account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
            })
            signed_tx = w3.eth.account.sign_transaction(tx_dict, private_key=signer_pk)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            tx_hash_bytes = w3.eth.send_raw_transaction(raw_tx)
            tx_hash = w3.to_hex(tx_hash_bytes)
        except (BlockchainError, BlockchainRevertError):
            raise
        except Exception as exc:
            logger.error("Failed to broadcast issueCredential transaction: %s", exc)
            raise BlockchainError(f"Failed to broadcast transaction: {exc}")

        tx_record = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            action=BlockchainAction.ISSUE_CREDENTIAL,
            related_object_id=related_object_id,
            status=BlockchainTxStatus.PENDING,
        )

        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=30)
            receipt_status = receipt.get('status') if isinstance(receipt, dict) else receipt.status
            gas_used = receipt.get('gasUsed') if isinstance(receipt, dict) else getattr(receipt, 'gasUsed', None)

            if receipt_status == 1:
                tx_record.status = BlockchainTxStatus.CONFIRMED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.info("Credential issuance tx %s confirmed (gas used: %s)", tx_hash, gas_used)
                return tx_hash
            else:
                tx_record.status = BlockchainTxStatus.FAILED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.error("Credential issuance tx %s reverted on-chain", tx_hash)
                raise BlockchainError("Transaction reverted on-chain.")
        except BlockchainError:
            raise
        except Exception as exc:
            tx_record.status = BlockchainTxStatus.FAILED
            tx_record.save(update_fields=['status'])
            logger.error("Error waiting for transaction receipt %s: %s", tx_hash, exc)
            raise BlockchainError(f"Transaction confirmation failed or timed out: {exc}")

    @classmethod
    def batch_issue_credentials(
        cls,
        credential_ids: List[Union[str, bytes, UUID]],
        document_hashes: List[Union[str, bytes]],
        ipfs_cids: List[str],
        issuer_wallet_address: str,
        related_object_id: Optional[UUID] = None,
    ) -> str:
        """
        Calls batchIssueCredentials(credentialIds, documentHashes, ipfsCIDs) on-chain.
        Signed by the approved issuer's decrypted custodial private key.
        Logs transaction to BlockchainTransaction model.
        Returns the transaction hash (str).
        """
        signer_pk = cls.get_issuer_private_key(issuer_wallet_address)
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)

        try:
            issuer_account = w3.eth.account.from_key(signer_pk)
        except Exception as exc:
            raise BlockchainError(f"Invalid issuer private key: {exc}")

        cred_ids_bytes = [to_bytes32(cid) for cid in credential_ids]
        doc_hashes_bytes = [to_bytes32(dh) for dh in document_hashes]
        str_cids = [str(c) for c in ipfs_cids]

        fn_call = contract.functions.batchIssueCredentials(
            cred_ids_bytes,
            doc_hashes_bytes,
            str_cids,
        )

        try:
            estimated_gas = fn_call.estimate_gas({'from': issuer_account.address})
            gas_limit = int(estimated_gas * 1.25)
        except Exception as exc:
            err_str = str(exc)
            logger.warning("Gas estimation failed for batchIssueCredentials: %s", err_str)
            if "issuer not whitelisted" in err_str.lower():
                raise BlockchainRevertError("Issuer not whitelisted on-chain.")
            if "array length mismatch" in err_str.lower():
                raise BlockchainRevertError("Array length mismatch in batch issuance.")
            if "already exists" in err_str.lower():
                raise BlockchainRevertError("One or more credentials in batch already exist on-chain.")
            if "revert" in err_str.lower():
                raise BlockchainRevertError(f"Transaction reverted during estimation: {err_str}")
            gas_limit = 500000 + len(credential_ids) * 100000

        try:
            nonce = w3.eth.get_transaction_count(issuer_account.address, 'pending')
            chain_id = cls.get_chain_id()
            gas_price = w3.eth.gas_price

            tx_dict = fn_call.build_transaction({
                'from': issuer_account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
            })
            signed_tx = w3.eth.account.sign_transaction(tx_dict, private_key=signer_pk)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            tx_hash_bytes = w3.eth.send_raw_transaction(raw_tx)
            tx_hash = w3.to_hex(tx_hash_bytes)
        except (BlockchainError, BlockchainRevertError):
            raise
        except Exception as exc:
            logger.error("Failed to broadcast batchIssueCredentials: %s", exc)
            raise BlockchainError(f"Failed to broadcast batch transaction: {exc}")

        tx_record = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            action=BlockchainAction.ISSUE_CREDENTIAL,
            related_object_id=related_object_id,
            status=BlockchainTxStatus.PENDING,
        )

        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=45)
            receipt_status = receipt.get('status') if isinstance(receipt, dict) else receipt.status
            gas_used = receipt.get('gasUsed') if isinstance(receipt, dict) else getattr(receipt, 'gasUsed', None)

            if receipt_status == 1:
                tx_record.status = BlockchainTxStatus.CONFIRMED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.info("Batch issuance tx %s confirmed (gas used: %s)", tx_hash, gas_used)
                return tx_hash
            else:
                tx_record.status = BlockchainTxStatus.FAILED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                raise BlockchainError("Batch transaction reverted on-chain.")
        except BlockchainError:
            raise
        except Exception as exc:
            tx_record.status = BlockchainTxStatus.FAILED
            tx_record.save(update_fields=['status'])
            logger.error("Error waiting for batch receipt %s: %s", tx_hash, exc)
            raise BlockchainError(f"Batch transaction confirmation failed: {exc}")

    @classmethod
    def revoke_credential(
        cls,
        credential_id: Union[str, bytes, UUID],
        issuer_wallet_address: str,
        related_object_id: Optional[UUID] = None,
    ) -> str:
        """
        Calls revokeCredential(credentialId) on-chain.
        Signed by the approved issuer's decrypted custodial private key.
        Logs transaction to BlockchainTransaction model.
        Returns the transaction hash (str).
        """
        signer_pk = cls.get_issuer_private_key(issuer_wallet_address)
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)

        try:
            issuer_account = w3.eth.account.from_key(signer_pk)
        except Exception as exc:
            raise BlockchainError(f"Invalid issuer private key: {exc}")

        cred_id_bytes = to_bytes32(credential_id)
        fn_call = contract.functions.revokeCredential(cred_id_bytes)

        try:
            estimated_gas = fn_call.estimate_gas({'from': issuer_account.address})
            gas_limit = int(estimated_gas * 1.25)
        except Exception as exc:
            err_str = str(exc)
            logger.warning("Gas estimation failed for revokeCredential: %s", err_str)
            if "revert" in err_str.lower():
                raise BlockchainRevertError(f"Transaction reverted during estimation: {err_str}")
            gas_limit = 200000

        try:
            nonce = w3.eth.get_transaction_count(issuer_account.address, 'pending')
            chain_id = cls.get_chain_id()
            gas_price = w3.eth.gas_price

            tx_dict = fn_call.build_transaction({
                'from': issuer_account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
            })
            signed_tx = w3.eth.account.sign_transaction(tx_dict, private_key=signer_pk)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            tx_hash_bytes = w3.eth.send_raw_transaction(raw_tx)
            tx_hash = w3.to_hex(tx_hash_bytes)
        except (BlockchainError, BlockchainRevertError):
            raise
        except Exception as exc:
            logger.error("Failed to broadcast revokeCredential transaction: %s", exc)
            raise BlockchainError(f"Failed to broadcast transaction: {exc}")

        tx_record = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            action=BlockchainAction.REVOKE_CREDENTIAL,
            related_object_id=related_object_id,
            status=BlockchainTxStatus.PENDING,
        )

        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=30)
            receipt_status = receipt.get('status') if isinstance(receipt, dict) else receipt.status
            gas_used = receipt.get('gasUsed') if isinstance(receipt, dict) else getattr(receipt, 'gasUsed', None)

            if receipt_status == 1:
                tx_record.status = BlockchainTxStatus.CONFIRMED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.info("Credential revocation tx %s confirmed (gas used: %s)", tx_hash, gas_used)
                return tx_hash
            else:
                tx_record.status = BlockchainTxStatus.FAILED
                tx_record.gas_used = gas_used
                tx_record.save(update_fields=['status', 'gas_used'])
                logger.error("Credential revocation tx %s reverted on-chain", tx_hash)
                raise BlockchainError("Transaction reverted on-chain.")
        except BlockchainError:
            raise
        except Exception as exc:
            tx_record.status = BlockchainTxStatus.FAILED
            tx_record.save(update_fields=['status'])
            logger.error("Error waiting for transaction receipt %s: %s", tx_hash, exc)
            raise BlockchainError(f"Transaction confirmation failed or timed out: {exc}")

    @classmethod
    def verify_credential(cls, credential_id: Union[str, bytes, UUID]) -> dict:
        """
        Public/view query calling verifyCredential(bytes32) on-chain.
        Returns dictionary with exists, revoked, issuer, document_hash, issued_on.
        """
        w3 = cls.get_web3()
        contract = cls.get_contract(w3)
        cred_id_bytes = to_bytes32(credential_id)
        try:
            exists, revoked, issuer, doc_hash_bytes, issued_on = contract.functions.verifyCredential(cred_id_bytes).call()
            doc_hash_hex = w3.to_hex(doc_hash_bytes) if isinstance(doc_hash_bytes, (bytes, bytearray)) else str(doc_hash_bytes)
            return {
                'exists': bool(exists),
                'revoked': bool(revoked),
                'issuer': str(issuer),
                'document_hash': doc_hash_hex,
                'issued_on': int(issued_on),
            }
        except Exception as exc:
            logger.error("Failed to verify credential on-chain %s: %s", credential_id, exc)
            raise BlockchainError(f"Failed to query verifyCredential on-chain: {exc}")


# Convenience module-level aliases
approve_issuer = BlockchainService.approve_issuer
revoke_issuer = BlockchainService.revoke_issuer
is_authorized_issuer = BlockchainService.is_authorized_issuer
issue_credential = BlockchainService.issue_credential
batch_issue_credentials = BlockchainService.batch_issue_credentials
verify_credential = BlockchainService.verify_credential
