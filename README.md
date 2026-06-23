# ComfyUI RSS Generator

Генератор RSS-лент из нескольких источников: публичный индекс workflow на `comfy.org` и модели организаций на HuggingFace.

## Состав

- `feeds.json` — источники данных, настройки и фильтры лент.
- `generate_feeds.py` — генератор (Python stdlib, без зависимостей).
- `.github/workflows/update-feeds.yml` — обновление раз в час, публикация GitHub Pages.
- `public/` — сюда создаются XML-файлы и `index.html`.

---

## 1. Настройте адрес

В `feeds.json` замените `base_url` на ваш:

```json
"base_url": "https://YOUR_USERNAME.github.io/YOUR_REPO_NAME"
```

## 2. Проверка локально

Нужен Python 3.10+. Дополнительные библиотеки не требуются.

```powershell
python generate_feeds.py
```

Готовые файлы появятся в `public/`.

## 3. Загрузка в GitHub

```powershell
git init
git add .
git commit -m "Initial RSS generator"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

## 4. GitHub Pages

Откройте `Settings → Pages`, затем в `Build and deployment` выберите:

```text
Source → GitHub Actions
```

После запуска workflow лентy будут доступны по адресам вида:

```text
https://USERNAME.github.io/REPO_NAME/newest.xml
https://USERNAME.github.io/REPO_NAME/hf-models.xml
```

---

## Архитектура конфигурации

Файл `feeds.json` состоит из трёх секций:

| Секция | Назначение |
|--------|-----------|
| `sources` | Словарь источников данных (каждый — отдельный API или сервис) |
| `site` | Метаданные RSS (заголовок, ссылка, язык) |
| `feeds` | Массив лент — каждая привязана к одному `source` через поле `"source"` |

```
source (данные)  →  feed (фильтр + RSS)  →  public/*.xml  →  GitHub Pages
```

---

## Добавление источника (source)

Каждый уникальный источник данных добавляется в секцию `"sources"` с уникальным именем-ключом.

### ComfyUI workflows (тип `comfy_workflow`)

```json
"sources": {
  "comfy_workflows": {
    "type": "comfy_workflow",
    "url": "https://cloud.comfy.org/api/hub/workflows/index?status=approved",
    "timeout_seconds": 30
  }
}
```

### HuggingFace организация (тип `huggingface`)

```json
"sources": {
  "huggingface_comfy": {
    "type": "huggingface",
    "org": "Comfy-Org",
    "timeout_seconds": 30,
    "sort": "lastModified",
    "direction": "-1",
    "fetch_limit": 1000
  }
}
```

| Параметр | Описание | Пример |
|----------|----------|--------|
| `type` | Тип источника: `comfy_workflow` или `huggingface` | `"huggingface"` |
| `org` | Название организации на HF (только для `huggingface`) | `"Comfy-Org"` |
| `sort` | Поле сортировки на стороне API | `"lastModified"`, `"createdAt"` |
| `direction` | Направление: `-1` = по убыванию (свежие первыми) | `"-1"` |
| `fetch_limit` | Сколько записей загрузить из API. Поставьте число больше, чем всего моделей в организации — чтобы фильтры работали на полных данных | `1000` |

### Несколько организаций

Каждая организация — отдельный entry в `sources`:

```json
"sources": {
  "huggingface_comfy": {
    "type": "huggingface",
    "org": "Comfy-Org",
    "sort": "lastModified",
    "direction": "-1",
    "fetch_limit": 1000
  },
  "huggingface_instantx": {
    "type": "huggingface",
    "org": "InstantX",
    "sort": "lastModified",
    "direction": "-1",
    "fetch_limit": 1000
  }
}
```

---

## Добавление ленты (feed)

Каждая лента — объект в массиве `"feeds"`. Обязательные поля: `source`, `filename`, `title`.

### Минимальный пример

```json
{
  "source": "huggingface_comfy",
  "filename": "hf-models.xml",
  "title": "ComfyUI HF Models",
  "description": "All models from Comfy-Org on HuggingFace.",
  "limit": 50
}
```

### Фильтрация по ключевым словам (`contains`)

```json
{
  "source": "huggingface_comfy",
  "filename": "hf-flux.xml",
  "title": "Comfy-Org Flux Models",
  "contains": "flux",
  "limit": 30
}
```

Несколько ключевых слов (OR):

```json
{
  "source": "huggingface_comfy",
  "filename": "hf-video.xml",
  "title": "Video Models",
  "contains": ["wan", "ltx", "hunyuan"],
  "limit": 50
}
```

### Исключение (`exclude`)

```json
{
  "source": "comfy_workflows",
  "filename": "flux-no-controlnet.xml",
  "title": "FLUX without ControlNet",
  "contains": "flux",
  "exclude": "controlnet",
  "limit": 100
}
```

### Фильтр по тегу (`tag`)

Точное совпадение (только для ComfyUI workflows):

```json
{
  "source": "comfy_workflows",
  "filename": "animation.xml",
  "title": "Animation Workflows",
  "tag": "animation",
  "limit": 100
}
```

### Фильтр по модели (`model`)

Точное совпадение (только для ComfyUI workflows):

```json
{
  "source": "comfy_workflows",
  "filename": "selected-model.xml",
  "title": "Selected model",
  "model": "exact-model-name",
  "limit": 100
}
```

### Фильтр по типу медиа (`media_type`)

```json
{
  "source": "comfy_workflows",
  "filename": "video.xml",
  "title": "Video Workflows",
  "media_type": "video",
  "limit": 100
}
```

---

## Полные параметры ленты

| Поле | Тип | Описание |
|------|-----|----------|
| `source` | `string` | Ключ источника из `sources` (обязательно при нескольких sources) |
| `filename` | `string` | Имя выходного файла, должно заканчиваться на `.xml` |
| `title` | `string` | Заголовок RSS-канала |
| `description` | `string` | Описание канала |
| `limit` | `int` | Максимум записей в ленте (по умолчанию 100) |
| `contains` | `string` \| `string[]` | Включить записи, содержащие любое из слов |
| `exclude` | `string` \| `string[]` | Исключить записи, содержащие любое из слов |
| `tag` | `string` | Точный тег (ComfyUI) |
| `model` | `string` | Точное название модели (ComfyUI) |
| `media_type` | `string` | Тип медиа: `video`, `image` (ComfyUI) |

---

## Пример: добавить организацию InstantX

1. В `sources` добавить источник:

```json
"huggingface_instantx": {
  "type": "huggingface",
  "org": "InstantX",
  "sort": "lastModified",
  "direction": "-1",
  "fetch_limit": 1000
}
```

2. В `feeds` добавить ленту:

```json
{
  "source": "huggingface_instantx",
  "filename": "hf-instantx.xml",
  "title": "InstantX Flux LoRAs",
  "description": "Flux LoRA models from InstantX on HuggingFace.",
  "limit": 50
}
```

3. Закоммитьте и запушьте — GitHub Actions автоматически сгенерирует `public/hf-instantx.xml`.

URL подписки:

```
https://USERNAME.github.io/REPO_NAME/hf-instantx.xml
```

## Ручной запуск на GitHub

`Actions → Update RSS feeds → Run workflow`