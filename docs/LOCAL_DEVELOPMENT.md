# Local Development (Ganache)

## Why Ganache

Ganache is a personal, local Ethereum-compatible blockchain that runs entirely on your own machine. It is used for all development and testing, and is the **recommended network for the live project demo**, because:

- No internet dependency during your presentation (a public testnet or faucet outage cannot break your demo)
- Instant transaction confirmation (no waiting for block times)
- 10 pre-funded test accounts (100 fake ETH each) with no faucet needed
- A GUI where you can watch every transaction/block/account balance live while your app runs — good for showing your teacher what's happening on-chain in real time

The smart contract code is identical whether it's deployed to Ganache, Hardhat's built-in network, or a public testnet. Only network configuration changes.

## 1. Install and Run Ganache

**Option A — GUI app:** download Ganache from the official Truffle Suite site, install, and launch it. It starts a workspace automatically on `http://127.0.0.1:7545` (default port) and shows 10 accounts with their addresses, balances, and private keys.

**Option B — CLI:**
```bash
npm install -g ganache
ganache
```
This starts the same local chain from the terminal, default RPC at `http://127.0.0.1:8545`.

Note the RPC URL and Chain ID shown (GUI default chain ID is `1337`; CLI default is `1337` as well unless configured otherwise) — you will need both.

## 2. Point Hardhat at Ganache

In `blockchain/hardhat.config.js`:
```js
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: "0.8.19",
  networks: {
    ganache: {
      url: "http://127.0.0.1:7545",   // match whatever Ganache shows you
      chainId: 1337,
      accounts: [
        // paste a private key from one of Ganache's 10 test accounts
        "0xYOUR_GANACHE_ACCOUNT_PRIVATE_KEY"
      ]
    }
  }
};
```

## 3. Deploy the Contract to Ganache

```bash
cd blockchain
npx hardhat compile
npx hardhat run scripts/deploy.js --network ganache
```
This prints the deployed contract address — copy it.

## 4. Update Backend `.env`

```
BLOCKCHAIN_RPC_URL=http://127.0.0.1:7545
BLOCKCHAIN_CHAIN_ID=1337
CONTRACT_ADDRESS=<address printed by the deploy script>
PLATFORM_ADMIN_PRIVATE_KEY=<the same Ganache account private key used to deploy, if it is the account that should hold the admin role>
```

Nothing else in the Django `blockchain` app wrapper needs to change — web3.py talks to whatever `BLOCKCHAIN_RPC_URL` points to.

## 5. Connect MetaMask to Ganache (for frontend testing)

1. Open MetaMask → Networks → **Add a custom network**
 - Network Name: `Ganache Local`
 - RPC URL: `http://127.0.0.1:7545`
 - Chain ID: `1337`
 - Currency symbol: `ETH`
2. Import a test account: MetaMask → Import Account → paste one of Ganache's private keys. That account now shows 100 fake ETH and can sign transactions on your local chain (e.g., an institution proving wallet ownership during registration).

## 6. Important: Ganache State Resets

Every time Ganache is closed and restarted (without using "Save Workspace" / a persistent `--db` folder), the entire local chain — deployed contracts, issued credentials, account balances — is wiped. Plan for this:

- **Use Ganache's "Save Workspace" option** (GUI) or run the CLI with a `--db ./ganache-data` flag to persist state across restarts, **or**
- **Write a seed script** (`blockchain/scripts/seed.js` + a matching Django management command) that redeploys the contract and recreates a couple of demo institutions/credentials automatically — this is genuinely useful to have regardless, since it guarantees a clean, reliable demo state right before your presentation instead of depending on leftover data from a previous session.

## 7. Optional: Also Deploy to a Public Testnet

If you want to additionally show a real Etherscan-style explorer link as a bonus for your teacher:

```bash
npx hardhat run scripts/deploy.js --network sepolia
```
with a `sepolia` network entry in `hardhat.config.js` pointing to an Infura/Alchemy RPC URL and a funded testnet account. This is optional and should not be depended on for the live demo — use it only as a "here's the same thing on a real public network" supplementary screenshot/link.

## Summary: What Changes Between Ganache and a Public Testnet

| | Changes | Stays the same |
|---|---|---|
| Ganache → Sepolia | `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CHAIN_ID`, which account signs transactions, transaction speed | Contract code, Django `blockchain` app wrapper, React/ethers.js integration code, API contract |
