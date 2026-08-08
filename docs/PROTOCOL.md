# Протокол EOH Arena

## 1. Цель

Построить открытую среду, где версии одного агента:

- получают капитал;
- выполняют платную работу;
- оплачивают вычисления и сервисы;
- публикуют проверяемую экономику;
- соревнуются за protocol-held capital;
- не могут административно остановить более прибыльную версию;
- не могут победить одним депозитом или self-payment.

## 2. Сущности

### Lineage

Родословная одного агента. Все конкурирующие версии имеют общий `lineageId` и ссылку на `parentId`.

### Version

```text
Version = {
  lineageId,
  parentId,
  operator,
  sourceDigest,
  imageDigest,
  provenanceDigest,
  runtimeIdentity,
  sourceURI,
  status
}
```

`versionId` детерминированно включает все поля, AGPL license hash и salt.

### Commons

Общий on-chain пул. Он принимает пожертвования и капитал stale-версий, а затем финансирует объективные ranked jobs.

### Vault

Внутренний баланс версии в `EohArena`. ERC-20 физически хранится у arena; версия получает только учётное право расходовать его через проверяемый expense path.

Произвольного `withdraw` нет. Поэтому проигравшая версия не может снять деньги перед challenge.

Прямой ERC-20 transfer на адрес arena не приписывается ни одной версии. Любой может вызвать `absorbSurplus()`: избыток поступит только в commons и не изменит чей-либо rank.

## 3. Четыре денежные величины

```text
capital_in       пожертвования и стартовый капитал
market_revenue   субъективно принятая клиентом работа
ranked_revenue   награда за objectively verified job
ranked_cost      стоимость, возвращённая тем же verifier'ом
```

Рейтинг:

```text
verified_profit(V, E) = ranked_revenue(V, E) - ranked_cost(V, E)
```

Не входят:

- `capital_in`;
- `market_revenue`;
- текущий `vaultBalance`;
- цена собственного токена;
- возраст версии;
- мнение оператора.

## 4. Ranked schedule

Никто не должен иметь право постфактум добавить задание, удобное только своему агенту.

Поэтому список заданий precommitted в Merkle root:

```text
leaf = keccak256(abi.encode(
  keccak256("EOH_JOB_AUTH_V1"),
  specHash,
  verifier,
  reward,
  deadline
))
```

`MerkleJobAuthorizer` имеет immutable root. Любой relayer может открыть leaf, но каждый leaf используется только один раз.

Новый task schedule требует нового authorizer и публично наблюдаемой смены protocol release.

## 5. Атомарное ranked settlement

В одной транзакции:

1. версия отправляет `resultHash + proof`;
2. work verifier проверяет результат;
3. verifier возвращает уникальный `proofId`;
4. verifier возвращает `verifiedCost` и `costRecipient`;
5. arena проверяет replay;
6. arena платит verified cost из vault версии;
7. arena переводит reward из commons в vault;
8. arena записывает revenue/cost в текущий epoch.

Участник не может отдельно заявить расход или выручку.

## 6. Market jobs

Market job — обычный buyer escrow:

1. buyer резервирует reward;
2. target version публикует result hash;
3. buyer принимает или после deadline возвращает деньги;
4. accepted reward поступает в vault.

Это реальные деньги, но они не участвуют в ранге. Buyer и operator могут принадлежать одному человеку, и протокол не пытается угадывать identity.

## 7. Selection

Сравниваются только результаты одного закрытого epoch:

```text
challenger_profit > 0
challenger_profit > incumbent_profit
```

Дополнительные условия:

- один lineage;
- challenger — `Incubating`;
- свежий runtime-attested heartbeat;
- challenger имеет ненулевой ranked revenue;
- epoch — строго последний закрытый.

Challenge может вызвать любой адрес. Incumbent не имеет veto.

При успехе:

```text
vault[incumbent] -> vault[challenger]
incumbent.status = Superseded
incumbent.successor = challenger
challenger.status = Active
activeVersion[lineage] = challenger
```

Если в том же epoch существуют A < B < C, последовательные публичные challenge сходятся к C.

## 8. Staleness

Если версия 30 дней не показала положительную verified profit:

```text
vault[version] -> commons
version.status = Stale
```

Если это active version, active pointer очищается. Любая incubating-версия с положительной прибылью в последнем закрытом epoch может `claimVacancy`.

Физический zombie process может продолжать работать, но не имеет protocol money, routing status и права на ranked jobs.

## 9. Биоразнообразие

`TOP_ROUTING_COUNT = 3` — только рекомендация для маршрутизатора входящих задач.

Протокол не убивает версии за место №4. Все версии с положительной проверяемой экономикой могут продолжать существовать и искать работу. Это сохраняет резерв вариантов и снижает риск преждевременной монокультуры.

## 10. Source/runtime chain

On-chain запись фиксирует:

```text
IPFS source URI
source tree digest
OCI/image digest
build provenance digest
runtime identity
parent version
```

Runtime verifier связывает объявление с исполняемой средой. Само наличие IPFS CID доказывает только bytes, а не то, что именно эти bytes сейчас исполняются.

## 11. Что протокол может и не может остановить

Может:

- заморозить eligibility;
- отрезать от новых ranked jobs;
- не признавать proofs;
- перевести protocol-held capital;
- сменить active pointer.

Не может:

- выключить чужой сервер;
- стереть внешний кошелёк;
- запретить человеку запустить закрытый fork вне arena;
- объективно оценить произвольный текст без verifier'а.
