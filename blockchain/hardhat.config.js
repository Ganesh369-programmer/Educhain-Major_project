require("@nomicfoundation/hardhat-toolbox");
const fs = require("fs");
const path = require("path");

// Load backend/.env if present
const envPath = path.resolve(__dirname, "../backend/.env");
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, "utf8");
  envContent.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith("#") && trimmed.includes("=")) {
      const idx = trimmed.indexOf("=");
      const key = trimmed.slice(0, idx).trim();
      const val = trimmed.slice(idx + 1).trim();
      if (!process.env[key]) {
        process.env[key] = val;
      }
    }
  });
}

const adminPrivateKey = process.env.PLATFORM_ADMIN_PRIVATE_KEY;
const accounts = adminPrivateKey && adminPrivateKey.startsWith("0x") ? [adminPrivateKey] : undefined;
const chainId = parseInt(process.env.BLOCKCHAIN_CHAIN_ID || "5777", 10);

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.19",
  networks: {
    ganache: {
      url: process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:7545",
      chainId: chainId,
      ...(accounts ? { accounts } : {}),
    },
  },
};

