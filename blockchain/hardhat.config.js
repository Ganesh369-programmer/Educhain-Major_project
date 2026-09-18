require("@nomicfoundation/hardhat-toolbox");

const adminPrivateKey = process.env.PLATFORM_ADMIN_PRIVATE_KEY;
const accounts = adminPrivateKey && adminPrivateKey.startsWith("0x") ? [adminPrivateKey] : undefined;

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.19",
  networks: {
    ganache: {
      url: process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:7545",
      chainId: 1337,
      ...(accounts ? { accounts } : {}),
    },
  },
};
