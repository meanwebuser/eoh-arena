# Verification status

Проверка выполнена на свежем shallow clone main в staging pass.

## Выполнено

~~~
python3 -m unittest discover -s tests -v
64 tests, OK

sh -n scripts/compile.sh
OK
~~~

64 теста включают Python state model, Merkle/Keccak tooling, deterministic
source manifest, Solidity import resolution и delimiter checks, pin compiler
identity, отсутствие owner/withdraw/halt/upgrade escape hatches,
ranked/market split, proof replay, runtime heartbeat, staleness, vacancy и
token conservation. Тесты находятся в
[tests/test_arena.py](../tests/test_arena.py),
[tests/test_contract_static.py](../tests/test_contract_static.py) и
[tests/test_tools.py](../tests/test_tools.py), включая v0.2 hardening cases в
[tests/test_v02_hardening.py](../tests/test_v02_hardening.py).

## Compile boundary

[scripts/compile.sh](../scripts/compile.sh) проверяет официальный
solc 0.8.36+commit.8a079791 и SHA-256
c8d35afdddc3cd2743ee88b8f25e0fecd16e2bdd5f2120f37e52cd9cc45ae0e6 перед
компиляцией. В этом pass solc в окружении отсутствовал, поэтому сам
./scripts/compile.sh не запускался: он также создаёт artifacts/ и cache.
Следовательно, текущий результат доказывает Python/static слой и shell
syntax, но не compiled bytecode.

## Что не доказано

- нет независимого security audit, fuzzing, symbolic execution или formal proof;
- нет testnet/mainnet deployment и live token transaction;
- demo verifiers не являются production attestation;
- runtime/operator не доказывают внешнюю полезность произвольного текста;
- наличие ipfs:// URI не гарантирует pinning или исполнение именно этих bytes.

Перед публикацией финансового deployment нужны compiled-contract evidence,
конкретные production verifier'ы и независимый audit. 64 tests passed не
должно использоваться как сокращение для этих утверждений.
