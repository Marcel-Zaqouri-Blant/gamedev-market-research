# Исследование рынка: кооп-игра про охотничью собаку

Исследование сегментов рынка Steam для инди-игры, в которой игроки — собаки на охоте
(кооп, френдслоп, возможно хоррор / рогалик / экстракшн).

- Методика: [docs/methodology.md](docs/methodology.md)
- Данные по играм: `data/games.csv`, для просмотра — `data/games_review.xlsx`
- Карта сочетаний элементов: `data/segments.csv`
- **Пересечение аудиторий и блогеры:** [docs/findings_audience.md](docs/findings_audience.md),
  таблицы — `data/audience_and_creators.xlsx`
- **Кто люди на стыках (открытые профили):** [docs/findings_profiles.md](docs/findings_profiles.md),
  таблицы — `data/profiles.xlsx`
- **Какие направления выигрывают в коопе (17 тыс. кооп-игр):**
  [docs/findings_coop_directions.md](docs/findings_coop_directions.md), таблицы — `data/coop_directions.xlsx`
- **Качество успеха, цена, игроки, ориентиры, конкуренты:** [docs/findings_quality.md](docs/findings_quality.md),
  таблицы — `data/quality.xlsx`, `data/competitors.xlsx`
- **Динамика сочетаний с собакой и охотой:** `docs/combos_overview.html`
  (интерактивная страница), данные — `data/combo_summary.csv`, `data/combo_dynamics.csv`

## Как пересобрать данные

```bash
pip install -r requirements.txt
cd scripts
python 01_collect_search.py   # список игр из поиска Steam по тегам
python 02_fetch_details.py    # теги, разработчик, отзывы (~1 ч, можно прерывать)
python 03_fetch_prices.py     # базовые цены
python 04_build_dataset.py    # data/games.csv
python 05_segment_map.py      # data/segments.csv
python 06_export_review.py    # data/games_review.xlsx
python 07_audience_overlap.py estimate   # сколько запросов нужно
python 07_audience_overlap.py collect    # авторы отзывов (~2 ч: Steam держит ~0,7 запроса/с; можно прерывать)
python 07_audience_overlap.py analyze    # data/audience_overlap.csv, data/audience_affinity.csv
```

Блогеры на стыках (нужен `YOUTUBE_API_KEY`, ~100 поисков в сутки по бесплатной квоте):

```bash
python 08_creators.py targets   # выбор игр по стыкам из кэша отзывов
python 08_creators.py search    # поиск видео (кэшируется)
python 08_creators.py rank      # data/creators.csv
python 09_export_audience.py    # data/audience_and_creators.xlsx
```

Динамика сочетаний и профили:

```bash
python 11_combo_dynamics.py     # data/combo_summary.csv, data/combo_dynamics.csv
python 12_overview_page.py      # docs/combos_overview.html
python 10_profiles.py collect   # открытые профили людей со стыков (~30 мин)
python 10_profiles.py tags      # теги игр из профилей
python 10_profiles.py analyze
python 13_export_profiles.py    # data/profiles.xlsx
```

Направления в коопе:

```bash
python 14_coop_market.py collect   # все кооп-игры Steam (~10 мин)
python 14_coop_market.py analyze   # data/coop_directions.xlsx
python 14_coop_market.py near      # то же на играх про животных и охоту: data/coop_near.xlsx
python 14_coop_market.py small     # недорогие направления: data/coop_small_scope.csv
python 15_quality.py collect       # цены, страницы, выборки отзывов (~15 мин)
python 15_quality.py youtube       # просмотры YouTube (квота!)
python 15_quality.py analyze       # data/quality.xlsx
python 16_competitors.py           # анонсы-конкуренты: data/competitors.xlsx
```

Проверка математики пересечений: `python tests/test_overlap.py`.

Настройки (теги, определения элементов, список AAA-издателей) — `scripts/config.py`.
