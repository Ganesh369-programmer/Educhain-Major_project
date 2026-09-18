# Blockchain Specification

## Design Principle

The smart contract is intentionally minimal: it is the **tamper-evident source of truth** for (a) who is allowed to issue credentials and (b) whether a given credential hash is valid or revoked. Everything else — names, emails, full documents, KYC files — stays off-chain. See `SECURITY.md` for the reasoning.

## What Goes On-Chain

- Credential ID (bytes32)
- Credential document hash (bytes32, SHA-256 or keccak256 of the document)
- Issuer wallet address
- Issue timestamp
- Revocation status (bool) + revocation timestamp
- Issuer whitelist status + trust tier

## What Must NOT Go On-Chain

- Student name, email, phone, address
- Full marksheet / grades detail
- Any government ID number
- KYC documents or their raw content
- Passwords or private keys

## Contract: IssuerRegistry + CredentialRegistry

Suggested combined contract (names are design suggestions, not mandatory):

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract CredentialPlatform {
    address public admin;

    struct Issuer {
        bool isApproved;
        uint8 trustTier;       // 1 = University, 2 = Company/NGO, 3 = Self-declared
        string institutionName;
        uint256 approvedOn;
    }

    struct Credential {
        address issuer;
        bytes32 documentHash;
        string ipfsCID;
        uint256 issuedOn;
        bool revoked;
        uint256 revokedOn;
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

    function issueCredential(bytes32 credentialId, bytes32 documentHash, string calldata ipfsCID) external onlyApprovedIssuer {
        require(credentials[credentialId].issuedOn == 0, "Credential already exists");
        credentials[credentialId] = Credential(msg.sender, documentHash, ipfsCID, block.timestamp, false, 0);
        emit CredentialIssued(credentialId, msg.sender, documentHash, block.timestamp);
    }

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

    function revokeCredential(bytes32 credentialId) external {
        Credential storage c = credentials[credentialId];
        require(c.issuedOn != 0, "Credential does not exist");
        require(c.issuer == msg.sender || msg.sender == admin, "Not authorized to revoke");
        require(!c.revoked, "Already revoked");
        c.revoked = true;
        c.revokedOn = block.timestamp;
        emit CredentialRevoked(credentialId, msg.sender, block.timestamp);
    }

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
```

## Access Control Summary

| Function | Who can call |
|---|---|
| `approveIssuer` / `revokeIssuer` | `admin` only |
| `issueCredential` / `batchIssueCredentials` | whitelisted issuer only |
| `revokeCredential` | the original issuer, or `admin` |
| `verifyCredential` / `isAuthorizedIssuer` | anyone (view functions, no gas for external calls) |

## Credential Lifecycle On-Chain

```
(no record) → issueCredential() → ACTIVE → revokeCredential() → REVOKED
```
There is no path back from REVOKED to ACTIVE — matches `CREDENTIAL_LIFECYCLE.md`.

## Transaction Handling & Gas Considerations

- Use `batchIssueCredentials` for bulk institutional uploads (e.g., a graduating class) to save gas versus one transaction per student.
- All admin/issuer write calls happen through the Django `blockchain` app using web3.py with the platform's or the issuer's signed transaction; the frontend does not submit privileged transactions directly except where the issuer explicitly signs via MetaMask (e.g., initial wallet-ownership proof during registration).
- Every write is logged in `BlockchainTransaction` (see `DATABASE_SCHEMA.md`) with status PENDING → CONFIRMED/FAILED, based on the transaction receipt.

## Network Configuration

- Development and primary demo: **Ganache** local blockchain (see `docs/LOCAL_DEVELOPMENT.md` for full setup) — configurable via `BLOCKCHAIN_RPC_URL` and `BLOCKCHAIN_CHAIN_ID` env vars
- Optional secondary demo: public testnet (Sepolia or Polygon Amoy), to show a real Etherscan-style block explorer link — same contract code, only the RPC URL/chain ID change
- Contract address stored in `CONTRACT_ADDRESS` env var, never hardcoded in application code
- The contract code itself is identical across Ganache, Hardhat's built-in network, and any public testnet — only the network configuration (`BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CHAIN_ID`) and the account used to deploy/sign transactions change

## Development Blockchain (Ganache)

For all local development and (recommended) the live demo, use Ganache instead of a public testnet — it is instant, free, and does not depend on internet/faucet availability during your presentation. Full setup steps are in `docs/LOCAL_DEVELOPMENT.md`. Nothing in the contract or in the Django/React integration code changes — only the RPC URL, chain ID, and which account signs transactions.

## Errors to Handle in the Backend Wrapper

- RPC timeout / node unreachable → surface as `502 BLOCKCHAIN_ERROR`
- Transaction reverted (e.g., not whitelisted) → surface as `403 FORBIDDEN` with the revert reason
- Nonce/gas estimation failures → retry once with updated gas parameters, then fail with `502`

## What Verification Actually Checks (mirrors PROJECT_OVERVIEW.md Section 4)

1. Credential exists on-chain (`issuedOn != 0`)
2. Provided/stored `documentHash` matches the on-chain hash
3. `issuer` address was whitelisted (checked historically via the `IssuerApproved` event or current `isApproved` state, per product decision — see `OPEN_QUESTIONS.md`)
4. `revoked` flag is false
5. Result mapped to: `VALID`, `REVOKED`, `INVALID` (hash mismatch), or `NOT_FOUND`
