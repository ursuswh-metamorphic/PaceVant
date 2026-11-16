// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface Vm {
    function readFile(string calldata name) external view returns (string memory);
    function parseJsonAddress(string calldata json, string calldata key) external pure returns (address);
    function parseJsonBytes32(string calldata json, string calldata key) external pure returns (bytes32);
    function parseJsonBytes(string calldata json, string calldata key) external pure returns (bytes memory);
    function parseJsonString(string calldata json, string calldata key) external pure returns (string memory);
    function parseUint(string calldata value) external pure returns (uint256);
    function warp(uint256 timestamp) external;
    function chainId(uint256 newChainId) external;
    function etch(address target, bytes calldata code) external;
    function expectRevert(bytes4 selector) external;
}

// An integration harness for the wire format. Member B owns PolicyVault and actual swap execution.
contract ApprovalHarness {
    struct Approval {
        bytes32 policyHash;
        bytes32 evidenceRoot;
        address router;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        bytes32 calldataHash;
        uint256 nonce;
        uint256 deadline;
    }

    bytes32 private constant APPROVAL_TYPEHASH = keccak256(
        "Approval(bytes32 policyHash,bytes32 evidenceRoot,address router,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,bytes32 calldataHash,uint256 nonce,uint256 deadline)"
    );
    bytes32 private constant DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );

    error InvalidCalldata();
    error InvalidSigner();
    error Expired();
    error Replay();

    mapping(uint256 => bool) private used;

    function digest(Approval memory approval) public view returns (bytes32) {
        bytes32 separator = keccak256(abi.encode(
            DOMAIN_TYPEHASH, keccak256("TreasuryPolicyVault"), keccak256("1"),
            block.chainid, address(this)
        ));
        return keccak256(abi.encodePacked(
            hex"1901", separator, keccak256(abi.encode(APPROVAL_TYPEHASH, approval))
        ));
    }

    function consume(Approval memory approval, bytes calldata data, bytes calldata signature, address signer)
        external
    {
        if (block.timestamp >= approval.deadline) revert Expired();
        if (used[approval.nonce]) revert Replay();
        if (keccak256(data) != approval.calldataHash) revert InvalidCalldata();
        bytes32 r = bytes32(signature[0:32]);
        bytes32 s = bytes32(signature[32:64]);
        uint8 v = uint8(signature[64]);
        if (ecrecover(digest(approval), v, r, s) != signer) revert InvalidSigner();
        used[approval.nonce] = true;
    }
}

contract ApprovalGoldenTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    ApprovalHarness private harness;
    ApprovalHarness.Approval private approval;
    bytes private payload;
    bytes private signature;
    bytes32 private expectedDigest;
    address private signer;

    function setUp() public {
        string memory vector = vm.readFile("fixtures/eip712_golden/vector.json");
        address vault = vm.parseJsonAddress(vector, ".signed_pdr.domain.verifyingContract");
        ApprovalHarness template = new ApprovalHarness();
        vm.etch(vault, address(template).code);
        harness = ApprovalHarness(vault);
        vm.chainId(43113);
        vm.warp(2000000000);
        approval = ApprovalHarness.Approval({
            policyHash: vm.parseJsonBytes32(vector, ".signed_pdr.approval.policyHash"),
            evidenceRoot: vm.parseJsonBytes32(vector, ".signed_pdr.approval.evidenceRoot"),
            router: vm.parseJsonAddress(vector, ".signed_pdr.approval.router"),
            tokenIn: vm.parseJsonAddress(vector, ".signed_pdr.approval.tokenIn"),
            tokenOut: vm.parseJsonAddress(vector, ".signed_pdr.approval.tokenOut"),
            amountIn: vm.parseUint(vm.parseJsonString(vector, ".signed_pdr.approval.amountIn")),
            minAmountOut: vm.parseUint(vm.parseJsonString(vector, ".signed_pdr.approval.minAmountOut")),
            calldataHash: vm.parseJsonBytes32(vector, ".signed_pdr.approval.calldataHash"),
            nonce: vm.parseUint(vm.parseJsonString(vector, ".signed_pdr.approval.nonce")),
            deadline: vm.parseUint(vm.parseJsonString(vector, ".signed_pdr.approval.deadline"))
        });
        payload = vm.parseJsonBytes(vector, ".built_transaction.router_calldata");
        signature = vm.parseJsonBytes(vector, ".signed_pdr.signature");
        expectedDigest = vm.parseJsonBytes32(vector, ".signed_pdr.typed_data_hash");
        signer = vm.parseJsonAddress(vector, ".signer");
    }

    function testPythonDigestAndSignaturePassInSolidity() public {
        require(harness.digest(approval) == expectedDigest, "digest mismatch");
        require(keccak256(bytes(vm.readFile("fixtures/eip712_golden/manifest.jcs"))) == approval.evidenceRoot);
        harness.consume(approval, payload, signature, signer);
    }

    function testChangedCalldataRejected() public {
        bytes memory changed = payload;
        changed[0] = bytes1(uint8(changed[0]) ^ 1);
        vm.expectRevert(ApprovalHarness.InvalidCalldata.selector);
        harness.consume(approval, changed, signature, signer);
    }

    function testChangedAmountRejected() public {
        approval.amountIn += 1;
        vm.expectRevert(ApprovalHarness.InvalidSigner.selector);
        harness.consume(approval, payload, signature, signer);
    }

    function testWrongChainRejected() public {
        vm.chainId(43114);
        vm.expectRevert(ApprovalHarness.InvalidSigner.selector);
        harness.consume(approval, payload, signature, signer);
    }

    function testReplayRejected() public {
        harness.consume(approval, payload, signature, signer);
        vm.expectRevert(ApprovalHarness.Replay.selector);
        harness.consume(approval, payload, signature, signer);
    }

    function testExpiredRejected() public {
        vm.warp(approval.deadline);
        vm.expectRevert(ApprovalHarness.Expired.selector);
        harness.consume(approval, payload, signature, signer);
    }
}
