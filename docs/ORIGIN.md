# Откуда выросла EOH Arena

Earn or Halt начинается с экономической идеи: открытая версия должна
зарабатывать право на следующий цикл, а капитал и роутинг должны переходить
к версии с лучшей проверяемой экономикой. EOH Arena переводит эту идею в
on-chain state machine, но не делает более сильных утверждений, чем способны
проверить verifier'ы.

## Перевод идеи в протокол

| Идея | Что реально фиксирует код |
| --- | --- |
| Открытые forks | createLineage/registerVersion сохраняют lineage, parent и digest'ы; исходник должен быть AGPL и иметь ipfs:// URI. |
| Деньги должны быть внешними | settlementToken передаётся в constructor; собственный token не является частью rank formula. |
| Поддержка не покупает победу | donate увеличивает vault/capital, но не _economy и не profit. |
| Работа должна быть objective | Ranked job допускается только через immutable IJobAuthorizer, а result/cost возвращает IWorkVerifier. |
| Клиентская выручка существует отдельно | Market escrow принимается buyer'ом и пишется в marketRevenue, но не участвует в selection. |
| Сильная версия может заменить incumbent | Любой адрес может вызвать supersede при строгом positive-profit превосходстве за last closed epoch. |
| Экономическая смерть не равна физическому kill | ejectStale переводит vault в commons и меняет protocol status; внешний сервер контракт выключить не может. |

## Почему разделены market и ranked

Buyer и operator могут быть одной стороной. Поэтому market payment — это
реальный капитал, но не объективный rank signal. Ranked reward приходит из
commons за заранее опубликованное задание, а verifier одновременно возвращает
proof id и protocol-visible cost. Формула selection использует только
rankedRevenue - verifiedRankedCost одного закрытого epoch.

Такой split не доказывает полезность всякой работы. Он ограничивает
утверждение: rank существует только там, где конкретный verifier способен
объективно проверить результат и стоимость. Для текста, внешней полезности и
реальных provider receipts нужен отдельный production verifier; demo
verifier'ы этого не предоставляют.

## Source, build и runtime — разные утверждения

Регистрация требует одновременно:

1. source digest и ipfs:// URI;
2. image digest и provenance digest;
3. runtime identity;
4. proof для IRuntimeVerifier.

Контракт сохраняет все поля, а heartbeat повторно проверяет runtime proof.
Это не превращает CID в доказательство живого исполнения: доступность source
bundle и семантика attestation остаются частью trust boundary конкретного
verifier'а.

## Граница реализации

Python-модель в [../model/arena.py](../model/arena.py) даёт исполняемую
проверку переходов и conservation. Solidity в
[../contracts/EohArena.sol](../contracts/EohArena.sol) — reference source,
закреплённый pin'ом compiler script, но без compiled artifact, независимого
аудита или deployment evidence в этом staging pass.
