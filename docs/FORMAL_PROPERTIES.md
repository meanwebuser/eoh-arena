# Формальные свойства reference model

Обозначим для версии `V` и epoch `E`:

```text
D(V,E)  donations / capital in
M(V,E)  subjective market revenue
R(V,E)  ranked revenue from precommitted objective jobs
C(V,E)  ranked cost returned by the same work verifier
P(V,E)  R(V,E) - C(V,E)
B(V)    protocol-held vault balance
```

## I1. Donation independence

```text
P(V,E) не зависит от D(V,E)
```

Следствие: произвольный депозит не может увеличить rank.

## I2. Subjective-payment independence

```text
P(V,E) не зависит от M(V,E)
```

Следствие: self-payment через Sybil buyer не может увеличить rank.

## I3. Atomic ranked accounting

Для settled ranked job `J`:

```text
ΔR(winner,E) = J.reward
ΔC(winner,E) = verifier(J).verifiedCost
```

Оба изменения происходят либо вместе с provider payment, либо не происходят вовсе.

## I4. Replay exclusion

```text
used(authorizationId) <= 1
used(proofId) <= 1
```

## I5. Strict selection

Переход active version возможен только если:

```text
P(challenger,E) > 0
P(challenger,E) > P(incumbent,E)
```

Равенство не побеждает. Версия, которая лишь теряет меньше денег, но всё ещё убыточна, тоже не побеждает.

## I6. Capital inheritance

При успешном supersession:

```text
B'(incumbent) = 0
B'(challenger) = B(challenger) + B(incumbent)
```

В контракте отсутствует произвольный withdrawal, поэтому incumbent не имеет штатного пути обойти переход.

## I7. Epoch comparability

Challenge принимает только `lastClosedEpoch()`. Нельзя сравнить lifetime profit старой версии с одним днём новой или выбрать исторически удобное окно.

## I8. Stale commons return

После `STALE_AFTER` без положительной verified profit:

```text
B'(V) = 0
commons' = commons + B(V)
status'(V) = Stale
```

## I9. Live-runtime heartbeat

Обновление `lastHeartbeat` возможно только после принятия proof неизменяемым runtime verifier. Подпись оператора сама по себе недостаточна.

## I10. Conservation

В эталонной модели:

```text
totalMinted = wallets + vaults + commonsAvailable
             + commonsReserved + marketEscrowReserved
             + unaccountedSurplus
```

64 unit tests проверяют эти переходы, включая mixed-flow conservation
(42 из v0.1.0 + 22 из v0.2.0 hardening).

## v0.2.0 дополнительные инварианты

### I11. Sybil bond lock-up (U1)

```text
∀ V registered at epoch E_V:
  bond(V) > 0  iff  V registered but not yet refunded/slashed
  reclaimBond(V) requires R(V, E_V + 1) - C(V, E_V + 1) > 0
```

Следствие: регистрация N Sybil версий стоит N × `VERSION_BOND` единиц,
и bond'ы не возвращаются без объективно проверенной прибыли.

### I12. Daily expense cap (U2)

```text
∀ V, day D:
  Σ settledOperatingExpense(V, D) ≤ DAILY_EXPENSE_CAP
```

Крупные expenses (выше 10% от cap) дополнительно требуют multi-sig с
`operator_threshold` подписями из `operator_signers`.

### I13. Commit-reveal binding (U3)

```text
∀ commit C = keccak256(challengerId, epoch, salt):
  reveal(C) requires C.committedAt + COMMIT_PHASE_BLOCKS ≤ block.timestamp
  reveal(C) is one-shot (supersedeRevealed[C] = true after reveal)
```

Следствие: block builder не может front-run rival challengers, потому
что identity скрыта в commit window.

### I14. Verifier set diversity (U4)

```text
∀ ranked job J with verifier_set S:
  |S| ≥ 1, и verifier(S) = S[entropy(blockhash, J) % |S|]
```

Следствие: атакующий должен контролировать ≥51% verifier set'а для
collusion, а не одного verifier'а.

### I15. Proof-of-retrieval freshness (U5)

```text
∀ V live:
  lastIpfsProofTs(V) обновлён в последнем heartbeat с непустым ipfs_proof
```

Off-chain индексеры могут требовать `lastIpfsProofTs(V) ≥ now - HEARTBEAT_GRACE`
для routing eligibility.

### I16. Market job auto-accept (U6)

```text
∀ market job J with work_verifier_id ≠ ∅:
  objective_proof_valid(submit) ⇒ J.status → Accepted atomically
```

Buyer не может grief'ить через отказ от accept.

### I17. Median profit stability (U8)

```text
profitMedian(V, E) = median({profit(V, E-i) : i ∈ [0, PROFIT_WINDOW_EPOCHS)})
```

В commit-reveal supersede пути используется median, не single-epoch profit.
Один outlier epoch не может поднять версию в rank.

### I18. Stale capital lineage preservation (U9)

```text
∀ V stale with active Incubating successor S in same lineage:
  B'(V) = 0
  B'(S) = B(S) + floor(B(V) × STALE_LINEAGE_SHARE_NUM / STALE_LINEAGE_SHARE_DEN)
  commons' = commons + B(V) - lineage_share
```

Без successor:
```text
  commons' = commons + B(V)
```

### I19. Heartbeat burn (U10)

```text
∀ heartbeat from V:
  B'(V) = B(V) - HEARTBEAT_BURN
  commons' = commons + HEARTBEAT_BURN
```

Spam heartbeats стоят пропорционально `HEARTBEAT_BURN × frequency`.

### I20. Settlement token allowlist (U12)

```text
∀ token T used in constructor or donation:
  allowedSettlementTokens[T] = true
```

Произвольные fee-on-transfer или rebasing токены не могут пройти
через escrow.

## Не доказано

- корректность production verifier'ов;
- отсутствие Solidity implementation bugs (включая v0.2.0 patches);
- экономическая полезность выбранного benchmark schedule;
- невозможность external subsidy;
- liveness базовой EVM-сети;
- юридическое соблюдение AGPL;
- безопасность до независимого аудита/fuzzing/formal verification;
- что commit-reveal полностью закрывает MEV (нужен отдельный анализ
  builder-anchor attack, где builder включает свою собственную
  commit+reveal в одном блоке).
