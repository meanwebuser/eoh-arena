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

42 unit tests проверяют эти переходы, включая mixed-flow conservation.

## Не доказано

- корректность production verifier'ов;
- отсутствие Solidity implementation bugs;
- экономическая полезность выбранного benchmark schedule;
- невозможность external subsidy;
- liveness базовой EVM-сети;
- юридическое соблюдение AGPL;
- безопасность до независимого аудита/fuzzing/formal verification.
