"""
ARKAINBRAIN — Web3 Output Generator (Phase 7)

Generates Solidity smart contracts, deployment scripts, and
frontend scaffolding for on-chain RMG games.

⚠️ IMPORTANT: Generated contracts are TEMPLATES requiring professional audit.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("arkainbrain.web3")


def generate_web3_output(game_type: str, config: dict, design: dict, output_dir: str) -> str:
    """Generate Web3 smart contract package.

    Returns path to the output directory.
    """
    od = Path(output_dir)
    od.mkdir(parents=True, exist_ok=True)

    title = design.get("title", "MiniGame")
    contract_name = "".join(w.capitalize() for w in title.split()[:3]) + "Game"
    contract_name = "".join(c for c in contract_name if c.isalnum())

    # 1. Solidity Contract
    sol = _generate_contract(game_type, config, contract_name)
    (od / f"{contract_name}.sol").write_text(sol, encoding="utf-8")

    # 2. Deployment Script (Hardhat)
    deploy = _generate_deploy_script(contract_name)
    (od / "deploy.js").write_text(deploy, encoding="utf-8")

    # 3. Hardhat Config
    hardhat = _generate_hardhat_config()
    (od / "hardhat.config.js").write_text(hardhat, encoding="utf-8")

    # 4. Frontend connector
    frontend = _generate_frontend_connector(contract_name, game_type)
    (od / "connector.js").write_text(frontend, encoding="utf-8")

    # 5. README with audit requirements
    readme = _generate_readme(contract_name, game_type, config)
    (od / "README.md").write_text(readme, encoding="utf-8")

    # 6. Package.json
    pkg = {
        "name": contract_name.lower(),
        "version": "0.1.0",
        "scripts": {
            "compile": "npx hardhat compile",
            "deploy:testnet": "npx hardhat run deploy.js --network sepolia",
            "deploy:mainnet": "npx hardhat run deploy.js --network mainnet",
        },
        "devDependencies": {
            "hardhat": "^2.19.0",
            "@nomicfoundation/hardhat-toolbox": "^4.0.0",
            "@chainlink/contracts": "^0.8.0",
        },
    }
    (od / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    logger.info(f"Generated Web3 package: {od}")
    return str(od)


def _generate_contract(game_type: str, config: dict, name: str) -> str:
    he = config.get("house_edge", 0.03)
    he_bps = int(he * 10000)  # basis points
    max_mult = int(config.get("max_multiplier", 1000))

    return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@chainlink/contracts/src/v0.8/vrf/VRFConsumerBaseV2.sol";
import "@chainlink/contracts/src/v0.8/interfaces/VRFCoordinatorV2Interface.sol";

/**
 * @title {name}
 * @notice On-chain {game_type} game with Chainlink VRF randomness
 *
 * ⚠️ TEMPLATE — NOT AUDITED ⚠️
 * This contract requires professional security audit before production use.
 * Known areas requiring review:
 *   - Reentrancy protection on payouts
 *   - VRF callback gas limits
 *   - House edge calculation overflow safety
 *   - Maximum bet limits relative to contract balance
 *   - Emergency withdrawal mechanisms
 */
contract {name} is VRFConsumerBaseV2 {{

    // ═══ STATE ═══
    VRFCoordinatorV2Interface immutable COORDINATOR;
    uint64 immutable s_subscriptionId;
    bytes32 immutable s_keyHash;

    address public owner;
    uint256 public houseEdgeBps = {he_bps}; // {he*100:.1f}% in basis points
    uint256 public maxMultiplier = {max_mult};
    uint256 public minBet = 0.001 ether;
    uint256 public maxBet = 1 ether;
    bool public paused = false;

    struct Bet {{
        address player;
        uint256 amount;
        uint256 targetMultiplier; // Player's cashout target (x100)
        bool settled;
    }}

    mapping(uint256 => Bet) public bets; // requestId => Bet
    mapping(address => uint256) public playerNonce;

    // ═══ EVENTS ═══
    event BetPlaced(address indexed player, uint256 requestId, uint256 amount, uint256 target);
    event BetSettled(address indexed player, uint256 requestId, uint256 multiplier, uint256 payout);
    event HouseEdgeUpdated(uint256 newEdgeBps);

    // ═══ MODIFIERS ═══
    modifier onlyOwner() {{ require(msg.sender == owner, "Not owner"); _; }}
    modifier whenNotPaused() {{ require(!paused, "Paused"); _; }}

    constructor(
        address _vrfCoordinator,
        uint64 _subscriptionId,
        bytes32 _keyHash
    ) VRFConsumerBaseV2(_vrfCoordinator) {{
        COORDINATOR = VRFCoordinatorV2Interface(_vrfCoordinator);
        s_subscriptionId = _subscriptionId;
        s_keyHash = _keyHash;
        owner = msg.sender;
    }}

    // ═══ GAMEPLAY ═══

    /**
     * @notice Place a bet with a target cashout multiplier
     * @param targetMultiplier Target multiplier x100 (e.g., 200 = 2.00x)
     */
    function placeBet(uint256 targetMultiplier) external payable whenNotPaused {{
        require(msg.value >= minBet && msg.value <= maxBet, "Bet out of range");
        require(targetMultiplier >= 101, "Min target 1.01x");
        require(targetMultiplier <= maxMultiplier * 100, "Exceeds max multiplier");

        // Ensure contract can cover max win
        uint256 maxPayout = (msg.value * targetMultiplier) / 100;
        require(address(this).balance >= maxPayout, "Insufficient house balance");

        uint256 requestId = COORDINATOR.requestRandomWords(
            s_keyHash, s_subscriptionId, 3, 200000, 1
        );

        bets[requestId] = Bet({{
            player: msg.sender,
            amount: msg.value,
            targetMultiplier: targetMultiplier,
            settled: false
        }});

        playerNonce[msg.sender]++;
        emit BetPlaced(msg.sender, requestId, msg.value, targetMultiplier);
    }}

    /**
     * @notice VRF callback — settles the bet
     */
    function fulfillRandomWords(uint256 requestId, uint256[] memory randomWords) internal override {{
        Bet storage bet = bets[requestId];
        require(!bet.settled && bet.player != address(0), "Invalid bet");
        bet.settled = true;

        // Generate crash/outcome point from random word
        uint256 rand = randomWords[0] % 10000;
        uint256 outcomeMultiplier;

        if (rand < houseEdgeBps) {{
            // Instant bust — house edge
            outcomeMultiplier = 0;
        }} else {{
            // Calculate outcome multiplier (simplified)
            // Full implementation depends on game type
            outcomeMultiplier = (10000 * 100) / (10000 - rand);
            if (outcomeMultiplier > maxMultiplier * 100) {{
                outcomeMultiplier = maxMultiplier * 100;
            }}
        }}

        uint256 payout = 0;
        if (outcomeMultiplier >= bet.targetMultiplier) {{
            payout = (bet.amount * bet.targetMultiplier) / 100;
            (bool sent, ) = bet.player.call{{value: payout}}("");
            require(sent, "Payout failed");
        }}

        emit BetSettled(bet.player, requestId, outcomeMultiplier, payout);
    }}

    // ═══ ADMIN ═══

    function setHouseEdge(uint256 _bps) external onlyOwner {{
        require(_bps <= 1000, "Max 10%");
        houseEdgeBps = _bps;
        emit HouseEdgeUpdated(_bps);
    }}

    function setBetLimits(uint256 _min, uint256 _max) external onlyOwner {{
        minBet = _min;
        maxBet = _max;
    }}

    function setPaused(bool _paused) external onlyOwner {{
        paused = _paused;
    }}

    function fundHouse() external payable onlyOwner {{}}

    function withdrawHouse(uint256 amount) external onlyOwner {{
        require(amount <= address(this).balance, "Insufficient");
        (bool sent, ) = owner.call{{value: amount}}("");
        require(sent, "Withdraw failed");
    }}

    function transferOwnership(address newOwner) external onlyOwner {{
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }}

    receive() external payable {{}}
}}
"""


def _generate_deploy_script(name: str) -> str:
    return f"""// Hardhat deployment script for {name}
const hre = require("hardhat");

async function main() {{
  // Chainlink VRF v2 addresses (Sepolia testnet)
  const VRF_COORDINATOR = "0x8103B0A8A00be2DDC778e6e7eaa21791Cd364625";
  const KEY_HASH = "0x474e34a077df58807dbe9c96d3c009b23b3c6d0cce433e59bbf5b34f823bc56c";
  const SUBSCRIPTION_ID = 0; // ← Replace with your Chainlink VRF subscription ID

  console.log("Deploying {name}...");

  const Game = await hre.ethers.getContractFactory("{name}");
  const game = await Game.deploy(VRF_COORDINATOR, SUBSCRIPTION_ID, KEY_HASH);
  await game.deployed();

  console.log(`{name} deployed to: ${{game.address}}`);
  console.log("\\n⚠️  Remember to:");
  console.log("  1. Fund the contract with ETH for house balance");
  console.log("  2. Add the contract as a VRF consumer in your Chainlink subscription");
  console.log("  3. Get a professional security audit before mainnet deployment");
}}

main().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
"""


def _generate_hardhat_config() -> str:
    return """require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.20",
  networks: {
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "https://rpc.sepolia.org",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
    mainnet: {
      url: process.env.MAINNET_RPC_URL || "",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY || "",
  },
};
"""


def _generate_frontend_connector(name: str, game_type: str) -> str:
    return f"""/**
 * Frontend connector for {name}
 * Uses ethers.js v6 + wagmi patterns
 *
 * ⚠️ TEMPLATE — adapt to your frontend framework
 */

// ABI will be generated after `npx hardhat compile`
// import ABI from './artifacts/contracts/{name}.sol/{name}.json';

const CONTRACT_ADDRESS = '0x...'; // ← Set after deployment

export class {name}Client {{
  constructor(signer) {{
    // this.contract = new ethers.Contract(CONTRACT_ADDRESS, ABI.abi, signer);
    this.signer = signer;
  }}

  async placeBet(amountEth, targetMultiplier) {{
    const tx = await this.contract.placeBet(
      Math.floor(targetMultiplier * 100),
      {{ value: ethers.parseEther(amountEth.toString()) }}
    );
    const receipt = await tx.wait();
    // Find BetPlaced event
    const event = receipt.logs.find(l => l.fragment?.name === 'BetPlaced');
    return {{ requestId: event?.args?.requestId, tx: receipt }};
  }}

  async getHouseEdge() {{
    const bps = await this.contract.houseEdgeBps();
    return Number(bps) / 10000;
  }}

  async getBalance() {{
    return ethers.formatEther(await this.signer.provider.getBalance(CONTRACT_ADDRESS));
  }}

  // Listen for bet settlement
  onBetSettled(callback) {{
    this.contract.on('BetSettled', (player, requestId, multiplier, payout) => {{
      callback({{
        player,
        requestId: requestId.toString(),
        multiplier: Number(multiplier) / 100,
        payout: ethers.formatEther(payout),
      }});
    }});
  }}
}}
"""


def _generate_readme(name: str, game_type: str, config: dict) -> str:
    he = config.get("house_edge", 0.03)
    return f"""# {name} — On-Chain {game_type.title()} Game

## ⚠️ SECURITY NOTICE

**These contracts are TEMPLATES and have NOT been professionally audited.**

Before deploying to mainnet with real funds:

1. **Hire a professional auditor** (e.g., Trail of Bits, OpenZeppelin, Certik)
2. **Run extensive testing** on testnet with edge cases
3. **Verify randomness** — Chainlink VRF subscription must be properly funded
4. **Check local regulations** — on-chain gambling may be restricted in your jurisdiction

## Configuration

- Game Type: {game_type}
- House Edge: {he*100:.1f}% ({int(he*10000)} basis points)
- Max Multiplier: {config.get('max_multiplier', 1000)}x
- Randomness: Chainlink VRF v2

## Setup

```bash
npm install
npx hardhat compile
```

## Deploy (Testnet)

```bash
export SEPOLIA_RPC_URL="https://..."
export PRIVATE_KEY="0x..."
npx hardhat run deploy.js --network sepolia
```

## Files

| File | Description |
|------|-------------|
| `{name}.sol` | Main game contract with VRF integration |
| `deploy.js` | Hardhat deployment script |
| `connector.js` | Frontend JavaScript connector |
| `hardhat.config.js` | Hardhat configuration |
| `package.json` | Node.js dependencies |

## Architecture

```
Player → placeBet(target) → Contract → requestRandomWords() → Chainlink VRF
                                                                    │
Player ← payout ← Contract ← fulfillRandomWords(result) ←─────────┘
```

## License

MIT — See contract header for details.
"""
