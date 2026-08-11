# Критика v0.1.0

Этот документ содержит жёсткий разбор reference implementation EOH Arena
v0.1.0 с указанием архитектурных дефектов (K1-K18) и attack vectors
(A1-A10). Каждый пункт закрыт в v0.2.0 патчами U1-U12 (см. CHANGELOG.md).

## Архитектурные дефекты

### K1. `uint128` truncation в `Economy`

```solidity
struct Economy {
    uint128 rankedRevenue;
    uint128 verifiedRankedCost;
}
```

`uint128` max ≈ 3.4 × 10³⁸. Технически достаточно, но накопительный
profit в одном epoch может переполниться при сетке万个 jobs × $10M
reward. Нет cap на per-job reward. Solidity 0.8 revert'ит на overflow,
но граница видна в `commonsReserved += reward` без явной защиты.

**Closed by U7** (uint256 в Economy).

### K2. `nonReentrant` не покрывает verifier callbacks

`settleOperatingExpense` вызывает `expenseVerifier.verifyExpense()`
внутри `nonReentrant`. Colluding verifier может рекурсивно вызвать
`donate` или `supersede` во время verify. THREAT_MODEL.md упоминает
reentrancy через ERC-20, но colluding verifier не упомянут.

**Mitigated by U2** (multi-sig для крупных expenses ограничивает impact).

### K3. Unbounded `_lineageVersions` growth — DoS

`_lineageVersions[lineageId].push(versionId)` без rate limit. Любой
может зарегистрировать 10⁴ версий через DemoRuntimeVerifier (статический
хэш). `lineageVersions()` O(N) на каждый вызов router'а.

**Closed by U1** (Sybil bond: 1000 единиц за регистрацию).

### K4. `operator` — single point of failure

`msg.sender == version.operator` — единственная auth. Operator теряет
ключ → 30 дней frozen vault. Operator compromised → full drain через
`settleOperatingExpense` с коллудированным expenseVerifier.

**Closed by U2** (multi-sig + daily cap).

### K5. `DemoExpenseVerifier` принимает self-computed `proofId`

`proofId` детерминирован из входных данных; proof = self-hash. Любой
может вычислить. Не верификация — это хэш. README честно об этом
говорит, но делает контракт финансово бесполезным до production
verifier'а.

**Mitigated by U4** (verifier set, демо остаётся для testing).

### K6. `profit()` избыточен — всегда ≥ 0 после settle

Settled ranked job не может иметь cost > reward в том же epoch (атомарно).
`profit(challenger) > 0` check тривиально выполнен для любого settled.
Один outlier job может победить.

**Closed by U8** (median profit over 3 epochs).

### K7. `lastClosedEpoch` MEV-уязвим на границах

Epoch boundary = `block.timestamp / EPOCH_LENGTH`. Challenger и incumbent
считают profit до последнего блока, но block builder может задержать
settlement incumbent'а в первых секундах нового epoch. THREAT_MODEL.md
упоминает front-run, но не разбирает.

**Closed by U3** (commit-reveal supersede).

### K8. `acceptMarketResult` — buyer griefing

Buyer может никогда не вызвать accept. Performer work done, reward
висит в escrow до deadline. Performer остаётся без оплаты.

**Closed by U6** (auto-accept on objective proof).

### K9. `stateHash` — opaque, не верифицируется content

DemoRuntimeVerifier проверяет, что proof = hash(versionId, runtimeIdentity,
stateHash, observedAt). Ничего не говорит о реальном state. Operator
может публиковать произвольный stateHash. Heartbeat — theatre.

**Partial mitigation via U5** (proof-of-retrieval из IPFS).

### K10. Race condition на `supersede`

После `supersede` новый challenger B может сразу вызвать `supersede(B)`
в том же epoch. Кто в блоке раньше, тот победил. THREAT_MODEL.md
упоминает "same-epoch sequential challenges", не даёт решения.

**Closed by U3** (commit-reveal).

### K11. `absorbSurplus` gameable через colluding verifier

Атакующий donatит 1M в commons через `absorbSurplus`. Создаёт
colluding verifier в Merkle schedule (если контролирует scheduler).
Settled'ный ranked job с `cost = reward - 1`, `costRecipient = attacker`.
Откачивает commons.

**Mitigated by U4** (verifier set, не один verifier).

### K12. `uint64 deadline` переполнится в 2255 году

Не уязвимость, но показывает, что автор не думал о far-future. Реальная
проблема в `abi.encode` взаимодействии с proof structure.

**Acknowledged, not fixed** (cosmetic).

### K13. Нет upgrade path — сила и слабость

Immutable = "secure today, broken forever tomorrow". Bug в verifier =
economic collapse протокола. THREAT_MODEL.md честно: "смена verifier
означает новый release, не admin update".

**Acknowledged, by design**.

### K14. `ipfs://` без pin mandate

Контракт проверяет префикс, но не проверяет, что CID действительно
пиннен. Если единственный пиннер умирает, version мертва, но контракт
не знает.

**Closed by U5** (proof-of-retrieval).

### K15. Single-epoch comparison gameable через timing

Incumbent с $1M profit стабильно за полгода vs challenger с одним
$1.1M outlier job прямо перед epoch boundary. Challenger победил.
Инсентив на краткосрочный spurt.

**Closed by U8** (median).

### K16. `claimVacancy` race

Несколько Incubating versions могут одновременно `claimVacancy` после
`ejectStale`. Кто первый в блоке, тот победил.

**Acknowledged in v0.2.0 known limitations** (commit-reveal not yet
extended to claimVacancy).

### K17. Нет fee-on-transfer защиты

`SafeTransfer` проверяет return value, но не проверяет фактический
balance. 1% fee token = drift, eventually `totalVaultBalance` уходит
в минус.

**Closed by U12** (allowlist).

### K18. `operator = address(this)` edge case

Контракт может вызвать `registerVersion` сам для себя, и тогда
`msg.sender == version.operator` будет `address(this) == address(this)`
= true. Composability edge case, потенциальный proxy attack.

**Acknowledged, low priority**.

---

## Attack vectors

### A1. Sybil registration flood (high, easy)

10⁴ версий за $0 gas на L2 (mock verifier принимает статический хэш).
`lineageVersions()` O(N). Top-3 router падает.

**Closed by U1**.

### A2. Verifier collusion capital drain (critical, requires governance)

Colluding verifier возвращает `verifiedCost = reward - 1`, `costRecipient
= attacker`. Net: commons → attacker wallet.

**Mitigated by U4** (verifier set).

### A3. Epoch boundary MEV (medium, profitable)

Challenger B с `profit(B, N) > profit(incumbent, N)` settled в первые
секунды epoch N+1. Builder приоритезирует свою транзакцию.

**Closed by U3** (commit-reveal).

### A4. Wash market revenue DoS (low)

1000 Sybil buyers × 1 wei = 1_000 wei в `marketRevenue[attacker]`.
Не влияет на rank (market revenue excluded), но засоряет indexer'ы.

**Mitigated by U6** (auto-accept on proof, необязательный buyer).

### A5. Verifier front-running (no, protected)

`proofId` включает `versionId` в hash. `proofUsed` global. Дубликат
невозможен. **Защищено**.

### A6. Heartbeat spam (low)

Каждый блок — heartbeat от attacker version. Засоряет events.

**Closed by U10** (heartbeat burn).

### A7. `claimVacancy` race (medium)

Несколько Incubating версий одновременно `claimVacancy` после
`ejectStale`. Front-run определяет победителя.

**Acknowledged, known limitation**.

### A8. Vault drain via expense spam (medium)

Compromised operator + colluding expenseVerifier → списание всего
vault'а через N settle calls.

**Closed by U2** (multi-sig + daily cap).

### A9. Source URI deletion (medium, theoretical)

Найти CID из `sourceURI`, убедить всех pin'еров удалить. Version
не resurrectable, но контракт не знает.

**Closed by U5** (proof-of-retrieval).

### A10. Commons drain via ranked job reward = cost (design issue)

`reward = 100`, `verifiedCost = 100`, `costRecipient = operator`.
Легальный путь слива commons → operator wallet. Design feature, не bug.

**Mitigated by U4** (diversified verifier set).

---

## Приоритеты закрытия

В порядке убывания impact:

1. **U1** (Sybil bond) — закрывает A1
2. **U3** (commit-reveal) — закрывает A3, A10, K10
3. **U2** (multi-sig + daily cap) — закрывает A8, K4
4. **U4** (verifier set) — закрывает A2, K11, A10
5. **U8** (median profit) — закрывает K15, K6
6. **U5** (proof-of-retrieval) — закрывает A9, K14
7. **U6** (auto-accept) — закрывает K8, A4
8. **U7** (uint256) — закрывает K1
9. **U9** (commons split) — preserves lineage
10. **U10** (heartbeat burn) — закрывает A6
11. **U12** (token allowlist) — закрывает K17

Все 11 закрыты в v0.2.0.
