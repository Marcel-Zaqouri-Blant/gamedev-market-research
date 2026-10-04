# Исследование рынка: кооп-игра про охотничью собаку

Исследование сегментов рынка Steam для инди-игры, в которой игроки — собаки на охоте
(кооп, френдслоп, возможно хоррор / рогалик / экстракшн).

- Методика: [docs/methodology.md](docs/methodology.md)
- Данные по играм: `data/games.csv`, для просмотра — `data/games_review.xlsx`
- Карта сочетаний элементов: `data/segments.csv`
- **Пересечение аудиторий и блогеры:** [docs/findings_audience.md](docs/findings_audience.md),
  таблицы — `data/audience_and_creators.xlsx`

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

Проверка математики пересечений: `python tests/test_overlap.py`.

Настройки (теги, определения элементов, список AAA-издателей) — `scripts/config.py`.
