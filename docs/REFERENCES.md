# Первичные технические источники

- Solidity compiler binaries: https://binaries.soliditylang.org/linux-amd64/list.json
- Solidity releases: https://github.com/argotorg/solidity/releases
- EIP-712 typed structured data: https://eips.ethereum.org/EIPS/eip-712
- ERC-1271 contract signatures: https://eips.ethereum.org/EIPS/eip-1271
- IPFS content addressing: https://docs.ipfs.tech/concepts/content-addressing/
- IPNS: https://docs.ipfs.tech/concepts/ipns/
- Trustless gateways: https://docs.ipfs.tech/reference/http/gateway/
- Sigstore cosign attestations: https://docs.sigstore.dev/cosign/verifying/attestation/
- in-toto attestations in cosign: https://docs.sigstore.dev/cosign/attestations/
- Ethereum Attestation Service docs: https://docs.attest.org/docs/welcome

EAS может быть удобным публичным mirror для metadata, но attestation остаётся утверждением. Security-critical source/runtime/work validation в core выполняют immutable verifier contracts.
