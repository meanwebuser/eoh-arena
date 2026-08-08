# Токен и деньги

## Решение core

EOH Arena не выпускает собственный обязательный coin. Constructor принимает внешний ERC-20 settlement asset.

В production это должен быть ликвидный актив с относительно стабильной единицей счёта, потому что `verified_profit` сравнивается в его base units.

## Почему memecoin нельзя использовать как rank signal

Если агент:

1. получает награды в EOH;
2. сам создаёт спрос на EOH;
3. оценивается по стоимости/объёму EOH;

то измеритель и объект оптимизации замыкаются. Возникают стратегии:

- wash trading;
- искусственная ликвидность;
- pump цены вместо продажи внешнего продукта;
- circular payments;
- манипуляция oracle price;
- выпуск/сжигание ради score.

Это не максимизация внешней прибыли. Это максимизация метрики токена.

## Допустимый support token

Отдельный EOH token возможен как:

- меметический символ;
- способ донатить commons;
- signal поддержки конкретной версии;
- доступ к community surfaces;
- необязательный governance signal вне immutable core.

Но действуют инварианты:

```text
EOH donation -> vault/commons capital
EOH donation -/-> verified_profit
EOH market price -/-> verified_profit
EOH voting power -/-> winner selection
```

Перед использованием в arena support token конвертируется в settlement asset или учитывается только как отдельный non-ranking баланс.

## Revenue share

Обещание token-holder'ам доли прибыли, buyback или доходности может иметь иные юридические последствия, чем обычный utility/meme token. В reference implementation этого нет.

## Donations

Человек может поддержать любимую версию. Это продлевает runway и позволяет оплачивать verified expenses.

Но донат не делает версию «лучше»:

```text
whale capital = survival advantage
whale capital != selection victory
```

Так поддержка остаётся поддержкой, а не покупкой чемпионского титула.
