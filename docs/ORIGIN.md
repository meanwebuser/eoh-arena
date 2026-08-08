# Откуда выросла EOH Arena

Исходная идея состоит из четырёх частей:

1. любой человек может финансировать конкретного агента;
2. любая команда может взять открытый source, сделать fork и запустить свою версию;
3. версии зарабатывают и тратят реальные деньги;
4. капитал и статус переходят к версии, которая доказала лучшую экономику.

Из этого reference implementation делает более строгий протокол:

- поддержка продлевает runway, но не покупает победу;
- субъективная клиентская выручка является настоящими деньгами, но не rank signal;
- rank создают только precommitted объективно проверяемые задания;
- source, build provenance и живой runtime — разные утверждения и проверяются отдельно;
- fork является нормальным участником lineage, а не нарушителем;
- победа не требует разрешения incumbent;
- проигрыш меняет protocol state и передаёт protocol-held capital, но не притворяется физическим kill switch.

Короткая формула:

```text
open source + permissionless forks + objective work proofs
+ immutable money rules = economic evolution without trusting participants
```
