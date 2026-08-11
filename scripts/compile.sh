#!/usr/bin/env sh
set -eu

VERSION="0.8.36"
BUILD="8a079791"
EXPECTED_SHA256="c8d35afdddc3cd2743ee88b8f25e0fecd16e2bdd5f2120f37e52cd9cc45ae0e6"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CACHE="$ROOT/.cache"
PINNED_SOLC="$CACHE/solc-$VERSION"
SOLC=${SOLC_BIN:-$PINNED_SOLC}

mkdir -p "$CACHE" "$ROOT/artifacts"
if [ "$SOLC" = "$PINNED_SOLC" ]; then
  if [ ! -x "$SOLC" ]; then
    URL="https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v${VERSION}+commit.${BUILD}"
    echo "Downloading pinned Solidity compiler $VERSION..." >&2
    rm -f "$SOLC.tmp"
    curl -fL --retry 3 "$URL" -o "$SOLC.tmp"
    printf '%s  %s\n' "$EXPECTED_SHA256" "$SOLC.tmp" | sha256sum -c -
    mv "$SOLC.tmp" "$SOLC"
    chmod +x "$SOLC"
  fi
  printf '%s  %s\n' "$EXPECTED_SHA256" "$SOLC" | sha256sum -c -
fi

VERSION_TEXT=$("$SOLC" --version)
printf '%s\n' "$VERSION_TEXT"
printf '%s\n' "$VERSION_TEXT" | grep -F "Version: ${VERSION}+commit.${BUILD}" >/dev/null || {
  echo "Unexpected solc version; expected ${VERSION}+commit.${BUILD}" >&2
  exit 1
}

"$SOLC" \
  --base-path "$ROOT" \
  --include-path "$ROOT" \
  --optimize \
  --optimize-runs 200 \
  --via-ir \
  --abi \
  --bin \
  -o "$ROOT/artifacts" \
  --overwrite \
  "$ROOT/contracts/EohArena.sol" \
  "$ROOT/contracts/verifiers/MerkleJobAuthorizer.sol" \
  "$ROOT/contracts/verifiers/FixedCostHashVerifier.sol" \
  "$ROOT/contracts/verifiers/DemoRuntimeVerifier.sol" \
  "$ROOT/contracts/verifiers/DemoExpenseVerifier.sol" \
  "$ROOT/contracts/mocks/MockUSDC.sol"
