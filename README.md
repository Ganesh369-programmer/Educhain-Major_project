# Blockchain-Based Academic Credential Verification and Career Platform

A platform where verified educational institutions issue tamper-proof digital academic credentials on a blockchain, students own and selectively share them, and recruiters instantly verify authenticity — with a built-in verified career/portfolio layer.

> For AI coding agents: read [`AGENTS.md`](./AGENTS.md) first. It is the authoritative project context.

## Features

- Institution registration with KYC-style document upload and admin approval before any issuance rights are granted
- On-chain issuer whitelist (smart-contract-enforced, not just a UI check)
- Single and bulk (batch) credential issuance
- Off-chain document storage (IPFS) + on-chain hash for tamper-evidence
- Student dashboard with shareable verification links and QR codes
- Public/recruiter verification portal (credential ID or QR scan)
- Credential revocation with on-chain status update
- Role-based access: Admin, Institution/Issuer, Student, Recruiter

## Architecture Overview

```
React (Tailwind) → Django REST API → SQLite
                        ↓
                 Blockchain Service (web3.py)
                        ↓
          Ethereum-compatible testnet ← Solidity contract
```

Full details: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

## Technology Stack

- **Frontend:** React.js, Tailwind CSS, ethers.js
- **Backend:** Django, Django REST Framework, web3.py
- **Database:** SQLite (dev)
- **Blockchain:** Ethereum-compatible testnet, Solidity, Hardhat
- **Auth:** JWT

## Repository Structure

```
project-root/
├── AGENTS.md
├── README.md
├── docs/                # full technical documentation (see below)
├── frontend/             # React app
├── backend/              # Django project
└── blockchain/           # Solidity contracts, Hardhat config, tests
```

## Documentation

| File | Purpose |
|---|---|
| `docs/PROJECT_OVERVIEW.md` | Goals, requirements, scope |
| `docs/ARCHITECTURE.md` | System + flow diagrams |
| `docs/DATABASE_SCHEMA.md` | Off-chain data model |
| `docs/API_SPECIFICATION.md` | REST API contract |
| `docs/BLOCKCHAIN_SPECIFICATION.md` | Smart contract design |
| `docs/AUTHENTICATION.md` | JWT auth flow |
| `docs/USER_ROLES_AND_PERMISSIONS.md` | Permission matrix |
| `docs/CREDENTIAL_LIFECYCLE.md` | Credential state machine |
| `docs/FRONTEND_GUIDELINES.md` | React conventions |
| `docs/BACKEND_GUIDELINES.md` | Django conventions |
| `docs/SECURITY.md` | Security requirements |
| `docs/DEVELOPMENT_RULES.md` | Rules for contributors/AI agents |
| `docs/FEATURE_ROADMAP.md` | Phased implementation plan |
| `docs/OPEN_QUESTIONS.md` | Unresolved decisions |

## Setup Overview

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate         # Windows
pip install -r requirements.txt
copy .env.example .env        # fill in values
python manage.py migrate
python manage.py runserver
```

### Frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

### Blockchain
```bash
cd blockchain
npm install
npx hardhat compile
npx hardhat test
npx hardhat run scripts/deploy.js --network sepolia
```

## Environment Variables

See `AGENTS.md` Section 13 for the full list. Never commit a real `.env` file — only `.env.example` with empty values.

## Testing

```bash
# backend
cd backend && pytest

# blockchain
cd blockchain && npx hardhat test

# frontend
cd frontend && npm test
```

## Status

Documentation-first phase — see `docs/FEATURE_ROADMAP.md` for the implementation order. Application code has not been written yet.
