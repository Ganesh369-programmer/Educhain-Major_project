"""
IPFS Service abstraction and local mock implementation for Phase 8.

Design principles per docs/FEATURE_ROADMAP.md and docs/ARCHITECTURE.md:
- Wrap storage behind a small IpfsService class/interface so swapping in a real IPFS node
  (e.g., Infura / Pinata / local go-ipfs daemon) later only requires changing this one class,
  with zero changes required in any calling view, serializer, or model.
- Generate deterministic CID-like identifier:
  Implements standard IPFS CIDv0 format (base58-encoded multihash: 0x12 sha256 + 32-byte digest)
  starting with 'Qm' (46 chars), completely reproducible for identical document bytes.
- Store documents in local media directory: `settings.MEDIA_ROOT / 'ipfs_mock'`.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Base58 character alphabet for canonical IPFS CIDv0 encoding
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58_encode(data: bytes) -> str:
    """Encodes bytes into a Base58 string."""
    n = int.from_bytes(data, 'big')
    encoded = []
    while n > 0:
        n, remainder = divmod(n, 58)
        encoded.append(BASE58_ALPHABET[remainder])
    
    # Preserve leading zero bytes as '1's
    pad = 0
    for byte in data:
        if byte == 0:
            pad += 1
        else:
            break
    return ('1' * pad) + ''.join(reversed(encoded))


def compute_ipfs_cid(file_bytes: bytes) -> str:
    """
    Computes a deterministic IPFS CIDv0 for the provided bytes.
    CIDv0 multihash format:
      0x12 (SHA-256 algorithm code) + 0x20 (32-byte length) + 32-byte SHA-256 digest
    Encoded in base58, this produces a standard 46-character string starting with 'Qm'.
    """
    sha256_digest = hashlib.sha256(file_bytes).digest()
    multihash = b'\x12\x20' + sha256_digest
    return base58_encode(multihash)


def compute_document_hash(file_bytes: bytes) -> str:
    """
    Computes the 66-character 0x-prefixed SHA-256 hex string required for
    on-chain bytes32 anchoring and Credential.document_hash.
    """
    return '0x' + hashlib.sha256(file_bytes).hexdigest().lower()


class BaseIpfsService:
    """Abstract base class for IPFS operations."""
    def upload_document(self, file_bytes: bytes, filename: Optional[str] = None) -> str:
        raise NotImplementedError

    def get_document(self, cid: str) -> Optional[bytes]:
        raise NotImplementedError

    def document_exists(self, cid: str) -> bool:
        raise NotImplementedError


class MockIpfsService(BaseIpfsService):
    """
    Local file-based mock IPFS service.
    Stores files under MEDIA_ROOT / 'ipfs_mock' indexed by CID.
    """
    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            media_root = getattr(settings, 'MEDIA_ROOT', None)
            if not media_root:
                media_root = Path(settings.BASE_DIR) / 'media'
            storage_dir = Path(media_root) / 'ipfs_mock'
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def upload_document(self, file_bytes: bytes, filename: Optional[str] = None) -> str:
        """
        Stores the document bytes locally and returns the deterministic IPFS CID.
        """
        cid = compute_ipfs_cid(file_bytes)
        file_path = self.storage_dir / cid
        if not file_path.exists():
            file_path.write_bytes(file_bytes)
            logger.info("Mock IPFS: stored document %s (%d bytes)", cid, len(file_bytes))
        return cid

    def get_document(self, cid: str) -> Optional[bytes]:
        """
        Retrieves the raw document bytes for a given CID.
        """
        file_path = self.storage_dir / cid
        if file_path.exists() and file_path.is_file():
            return file_path.read_bytes()
        return None

    def document_exists(self, cid: str) -> bool:
        """
        Checks whether a document with the given CID exists in storage.
        """
        file_path = self.storage_dir / cid
        return file_path.exists() and file_path.is_file()


# Primary service instance for dependency injection across credentials app
IpfsService = MockIpfsService
default_ipfs_service = MockIpfsService()
