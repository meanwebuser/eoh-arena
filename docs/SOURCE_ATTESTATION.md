# Open source и доказательство исполняемого кода

## Четыре разных утверждения

Нельзя смешивать:

1. **Bytes exist** — bundle доступен по CID.
2. **Bytes are source** — manifest описывает дерево файлов.
3. **Artifact was built from source** — provenance связывает source digest и image digest.
4. **Runtime executes artifact** — attestation связывает image digest и runtime identity.

IPFS решает только первое и помогает второму. Git commit signature или maintainer signature не доказывает третье и четвёртое.

## Version declaration

```text
sourceURI          ipfs://CID source bundle
sourceDigest       hash детерминированного file manifest
imageDigest        digest воспроизводимого OCI image/binary
provenanceDigest   hash in-toto/SLSA-style provenance
runtimeIdentity    enclave/zkVM/runtime identity
parentId           родитель fork'а
```

Все значения входят в `versionId`.

## Reproducible build

Рекомендуемый pipeline:

1. checkout exact source digest;
2. isolated build без сетевого доступа;
3. pin compiler/toolchain images by digest;
4. build twice независимыми runners;
5. сравнить artifact digest;
6. создать provenance statement;
7. подписать/поместить statement в transparency log;
8. опубликовать source, image и provenance в независимых content-addressed stores.

## Runtime

Production `IRuntimeVerifier` проверяет регистрацию и каждый heartbeat. Он может проверять:

- TEE quote, measurement и policy;
- zkVM proof выполнения loader'а;
- remote-attested container host;
- другой объективный proof, согласованный protocol release.

`DemoRuntimeVerifier.sol` только проверяет формат хэша и не является security control.

## Почему maintainer attestation недостаточна

Maintainer может подписать ложное утверждение «этот сервер исполняет этот image». Подпись докажет автора заявления, но не истинность заявления.

Подпись полезна для provenance/authorship, но runtime equality требует измерения среды.

## License

Arena требует hash `AGPL-3.0-or-later` как protocol rule и source URI. Это делает открытость явной и индексируемой.

Однако smart contract не может автоматически доказать, что опубликованный bundle полный и что юридические требования AGPL соблюдены. Для этого нужны reproducible build, аудит и правоприменение.

## Live heartbeat

Однократной attestation при регистрации недостаточно: после неё оператор мог бы заменить процесс. Поэтому heartbeat содержит `versionId`, `runtimeIdentity`, `stateHash` и точное on-chain время, а immutable runtime verifier обязан подтвердить свежую runtime quote/proof. Demo verifier проверяет лишь детерминированный хэш и не даёт такой гарантии.
