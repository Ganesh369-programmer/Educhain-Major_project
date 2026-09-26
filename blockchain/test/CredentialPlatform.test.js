const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("CredentialPlatform - Issuer Authorization", function () {
  let contract;
  let admin, issuer1, nonAdmin;

  beforeEach(async function () {
    [admin, issuer1, nonAdmin] = await ethers.getSigners();
    const CredentialPlatform = await ethers.getContractFactory("CredentialPlatform");
    contract = await CredentialPlatform.deploy();
    await contract.waitForDeployment();
  });

  it("sets deployer as platform admin", async function () {
    expect(await contract.admin()).to.equal(admin.address);
  });

  it("confirm a non-admin cannot call approveIssuer (must revert)", async function () {
    await expect(
      contract.connect(nonAdmin).approveIssuer(issuer1.address, "Test University", 1)
    ).to.be.revertedWith("Not platform admin");
  });

  it("confirm approveIssuer correctly whitelists an address", async function () {
    await expect(
      contract.connect(admin).approveIssuer(issuer1.address, "Test University", 1)
    )
      .to.emit(contract, "IssuerApproved");

    const issuer = await contract.issuers(issuer1.address);
    expect(issuer.isApproved).to.be.true;
    expect(issuer.trustTier).to.equal(1);
    expect(issuer.institutionName).to.equal("Test University");
  });

  it("confirm a whitelisted address passes isAuthorizedIssuer", async function () {
    expect(await contract.isAuthorizedIssuer(issuer1.address)).to.be.false;

    await contract.connect(admin).approveIssuer(issuer1.address, "Test University", 1);

    expect(await contract.isAuthorizedIssuer(issuer1.address)).to.be.true;
  });

  it("confirm a non-admin cannot call revokeIssuer (must revert)", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Test University", 1);

    await expect(
      contract.connect(nonAdmin).revokeIssuer(issuer1.address)
    ).to.be.revertedWith("Not platform admin");
  });

  it("confirm revokeIssuer removes access", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Test University", 1);
    expect(await contract.isAuthorizedIssuer(issuer1.address)).to.be.true;

    await expect(contract.connect(admin).revokeIssuer(issuer1.address))
      .to.emit(contract, "IssuerRevoked");

    expect(await contract.isAuthorizedIssuer(issuer1.address)).to.be.false;
  });
});

describe("CredentialPlatform - Credential Registry", function () {
  let contract;
  let admin, issuer1, issuer2, nonAdmin;

  const credentialId1 = ethers.keccak256(ethers.toUtf8Bytes("CRED-2026-001"));
  const docHash1 = ethers.keccak256(ethers.toUtf8Bytes("DocHash-Transcript-2026-001"));
  const ipfsCID1 = "QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco";

  beforeEach(async function () {
    [admin, issuer1, issuer2, nonAdmin] = await ethers.getSigners();
    const CredentialPlatform = await ethers.getContractFactory("CredentialPlatform");
    contract = await CredentialPlatform.deploy();
    await contract.waitForDeployment();
  });

  it("1. Negative case: a non-whitelisted address tries to call issueCredential — must revert", async function () {
    await expect(
      contract.connect(nonAdmin).issueCredential(credentialId1, docHash1, ipfsCID1)
    ).to.be.revertedWith("Issuer not whitelisted");
  });

  it("2. A whitelisted issuer successfully issues a credential", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);

    await expect(
      contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1)
    )
      .to.emit(contract, "CredentialIssued")
      .withArgs(credentialId1, issuer1.address, docHash1, (ts) => ts > 0n);

    const cred = await contract.credentials(credentialId1);
    expect(cred.issuer).to.equal(issuer1.address);
    expect(cred.documentHash).to.equal(docHash1);
    expect(cred.ipfsCID).to.equal(ipfsCID1);
    expect(cred.revoked).to.be.false;
    expect(cred.revokedOn).to.equal(0n);
    expect(cred.issuedOn).to.be.gt(0n);
  });

  it("3. Trying to issue a credentialId that already exists — must revert ('already exists')", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);
    await contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1);

    await expect(
      contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1)
    ).to.be.revertedWith("Credential already exists");
  });

  it("4. batchIssueCredentials issues multiple credentials in one transaction", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);

    const idA = ethers.keccak256(ethers.toUtf8Bytes("CRED-BATCH-001"));
    const idB = ethers.keccak256(ethers.toUtf8Bytes("CRED-BATCH-002"));
    const hashA = ethers.keccak256(ethers.toUtf8Bytes("DocHash-BATCH-001"));
    const hashB = ethers.keccak256(ethers.toUtf8Bytes("DocHash-BATCH-002"));
    const ipfsA = "QmBatchCID001";
    const ipfsB = "QmBatchCID002";

    const tx = await contract.connect(issuer1).batchIssueCredentials(
      [idA, idB],
      [hashA, hashB],
      [ipfsA, ipfsB]
    );

    await expect(tx)
      .to.emit(contract, "CredentialIssued")
      .withArgs(idA, issuer1.address, hashA, (ts) => ts > 0n);

    await expect(tx)
      .to.emit(contract, "CredentialIssued")
      .withArgs(idB, issuer1.address, hashB, (ts) => ts > 0n);

    const credA = await contract.credentials(idA);
    const credB = await contract.credentials(idB);
    expect(credA.issuer).to.equal(issuer1.address);
    expect(credB.issuer).to.equal(issuer1.address);
    expect(credA.documentHash).to.equal(hashA);
    expect(credB.documentHash).to.equal(hashB);
    expect(credA.ipfsCID).to.equal(ipfsA);
    expect(credB.ipfsCID).to.equal(ipfsB);
  });

  it("5. The original issuer can revoke their own credential", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);
    await contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1);

    await expect(contract.connect(issuer1).revokeCredential(credentialId1))
      .to.emit(contract, "CredentialRevoked")
      .withArgs(credentialId1, issuer1.address, (ts) => ts > 0n);

    const cred = await contract.credentials(credentialId1);
    expect(cred.revoked).to.be.true;
    expect(cred.revokedOn).to.be.gt(0n);
  });

  it("6. A different (non-owning, non-admin) address cannot revoke someone else's credential — must revert", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);
    await contract.connect(admin).approveIssuer(issuer2.address, "Global Academy", 2);
    await contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1);

    // Non-admin, non-issuer account
    await expect(
      contract.connect(nonAdmin).revokeCredential(credentialId1)
    ).to.be.revertedWith("Not authorized to revoke");

    // Another whitelisted issuer who is NOT the creator of this credential
    await expect(
      contract.connect(issuer2).revokeCredential(credentialId1)
    ).to.be.revertedWith("Not authorized to revoke");
  });

  it("7. Revoking an already-revoked credential — must revert", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);
    await contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1);

    // First revocation succeeds
    await contract.connect(issuer1).revokeCredential(credentialId1);

    // Second revocation by original issuer must revert
    await expect(
      contract.connect(issuer1).revokeCredential(credentialId1)
    ).to.be.revertedWith("Already revoked");

    // Even admin cannot revoke an already-revoked credential
    await expect(
      contract.connect(admin).revokeCredential(credentialId1)
    ).to.be.revertedWith("Already revoked");
  });

  it("8. verifyCredential returns correct data for an existing, non-existent, and revoked credential", async function () {
    await contract.connect(admin).approveIssuer(issuer1.address, "Apex Institute of Tech", 1);

    // 8a: Non-existent credential
    const nonExistentId = ethers.keccak256(ethers.toUtf8Bytes("NON-EXISTENT-CRED"));
    const [existsNone, revokedNone, issuerNone, hashNone, issuedOnNone] = await contract.verifyCredential(nonExistentId);
    expect(existsNone).to.be.false;
    expect(revokedNone).to.be.false;
    expect(issuerNone).to.equal(ethers.ZeroAddress);
    expect(hashNone).to.equal(ethers.ZeroHash);
    expect(issuedOnNone).to.equal(0n);

    // 8b: Existing active credential
    await contract.connect(issuer1).issueCredential(credentialId1, docHash1, ipfsCID1);
    const [existsActive, revokedActive, issuerActive, hashActive, issuedOnActive] = await contract.verifyCredential(credentialId1);
    expect(existsActive).to.be.true;
    expect(revokedActive).to.be.false;
    expect(issuerActive).to.equal(issuer1.address);
    expect(hashActive).to.equal(docHash1);
    expect(issuedOnActive).to.be.gt(0n);

    // 8c: Revoked credential
    await contract.connect(issuer1).revokeCredential(credentialId1);
    const [existsRevoked, revokedRevoked, issuerRevoked, hashRevoked, issuedOnRevoked] = await contract.verifyCredential(credentialId1);
    expect(existsRevoked).to.be.true;
    expect(revokedRevoked).to.be.true;
    expect(issuerRevoked).to.equal(issuer1.address);
    expect(hashRevoked).to.equal(docHash1);
    expect(issuedOnRevoked).to.equal(issuedOnActive);
  });
});

