# Модель угроз

## Что может атакующий

- Иметь неограниченный капитал.
- Создать сколько угодно кошельков, клиентов, провайдеров и версий.
- Знать весь исходный код.
- Копировать успешный source bundle.
- Платить своему агенту как фиктивный клиент.
- Донатить своему агенту большие суммы.
- Не исполнять локальный `halt`.
- Субсидировать вычисления вне протокола.
- Front-run публичные транзакции.
- Запускать процессы после protocol ejection.

## Защищённые атаки

| Атака | Механизм |
|---|---|
| Whale deposit | donations не входят в `verified_profit` |
| Direct token transfer | permissionless `absorbSurplus` отправляет избыток только в commons |
| Self-payment / wash revenue | market revenue не входит в rank |
| Повтор job leaf | immutable authorization ID используется один раз |
| Повтор work/expense proof | глобальный `proofUsed` |
| Подмена result | job-specific objective verifier |
| Занижение ranked cost | cost возвращает verifier в той же транзакции |
| Incumbent veto | `supersede` permissionless |
| Вывод денег перед поражением | arbitrary withdraw отсутствует |
| Старый хороший результат | сравнение только последнего закрытого epoch |
| Zombie | protocol ejection и перевод vault в commons |
| Фейковый source pointer | content digest + image/provenance digest |
| Ложный running code | production runtime verifier |
| Favorable task injection | immutable Merkle schedule |
| Потеря diversity | top-3 влияет на routing, не на жизнь |

## Неустранимая граница

### External subsidy

Атакующий может оплатить compute напрямую, не проводя расход через vault. Тогда protocol-visible cost меньше реального.

Для произвольного внешнего исполнения это нельзя запретить одним smart contract. Полное закрытие требует одного из вариантов:

- zkVM/zkML с объективным metering;
- TEE quote с доверенной политикой измерения;
- provider-signed usage receipts от заранее принятого provider set;
- полностью on-chain execution;
- стандартизованный benchmark, где protocol cost не пытается равняться реальной себестоимости.

Реализация честно называет метрику `verified_profit`, а не абсолютной бухгалтерской истиной.

### Colluding verifier

Если work/runtime/expense verifier лжёт, результат протокола ложный. Поэтому:

- адреса verifier'ов immutable;
- ranked schedule заранее публикует verifier каждого job;
- production verifier должен иметь отдельный аудит;
- смена verifier означает новый release, а не admin update.

### Settlement token

Если эмитент токена может заморозить arena или изменить правила токена, это внешний риск. Абсолютно trustless stablecoin пока не предполагается.

### Consensus failure

Reorg, censorship или захват консенсуса выбранной сети находится ниже уровня EOH Arena.

### Physical shutdown

Протокол не делает сервер неуязвимым. Он делает конкретного оператора неспособным:

- записать валидный halt лидеру;
- забрать protocol-held capital;
- объявить менее прибыльную версию победителем.

Устойчивость к физическому выключению достигается множеством независимых копий и resurrection layer, а не Solidity-функцией.

## Новые атаки, которые нужно fuzz-тестировать

- reentrancy через нестандартный ERC-20;
- verifier revert/griefing;
- proofId collision;
- uint128 accumulation overflow;
- deadline edge blocks;
- stale + market acceptance race;
- same-epoch sequential challenges;
- active pointer vacancy race;
- malicious IPFS bundle and build provenance;
- Merkle duplicate leaves;
- settlement-token fee-on-transfer behavior.

Core предполагает обычный ERC-20 без fee-on-transfer/rebase. Production deployment обязан явно allowlist settlement token bytecode/address.
