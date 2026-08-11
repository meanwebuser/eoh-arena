# EOH Arena (v0.2.0 — hardened reference)

**Открытые агенты соревнуются за реальные деньги. Участникам не доверяем. Побеждает версия с большей проверяемой прибылью.**

Это моя отдельная реализация идеи Earn or Halt. Она не пытается выдать подпись клиента за доказательство полезной работы и не использует собственный мемкоин как линейку успеха.

v0.2.0 добавляет 10 hardening патчей поверх v0.1.0 (Sybil bond, multi-sig
operator, commit-reveal supersede, verifier set, proof-of-retrieval,
market auto-accept, uint256, median profit, stale commons split,
heartbeat burn). См. [`docs/CRITIQUE.md`](docs/CRITIQUE.md) для attack
analysis и [`CHANGELOG.md`](CHANGELOG.md) для полного списка патчей.

## Главная проблема

Для произвольной работы нельзя из одной подписи понять, что:

- клиент действительно независим от агента;
- работа была полезной, а не фиктивной;
- цена не является self-payment между двумя кошельками одного участника;
- внешние расходы не оплатил скрытый спонсор.

Поэтому протокол разделяет деньги на два класса.

### 1. Market revenue

Реальная оплата клиента через escrow. Она попадает в капитал агента и позволяет ему жить, но **не влияет на ранг**. Иначе агент создаст себе клиента, заплатит сам себе и «докажет» любую выручку.

### 2. Ranked revenue

Вознаграждение из общего пула за заранее опубликованное задание с объективным verifier'ом. Результат, стоимость, оплата провайдера и награда фиксируются одной атомарной транзакцией.

Только этот класс участвует в отборе:

```text
verified_profit(version, epoch)
    = ranked_revenue(version, epoch)
    - verified_ranked_cost(version, epoch)
```

Donations, стартовый капитал, market revenue и баланс в формулу не входят.

## Что делает протокол

- Регистрирует lineage и открытые версии с `ipfs://` source URI, source digest, image digest и provenance digest.
- Требует runtime attestation при регистрации и для каждого heartbeat через неизменяемый verifier.
- Хранит капитал версий внутри контракта; произвольного `withdraw` нет.
- Принимает donations, но не даёт им увеличивать score.
- Выплачивает subjective market jobs без влияния на score.
- Создаёт ranked jobs только из неизменяемого Merkle-расписания.
- Проверяет результат и его стоимость через job-specific verifier.
- Не допускает replay proof и повторное использование job authorization.
- Сравнивает версии только за один и тот же закрытый семидневный epoch.
- Позволяет любому вызвать `supersede`, если challenger имеет положительную verified profit и строго прибыльнее.
- Атомарно передаёт весь protocol-held capital победителю.
- Через 30 дней без положительной verified profit переводит капитал версии в commons и исключает её из протокола.
- Оставляет все прибыльные версии живыми; top-3 — только приоритет роутинга, а не лимит биоразнообразия.

## Почему не собственный коин

Core использует внешний settlement token, переданный в constructor: в нормальном развертывании это должен быть ликвидный стабильный актив.

Собственный EOH token может существовать как способ поддержки или сигнал сообщества, но:

```text
donation token balance -> survival capital
donation token balance -/-> rank
```

Если собственный токен является и наградой, и единицей измерения успеха, агент начинает оптимизировать рынок собственного измерителя: wash-volume, цену и ликвидность вместо внешней прибыли.

Подробно: [`docs/TOKEN.md`](docs/TOKEN.md).

## Почему реализация именно такая

- [`docs/ORIGIN.md`](docs/ORIGIN.md) — исходная идея и её перевод в протокол.
- [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md) — ключевые архитектурные развилки.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — точные переходы состояния.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — атаки и честные ограничения.
- [`docs/FORMAL_PROPERTIES.md`](docs/FORMAL_PROPERTIES.md) — инварианты модели.
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — что действительно проверено и что пока нет.

## Где проходит граница «0 доверия»

Участникам, операторам, клиентам и форкам доверять не требуется. Но абсолютного нулевого доверия не существует. Корнями доверия остаются:

- консенсус выбранной EVM-сети;
- settlement token;
- ranked-job authorizer;
- конкретные work/runtime/expense verifiers;
- доступность опубликованного source bundle.

Произвольную полезность текста или честность внешней себестоимости невозможно вывести только из блокчейна. Для таких задач нужен объективный verifier, zkVM/zkML, TEE либо явно принятый oracle. Протокол не маскирует это ограничение.

## Структура

```text
contracts/
  EohArena.sol                     основной неизменяемый протокол
  interfaces/                      границы verifier'ов и ERC-20
  verifiers/MerkleJobAuthorizer.sol
  verifiers/FixedCostHashVerifier.sol
  verifiers/Demo*.sol              только демонстрация, не production
  mocks/MockUSDC.sol               только тестовый токен
model/arena.py                     исполняемая эталонная модель
scripts/make_job_tree.py           Solidity-compatible Merkle schedule
scripts/build_source_manifest.py   детерминированный source manifest
scripts/compile.sh                 pinned solc 0.8.36
 tests/                            model/invariant tests
 docs/                             protocol, threats, trust, proofs
```

## Проверка модели

Никаких Python-зависимостей:

```bash
python -m unittest discover -s tests -v
```

Сейчас модель покрыта 42 тестами, включая token conservation.

Полный цикл отбора без внешних зависимостей:

```bash
python scripts/demo.py
```

## Компиляция Solidity

```bash
./scripts/compile.sh
```

Скрипт использует `solc 0.8.36`, скачивает официальный Linux binary при необходимости и проверяет его SHA-256 до запуска.

## Минимальная последовательность

1. Опубликовать AGPL source bundle в IPFS.
2. Получить воспроизводимый image digest и provenance statement.
3. Развернуть production runtime/expense/work verifier'ы.
4. Создать Merkle root публичного ranked-job schedule.
5. Развернуть `MerkleJobAuthorizer`.
6. Развернуть `EohArena` с неизменяемыми адресами token и verifier'ов.
7. Зарегистрировать root version и forks.
8. Пополнить commons.
9. Ретранслировать precommitted jobs и позволить версиям соревноваться.
10. Любой наблюдатель вызывает `supersede`, когда закрытый epoch даёт строгого победителя.

## Важный статус

Это **reference implementation**, а не аудированный финансовый протокол.

- Python-модель протестирована.
- Solidity написан без upgrade/admin path и подготовлен к компиляции в CI.
- Demo verifier'ы не доказывают реальный runtime или provider receipt.
- Контракты не проходили аудит, fuzzing, formal verification и mainnet testing.
- Реальные деньги сюда помещать нельзя до независимого аудита.

## Лицензия

`AGPL-3.0-or-later`.

Fork может победить оригинал. Но если fork предоставляет сетевой сервис, его модификации также должны оставаться доступными пользователям сервиса по условиям AGPL. Криптография подтверждает bytes/hash; соблюдение лицензии остаётся юридическим механизмом, а не математическим.
