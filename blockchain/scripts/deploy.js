const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying CredentialPlatform with account:", deployer.address);

  const CredentialPlatform = await hre.ethers.getContractFactory("CredentialPlatform");
  const platform = await CredentialPlatform.deploy();

  await platform.waitForDeployment();

  const contractAddress = await platform.getAddress();
  console.log("CredentialPlatform deployed to:", contractAddress);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
