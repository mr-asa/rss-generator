# ComfyUI Workflows RSS

Генератор нескольких RSS-лент из публичного индекса workflow на `comfy.org`.

## Состав

- `feeds.json` — список и фильтры лент.
- `generate_feeds.py` — один генератор для всех лент.
- `.github/workflows/update-feeds.yml` — обновление раз в час и публикация GitHub Pages.
- `public/` — сюда создаются XML-файлы.

## 1. Настройте адрес

В `feeds.json` замените:

```json
"base_url": "https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPOSITORY_NAME"
```

Например:

```json
"base_url": "https://mr-asa.github.io/comfy-rss"
```

## 2. Проверка локально

Нужен Python 3.10 или новее. Дополнительные библиотеки не нужны.

```powershell
python generate_feeds.py
```

Готовые файлы появятся в `public`.

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

После запуска workflow будут доступны адреса:

```text
https://USERNAME.github.io/REPOSITORY/newest.xml
https://USERNAME.github.io/REPOSITORY/video.xml
https://USERNAME.github.io/REPOSITORY/flux.xml
https://USERNAME.github.io/REPOSITORY/wan.xml
```

## Добавление ленты

Добавьте объект в массив `feeds` в `feeds.json`.

По слову:

```json
{
  "filename": "ltx.xml",
  "title": "ComfyUI — LTX workflows",
  "description": "Newest workflows mentioning LTX.",
  "contains": "ltx",
  "limit": 100
}
```

По точному тегу:

```json
{
  "filename": "animation.xml",
  "title": "ComfyUI — Animation",
  "tag": "animation",
  "limit": 100
}
```

По точному названию модели:

```json
{
  "filename": "selected-model.xml",
  "title": "Selected model",
  "model": "exact-model-name",
  "limit": 100
}
```

По любому из нескольких слов:

```json
{
  "filename": "video-models.xml",
  "title": "Video models",
  "contains": ["wan", "ltx", "hunyuan"],
  "limit": 100
}
```

С исключением:

```json
{
  "filename": "flux-no-controlnet.xml",
  "title": "FLUX without ControlNet",
  "contains": "flux",
  "exclude": "controlnet",
  "limit": 100
}
```

## Ручной запуск на GitHub

`Actions → Update RSS feeds → Run workflow`
