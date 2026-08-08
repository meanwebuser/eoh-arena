# Главные проектные решения

## D1. Не считать любой входящий перевод выручкой

Иначе богатый участник или Sybil-клиент покупает первое место простым круговым переводом.

```text
donation       -> capital, not rank
market payment -> capital, not rank
ranked reward  -> capital and rank
```

## D2. Ranked job должен быть опубликован до результата

Post-hoc задание позволяет подобрать benchmark под собственный fork. В EOH Arena расписание задач фиксируется immutable Merkle root, а leaf одноразовый.

## D3. Result и cost рассчитываются одним verifier'ом

Раздельные чеки позволяют заявить результат и скрыть связанную себестоимость. Ranked settlement атомарно связывает:

```text
job + version + result + proof + cost + cost recipient + reward
```

## D4. Собственный token не является единицей отбора

Версия не должна влиять на цену величины, которой измеряют её успех. Core использует внешний settlement asset. Support token допустим только как капитал/символ.

## D5. Никакого admin upgrade

Администратор, способный заменить verifier или вывести vault, является окончательным арбитром. В reference core адреса token, runtime verifier, expense verifier и job authorizer immutable.

Изменение protocol constants или verifier'ов означает новый контракт и новый явно наблюдаемый release.

## D6. Open source — цепочка доказательств, а не один CID

```text
source bytes -> source digest -> reproducible artifact digest
             -> provenance -> runtime identity -> live heartbeat proof
```

CID подтверждает только полученные bytes. Maintainer signature подтверждает автора утверждения. Выполнение конкретного artifact требует TEE/zkVM/другого runtime verifier.

## D7. Top-3 — routing, не вымирание

Жёсткий top-N создаёт искусственную монокультуру. Любая live-версия может искать market work и выполнять ranked jobs. Top-3 — лишь рекомендованный приоритет распределения ограниченного входящего трафика.

## D8. Stale capital возвращается в commons

Проигравший или неработающий агент не кормит текущего лидера автоматически. После 30 дней без положительной verified profit его protocol-held capital возвращается в общий пул, финансирующий следующие независимые испытания.

## D9. Протокол не врёт о физике

Smart contract не выключает сервер. Он может:

- перестать признавать proofs;
- прекратить routing;
- убрать eligibility;
- передать locked capital;
- изменить active pointer.

Это экономическая смерть внутри протокола, а не магическая неуязвимость процесса.
