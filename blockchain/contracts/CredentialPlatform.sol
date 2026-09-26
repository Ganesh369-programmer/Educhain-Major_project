// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title CredentialPlatform
 * @dev Manages the platform admin and authorized institutional issuers.
 * Credential issuance and revocation functions will be added in Phase 7.
 */
contract CredentialPlatform {
    address public admin;

    struct Issuer {
        bool isApproved;
        uint8 trustTier;       // 1 = University, 2 = Company/NGO, 3 = Self-declared
        string institutionName;
        uint256 approvedOn;
    }

    struct Credential {
        address issuer;          // Wallet address of the institution that issued this credential
        bytes32 documentHash;    // Cryptographic hash (e.g. SHA-256) of the original PDF / document
        string ipfsCID;          // Decentralized storage reference pointing to the encrypted or off-chain record
        uint256 issuedOn;        // Timestamp when the credential was anchored on-chain
        bool revoked;            // Revocation flag (true if no longer valid)
        uint256 revokedOn;       // Timestamp when the credential was revoked (0 if active)
    }

    mapping(address => Issuer) public issuers;
    mapping(bytes32 => Credential) public credentials;

    event IssuerApproved(address indexed issuer, string name, uint8 trustTier, uint256 timestamp);
    event IssuerRevoked(address indexed issuer, uint256 timestamp);
    event CredentialIssued(bytes32 indexed credentialId, address indexed issuer, bytes32 documentHash, uint256 timestamp);
    event CredentialRevoked(bytes32 indexed credentialId, address indexed issuer, uint256 timestamp);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not platform admin");
        _;
    }

    modifier onlyApprovedIssuer() {
        require(issuers[msg.sender].isApproved, "Issuer not whitelisted");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function approveIssuer(address issuerAddress, string calldata name, uint8 trustTier) external onlyAdmin {
        issuers[issuerAddress] = Issuer(true, trustTier, name, block.timestamp);
        emit IssuerApproved(issuerAddress, name, trustTier, block.timestamp);
    }

    function revokeIssuer(address issuerAddress) external onlyAdmin {
        issuers[issuerAddress].isApproved = false;
        emit IssuerRevoked(issuerAddress, block.timestamp);
    }

    function isAuthorizedIssuer(address issuerAddress) external view returns (bool) {
        return issuers[issuerAddress].isApproved;
    }

    /**
     * @notice Issues and anchors a single academic credential onto the blockchain.
     * 
     * WHY THIS EXISTS:
     * When an institution awards a degree or certificate, they call this function to register
     * an unalterable proof of that credential on the blockchain. Once written, the timestamp,
     * issuing institution address, and document fingerprint become permanent.
     * 
     * WHAT EACH CHECK PROTECTS AGAINST:
     * 1. `onlyApprovedIssuer`: Protects against impostors or random public addresses registering
     *    fraudulent certificates. Only vetted institutions authorized by the platform admin can issue.
     * 2. `require(credentials[credentialId].issuedOn == 0, "Credential already exists")`:
     *    Protects against duplicate registrations or overwriting existing certificates. If a
     *    credential with this ID was already issued, attempting to re-issue it is rejected so an
     *    existing record can never be tampered with or replaced.
     */
    function issueCredential(
        bytes32 credentialId,
        bytes32 documentHash,
        string calldata ipfsCID
    ) external onlyApprovedIssuer {
        require(credentials[credentialId].issuedOn == 0, "Credential already exists");
        credentials[credentialId] = Credential(msg.sender, documentHash, ipfsCID, block.timestamp, false, 0);
        emit CredentialIssued(credentialId, msg.sender, documentHash, block.timestamp);
    }

    /**
     * @notice Issues multiple academic credentials in a single blockchain transaction.
     * 
     * WHY THIS EXISTS:
     * Educational institutions frequently graduate entire cohorts or classes at the same time.
     * Submitting transactions individually would be slow and waste significant gas fees.
     * This batch function lets an institution register dozens or hundreds of credentials in one go.
     * 
     * WHAT EACH CHECK PROTECTS AGAINST:
     * 1. `onlyApprovedIssuer`: Ensures only approved institutions can perform bulk credential issuance.
     * 2. `require(credentialIds.length == documentHashes.length && documentHashes.length == ipfsCIDs.length, "Array length mismatch")`:
     *    Protects against data corruption caused by misaligned arrays. If the caller accidentally
     *    supplies 10 IDs but only 9 document hashes, records would mismatch or corrupt; this check
     *    guarantees every single credential has complete, matching input parameters.
     * 3. `require(credentials[credentialIds[i]].issuedOn == 0, "Credential already exists")`:
     *    Protects against re-issuing or overwriting any credential in the batch. If even one ID in
     *    the batch is already registered, the entire transaction safely reverts to prevent collisions.
     */
    function batchIssueCredentials(
        bytes32[] calldata credentialIds,
        bytes32[] calldata documentHashes,
        string[] calldata ipfsCIDs
    ) external onlyApprovedIssuer {
        require(
            credentialIds.length == documentHashes.length && documentHashes.length == ipfsCIDs.length,
            "Array length mismatch"
        );
        for (uint256 i = 0; i < credentialIds.length; i++) {
            require(credentials[credentialIds[i]].issuedOn == 0, "Credential already exists");
            credentials[credentialIds[i]] = Credential(msg.sender, documentHashes[i], ipfsCIDs[i], block.timestamp, false, 0);
            emit CredentialIssued(credentialIds[i], msg.sender, documentHashes[i], block.timestamp);
        }
    }

    /**
     * @notice Permanently revokes an existing academic credential.
     * 
     * WHY THIS EXISTS:
     * If a certificate was issued in error, if an academic fraud is later uncovered, or if a
     * student is expelled, the issuing institution or the platform admin needs a way to mark
     * the certificate invalid on-chain so that future verifications will immediately fail.
     * 
     * WHAT EACH CHECK PROTECTS AGAINST:
     * 1. `require(c.issuedOn != 0, "Credential does not exist")`:
     *    Protects against revoking non-existent records. We cannot invalidate a certificate that
     *    was never created in the first place.
     * 2. `require(c.issuer == msg.sender || msg.sender == admin, "Not authorized to revoke")`:
     *    Protects against unauthorized tampering. Random third parties, rival institutions, or
     *    malicious users cannot revoke someone else's credentials. Only the original issuing
     *    institution or the emergency platform admin has permission to revoke.
     * 3. `require(!c.revoked, "Already revoked")`:
     *    Protects against redundant operations and enforces the one-way state transition. Revocation
     *    is final and irreversible; once revoked, a credential cannot be revoked again or revived.
     */
    function revokeCredential(bytes32 credentialId) external {
        Credential storage c = credentials[credentialId];
        require(c.issuedOn != 0, "Credential does not exist");
        require(c.issuer == msg.sender || msg.sender == admin, "Not authorized to revoke");
        require(!c.revoked, "Already revoked");
        c.revoked = true;
        c.revokedOn = block.timestamp;
        emit CredentialRevoked(credentialId, msg.sender, block.timestamp);
    }

    /**
     * @notice Publicly queries the status and authenticity data of a credential.
     * 
     * WHY THIS EXISTS:
     * This is the core verification mechanism of the platform. Anyone (employers, recruiters,
     * universities, or students) can call this function for free without paying gas fees to
     * determine whether a credential is genuine, who issued it, what document hash was anchored,
     * and whether it has been revoked.
     * 
     * Note: This is a `view` function that does not modify contract state and does not require gas
     * when called externally.
     */
    function verifyCredential(bytes32 credentialId) external view returns (
        bool exists,
        bool revoked,
        address issuer,
        bytes32 documentHash,
        uint256 issuedOn
    ) {
        Credential memory c = credentials[credentialId];
        exists = c.issuedOn != 0;
        return (exists, c.revoked, c.issuer, c.documentHash, c.issuedOn);
    }
}
