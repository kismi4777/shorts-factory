# Shorts Factory

Конвейер коротких вертикальных роликов на базе идей **MoneyPrinterTurbo** (стоки) и **ShortGPT** (история поверх геймплея). Старый Fact-Shorts вынесен в `_archive_factshorts/`.

## Режимы

| Mode | Что делает |
|------|------------|
| `stock` | тема → Ollama сценарий + EN search terms → Pexels → Edge-TTS → pop-up субтитры → FFmpeg |
| `reddit_gameplay` | тема → Ollama story → Edge-TTS → субтитры поверх `assets/backgrounds/*.mp4` |

ИИ-картинки (Flux/Ken Burns) не используем.

## Локально (Ollama)

Нужны: Python 3.11+, FFmpeg в PATH, [Ollama](https://ollama.com) с моделью (по умолчанию `qwen2.5:1.5b`).

```bash
pip install -r requirements.txt
# стоки: Pixabay (Pexels сейчас не выдаёт новые ключи)
# https://pixabay.com/api/docs/ → Login → скопировать key
# set PIXABAY_API_KEY=...

python -m factory make --mode stock --topic "Почему кофе бодрит"
python -m factory render --job jobs/<id>.json

# или сразу:
python -m factory all --mode stock --topic "Почему кофе бодрит"
python -m factory all --mode reddit_gameplay --topic "История с работы про босса"
```

Без `PIXABAY_API_KEY` stock-режим соберёт цветные placeholder-клипы (для smoke).

## GitHub Actions (сборка бесплатно)

1. Запушь репозиторий на GitHub (public = без лимита минут Actions).
2. Secrets → `PIXABAY_API_KEY` (для stock; Pexels опционально).
3. Локально `make` → закоммить `jobs/*.json` **или**:

```bash
gh workflow run render-short.yml -f job=jobs/<id>.json
```

Артефакт: `short-output` → `output/<id>/output.mp4`.

Сценарий на Actions **не** генерируется (нет доступа к твоему Ollama) — только render.

## Vendor

- `vendor/MoneyPrinterTurbo/` — upstream MIT, pin в `PINNED_COMMIT`, `config.toml` с `llm_provider=ollama`.
- Полный MPT WebUI/API можно поднять отдельно из `vendor/MoneyPrinterTurbo`; factory использует lean FFmpeg-путь для CI.

## Структура

```
factory/           # CLI + Ollama + render
jobs/              # JSON задания
output/            # готовые mp4
assets/backgrounds # фоны для reddit_gameplay
vendor/MoneyPrinterTurbo
_archive_factshorts
.github/workflows/render-short.yml
```
