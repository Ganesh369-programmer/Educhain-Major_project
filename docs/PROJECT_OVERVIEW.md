# Project Overview

## Purpose

Academic credential verification today is largely manual, paper-based, or dependent on a single centralized institutional record. This makes verification slow, and makes forgery/tampering hard to detect. This project builds a blockchain-based platform that issues tamper-evident digital credentials, gives students ownership and control over sharing them, and gives employers/institutions a fast, trustworthy way to verify authenticity — while also connecting verified credentials to career opportunities.

## Problem Statement

Traditional credential verification relies on manual, paper-based, or centralized processes that are slow, prone to forgery, and dependent on the issuing institution's availability, resulting in fraud risk and delayed verification turnaround.

## Proposed Solution

A platform where:
1. Institutions/organizations register and go through a verification (KYC) process before being allowed to issue credentials.
2. Approved issuers issue credentials whose document hash is recorded immutably on a blockchain.
3. Students hold their credentials in a personal dashboard and can generate shareable verification links/QR codes without exposing more than necessary.
4. Recruiters/employers verify a credential's authenticity in seconds, independent of the issuing institution's own uptime or cooperation.

## Objectives

- O1: Design and implement a blockchain-based system for issuing tamper-proof, verifiable digital academic credentials by authorized institutions.
- O2: Develop a secure student-owned digital credential dashboard enabling selective sharing of verified records.
- O3: Build an instant credential-verification interface for employers/verifiers that removes dependency on manual institutional confirmation.
- O4: Prevent unauthorized/fraudulent issuers from entering the system through a gated, whitelisted onboarding process.
- O5 (stretch): Integrate a career/job-matching layer linking verified credentials to recruiter-facing candidate profiles.

## Target Users / Roles

- **Admin** — platform operator; reviews and approves/rejects institutions; manages the on-chain issuer whitelist.
- **Institution / Issuer** — a college, university, or training organization that, once approved, issues and can revoke credentials.
- **Student** — receives, stores, and selectively shares credentials; builds a career profile.
- **Recruiter / Employer** — verifies credentials and views permitted parts of a candidate's career profile.

## Major Features

- Institution registration + document-based verification workflow
- Admin approval dashboard and on-chain issuer whitelisting
- Single and bulk (CSV-based) credential issuance
- Off-chain document storage (IPFS) with on-chain hash anchoring
- Credential revocation
- Student credential dashboard, shareable links, QR codes
- Public/recruiter verification portal
- Career profile aggregating verified credentials

## Functional Requirements

- Users can register and authenticate per role.
- Institutions can submit KYC documents for review.
- Admins can approve/reject institutions and manage issuer wallet whitelisting.
- Approved issuers can issue single or batch credentials.
- Students can view, share, and generate verification artifacts (link/QR) for their credentials.
- Anyone with a credential ID or QR code can verify a credential's authenticity and status.
- Issuers can revoke a credential they issued; revocation status is reflected on-chain and in verification results.

## Non-Functional Requirements

- **Security**: server-side authorization on every privileged action; no PII on-chain; secrets only in environment variables.
- **Performance**: verification response should be near-instant (seconds), independent of institution availability.
- **Usability**: role-appropriate dashboards; minimal steps for common actions (issue, verify, share).
- **Auditability**: every on-chain state change (issuance, revocation, whitelist change) is an emitted event and traceable.
- **Portability**: works across institutions rather than being tied to one national system.

## Technology Stack

React.js, Tailwind CSS, Django, Django REST Framework, SQLite, Solidity, Ethereum-compatible testnet, ethers.js, web3.py, JWT.

## System Boundaries

- This platform issues and verifies **credential records**, not the underlying academic evaluation itself (grading, exam conduct) — that remains the institution's responsibility.
- The platform is not a replacement for a national credential registry (e.g., DigiLocker/NAD); it is a complementary, issuer-agnostic verification layer for institutions/organizations outside or in addition to such systems.

## Assumptions

- Institutions have internet access and at least one staff member capable of using a web dashboard and a browser-based wallet (MetaMask) for the pilot phase.
- A testnet (not mainnet) is acceptable for the academic prototype; production gas-cost/network decisions are out of scope for this phase.
- KYC verification in the prototype is manual admin review plus basic automated format checks (e.g., GST/registration number pattern), not a live government API integration.

## Future Scope

- Zero-Knowledge Proof-based selective disclosure (e.g., prove CGPA ≥ X without revealing the full transcript).
- Multi-party attestation/co-signing for high-stakes credentials (e.g., internship certificates co-signed by a college TPO).
- Trust-tier system distinguishing UGC/AICTE-recognized institutions from other registered organizations.
- Decentralized Identifiers (DIDs) anchoring issuer identity to verifiable real-world documents.
- Full recruiter-facing job-matching module.
