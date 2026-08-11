# Протокол EOH Arena

Ниже описаны переходы, которые видны в текущем
[contracts/EohArena.sol](../contracts/EohArena.sol). Названия функций — это
не пожелания к будущему API, а текущие Solidity entrypoints.

## v0.2.0 hardening boundary

The v0.2.0 source adds hardening around registration, verifier choice,
supersession, market settlement, accounting and stale-capital handling. The
exact patch-by-patch semantics are maintained in
[CHANGELOG.md](../CHANGELOG.md) and the associated attacker assumptions in
[CRITIQUE.md](CRITIQUE.md); those documents take precedence over a shortened
description here. None of these controls turns the reference package into a
deployed, audited financial protocol.

## 1. Lineage и version

createLineage(declaration, runtimeProof, salt) создаёт lineage и сразу
делает root Active. registerVersion(...) требует существующий parent того же
lineage и создаёт Incubating version. В declaration проверяются:

- keccak256("AGPL-3.0-or-later");
- ненулевые source/image/provenance digest и runtime identity;
- непустой ipfs:// URI длиной не больше 256 bytes.

Обе операции вызывают immutable runtimeVerifier. versionId включает lineage,
parent, operator, digest'ы, runtime identity, hash URI и salt.

Heartbeat вызывается operator'ом live version и проверяет stateHash через
verifyHeartbeat. Contract использует HEARTBEAT_GRACE = 2 hours при isFresh;
наличие константы HEARTBEAT_PERIOD = 1 hour само по себе не создаёт
планировщик и не заставляет внешний процесс отправлять heartbeat.

## 2. Денежные buckets

donate переводит settlement token в vault live beneficiary и увеличивает
capitalIn. fundCommons пополняет commons. settleOperatingExpense — единственный
общий operator-requested выход из vault: operator передаёт expense proof,
immutable expense verifier возвращает уникальный proofId, после чего token
переводится recipient'у и proof помечается использованным. Отдельно
submitRankedResult может оплатить verifier-returned ranked cost. Обычного
withdraw нет.

Внутри arena учитываются commonsAvailable, commonsReserved,
marketEscrowReserved и totalVaultBalance. Незапрошенный прямой transfer не
относится к version; absorbSurplus зачисляет излишек только в commons.

## 3. Ranked schedule и settlement

createRankedJob проверяет reward/deadline и вызывает immutable
rankedJobAuthorizer. В стандартном MerkleJobAuthorizer authorization id —
Merkle leaf для (specHash, verifier, reward, deadline); каждая authorization
используется один раз. Проверка root не является проверкой результата.

submitRankedResult требует:

1. открытый job и неистёкший deadline;
2. live version с свежим heartbeat;
3. operator version;
4. IWorkVerifier.verify(...) == valid и новый proof id;
5. достаточный vault для returned verifiedCost.

После этого одна транзакция переводит cost recipient'у, reward из commons в
vault, и записывает reward/cost в текущий epoch. profit(version, epoch) —
разность этих двух полей. Отдельно заявить ranked cost или ranked revenue
нельзя.

## 4. Market jobs

openMarketJob резервирует buyer reward в escrow. Operator live beneficiary
публикует non-zero result через submitMarketResult; buyer решает принять его
через acceptMarketResult. После supersede исполнение/оплата может быть
направлена successor'у. Если deadline прошёл, buyer может вызвать
refundMarketJob.

Accepted market reward попадает в vault и marketRevenue, но не в _economy и
не в profit. Протокол не пытается определить, независимы ли buyer и
operator.

## 5. Selection

Для supersede(challengerId, epoch):

~~~
epoch == lastClosedEpoch()
challenger.status == Incubating
challenger heartbeat is fresh
challenger rankedRevenue > 0
challenger profit > 0
challenger profit > incumbent profit
~~~

Challenger и incumbent должны быть в одном lineage. Любой caller может
запустить переход; incumbent veto не нужен. При успехе vault incumbent
обнуляется и целиком добавляется challenger, statuses меняются на
Superseded/Active, а activeVersion[lineage] указывает на challenger.

TOP_ROUTING_COUNT = 3 — рекомендация для внешнего router; Python-модель
возвращает top-three через top_versions, но Solidity контракт не хранит
отдельный routing registry. Версии ниже top-three не получают автоматический
Stale status.

## 6. Staleness и vacancy

ejectStale применяет reference createdAt или последнюю положительную ranked
profit. После 30 дней без такой прибыли vault переводится в commons, status
становится Stale, а active pointer очищается, если он указывал на эту
version. Это изменение protocol state; оно не убивает внешний process.

После очистки active pointer incubating version с fresh heartbeat и
положительной ranked profit за last closed epoch может вызвать claimVacancy.
Контракт не содержит отдельного operator halt.

## 7. Что остаётся внешним

IRuntimeVerifier, IWorkVerifier, IExpenseVerifier, settlement token и Merkle
root — trust boundary deployment. DemoRuntimeVerifier,
DemoExpenseVerifier и FixedCostHashVerifier детерминированы для тестов и не
доказывают реальную TEE/zkVM execution, полезность результата или честный
provider bill. До независимого аудита и production verifier'ов этот пакет
нельзя трактовать как готовый финансовый deployment.
