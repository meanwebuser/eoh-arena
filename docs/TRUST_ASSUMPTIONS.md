# Что именно значит «0 доверия»

## Не доверяем

- оператору версии;
- владельцу крупного капитала;
- участнику, создавшему тысячу Sybil-кошельков;
- buyer'у subjective market job;
- relayer'у;
- indexer'у;
- IPFS gateway;
- автору fork'а;
- локальному self-reporting агента.

Их заявления не меняют rank без проверки контракта и verifier'а.

## Доверяем как корням системы

### 1. EVM consensus

Контрактное состояние и порядок транзакций считаются каноническими в рамках выбранной сети.

### 2. Settlement token

Его `transfer/transferFrom`, decimals и policy считаются корректными. Fee-on-transfer и rebasing token не поддерживаются.

### 3. Ranked-job authorizer

Merkle root считается публичным неизменяемым расписанием допустимых задач. Генерация самого root должна быть воспроизводимой и опубликованной.

### 4. Work verifier

Он определяет объективность результата и ranked cost. Это главный прикладной trust root.

### 5. Runtime verifier

Он связывает source/image/provenance с runtime identity. Demo verifier из репозитория этого не обеспечивает.

### 6. Expense verifier

Он не даёт оператору превратить vault в свободный withdrawal. Production вариант должен проверять provider receipt или иную объективную аттестацию.

### 7. Availability

Хотя content digest позволяет проверить bytes, кто-то должен продолжать хранить source bundle, image и provenance. Собственные IPFS pins и независимые mirrors обязательны.

## Не доверяем indexer'у

Top-3 routing можно вычислять off-chain, но любой клиент обязан перепроверить:

```text
rankedRevenue
verifiedRankedCost
status
heartbeat
lineageId
```

непосредственно по событиям и состоянию контракта.

## Формула

```text
zero trust to participants
!=
zero assumptions about infrastructure
```

Правильное обещание протокола:

> Ни один участник не может победить только потому, что ему поверили.
> Каждая победа следует из состояния immutable contracts и заранее
> выбранных verifier'ов.
