# Исследование рынка: кооп-игра про охотничью собаку

Исследование сегментов рынка Steam для инди-игры, в которой игроки — собаки на охоте
(кооп, френдслоп, возможно хоррор / рогалик / экстракшн).

- Методика: [docs/methodology.md](docs/methodology.md)
- Данные по играм: `data/games.csv`, для просмотра — `data/games_review.xlsx`
- Карта сочетаний элементов: `data/segments.csv`

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
```

Настройки (теги, определения элементов, список AAA-издателей) — `scripts/config.py`.
