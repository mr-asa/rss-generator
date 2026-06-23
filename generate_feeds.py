from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "feeds.json"
OUTPUT_DIR = ROOT / "public"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def fetch_json(url: str, timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "comfy-rss-generator/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API returned HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to API: {exc.reason}") from exc


def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_date(item: dict[str, Any]) -> datetime:
    if "pub_date" in item:
        v = item["pub_date"]
        if isinstance(v, datetime):
            return v
        return parse_date(v)
    for key in ("date", "publish_time", "createdAt", "lastModified"):
        v = item.get(key)
        if v:
            return parse_date(v)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def workflow_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("name") or "Untitled workflow")


def workflow_description(item: dict[str, Any]) -> str:
    return str(item.get("description") or "")


def workflow_share_id(item: dict[str, Any]) -> str:
    return str(item.get("shareId") or item.get("share_id") or "")


def workflow_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or workflow_share_id(item))


def workflow_url(item: dict[str, Any]) -> str:
    name = workflow_name(item).strip("/")
    share_id = workflow_share_id(item)
    if not share_id:
        return "https://comfy.org/workflows"
    slug = f"{name}-{share_id}" if name and not name.endswith(share_id) else name
    return f"https://comfy.org/workflows/{quote(slug, safe='-._~')}/"


def workflow_author(item: dict[str, Any]) -> str:
    profile = item.get("profile") or {}
    if isinstance(profile, dict):
        return str(
            profile.get("display_name")
            or profile.get("username")
            or item.get("username")
            or "ComfyUI"
        )
    return str(item.get("username") or "ComfyUI")


def as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            result.append(entry)
        elif isinstance(entry, dict):
            text = entry.get("display_name") or entry.get("name")
            if text:
                result.append(str(text))
    return result


def normalize_workflow(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "_source": "comfy_workflow",
        "title": workflow_title(item),
        "link": workflow_url(item),
        "guid": workflow_share_id(item) or workflow_url(item),
        "pub_date": parse_date(item.get("date") or item.get("publish_time")),
        "author": workflow_author(item),
        "description": workflow_description(item),
        "tags": as_text_list(item.get("tags")),
        "models": as_text_list(item.get("models")),
        "raw": item,
    }


def normalize_api_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        workflows = payload.get("workflows")
        if isinstance(workflows, list):
            return [item for item in workflows if isinstance(item, dict)]
    raise RuntimeError("Unexpected API response format")


def fetch_comfy_workflows(source: dict[str, Any]) -> list[dict[str, Any]]:
    payload = fetch_json(str(source["url"]), int(source.get("timeout_seconds", 30)))
    items = normalize_api_payload(payload)
    return [normalize_workflow(i) for i in items]


def normalize_hf_model(item: dict[str, Any]) -> dict[str, Any]:
    model_id = item.get("modelId") or item.get("id", "")
    model_url = f"https://huggingface.co/{model_id}"
    tags = [t for t in item.get("tags", []) if not t.startswith("license:") and not t.startswith("region:")]
    name_parts = model_id.split("/")
    short_name = name_parts[-1] if name_parts else model_id
    # Use lastModified for pub_date so updated models appear fresh
    pub_date_raw = item.get("lastModified") or item.get("createdAt")

    return {
        "_source": "huggingface",
        "title": short_name,
        "link": model_url,
        "guid": model_id,
        "pub_date": parse_date(pub_date_raw),
        "author": item.get("author", "HuggingFace"),
        "description": f"ComfyUI model on HuggingFace: {model_id}",
        "tags": tags,
        "models": [],
        "raw": item,
    }


def fetch_huggingface_models(source: dict[str, Any]) -> list[dict[str, Any]]:
    org = str(source["org"])
    sort_by = source.get("sort", "createdAt")
    direction = source.get("direction", "-1")
    fetch_limit = source.get("fetch_limit", 100)
    timeout = int(source.get("timeout_seconds", 30))

    url = (
        f"https://huggingface.co/api/models"
        f"?author={quote(org)}"
        f"&sort={quote(sort_by)}"
        f"&direction={quote(direction)}"
        f"&limit={fetch_limit}"
    )
    payload = fetch_json(url, timeout)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected HuggingFace API response: expected a list.")
    return [normalize_hf_model(i) for i in payload if isinstance(i, dict)]


def fetch_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    stype = source.get("type", "comfy_workflow")
    if stype == "comfy_workflow":
        return fetch_comfy_workflows(source)
    if stype == "huggingface":
        return fetch_huggingface_models(source)
    raise RuntimeError(f"Unknown source type: {stype}")


def searchable_text(item: dict[str, Any]) -> str:
    raw = item.get("raw", {})
    values = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("author", ""),
        *item.get("tags", []),
        *item.get("models", []),
    ]
    if item.get("_source") == "comfy_workflow":
        values.extend([
            workflow_name(raw),
            str(raw.get("mediaType") or raw.get("media_type", "")),
            *as_text_list(raw.get("requiresCustomNodes")),
        ])
    if item.get("_source") == "huggingface":
        values.append(raw.get("modelId", ""))
    return " ".join(str(v).casefold() for v in values)


def matches_feed(item: dict[str, Any], feed: dict[str, Any]) -> bool:
    required_source = feed.get("source_type")
    if required_source:
        if item.get("_source") != required_source:
            return False

    media_type = feed.get("media_type")
    if media_type:
        raw = item.get("raw", {})
        actual = str(raw.get("mediaType") or raw.get("media_type", ""))
        if actual.casefold() != str(media_type).casefold():
            return False

    required_tag = feed.get("tag")
    if required_tag:
        tags = {t.casefold() for t in item.get("tags", [])}
        if str(required_tag).casefold() not in tags:
            return False

    required_model = feed.get("model")
    if required_model:
        models = {m.casefold() for m in item.get("models", [])}
        if str(required_model).casefold() not in models:
            return False

    contains = feed.get("contains")
    if contains:
        needles = [contains] if isinstance(contains, str) else contains
        haystack = searchable_text(item)
        if not any(str(needle).casefold() in haystack for needle in needles):
            return False

    exclude = feed.get("exclude")
    if exclude:
        needles = [exclude] if isinstance(exclude, str) else exclude
        haystack = searchable_text(item)
        if any(str(needle).casefold() in haystack for needle in needles):
            return False

    return True


def add_text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = value
    return element


sources_map: dict[str, dict[str, Any]] = {}


def build_feed(items: list[dict[str, Any]], feed: dict[str, Any], site: dict[str, Any]) -> ET.ElementTree:
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    filename = str(feed["filename"])
    base_url = str(site.get("base_url") or "").rstrip("/")
    feed_url = f"{base_url}/{filename}" if base_url else ""

    source_name = feed.get("source")
    src = sources_map.get(source_name, {})
    if src.get("type") == "huggingface":
        org = src.get("org", "")
        channel_link = f"https://huggingface.co/{org}"
    else:
        channel_link = "https://comfy.org/workflows"

    add_text(channel, "title", str(feed["title"]))
    add_text(channel, "link", channel_link)
    add_text(channel, "description", str(feed.get("description") or ""))
    add_text(channel, "language", "en")
    add_text(channel, "lastBuildDate", format_datetime(datetime.now(timezone.utc)))
    if feed_url:
        ET.SubElement(
            channel,
            "{http://www.w3.org/2005/Atom}link",
            {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
        )

    for item in items:
        entry = ET.SubElement(channel, "item")
        description = str(item.get("description", ""))

        if item.get("_source") == "comfy_workflow":
            raw = item.get("raw", {})
            thumbnail = str(raw.get("thumbnailUrl") or raw.get("thumbnail_url") or "")
            if thumbnail:
                description = f'<p><img src="{thumbnail}" alt=""></p><p>{description}</p>'

        if item.get("_source") == "huggingface":
            raw = item.get("raw", {})
            likes = raw.get("likes")
            downloads = raw.get("downloads")
            stats_parts = []
            if likes is not None:
                stats_parts.append(f"\u2764 {likes}")
            if downloads is not None:
                stats_parts.append(f"\u2193 {downloads}")
            if stats_parts:
                description = f'<p>{" | ".join(stats_parts)}</p><p>{description}</p>'

        add_text(entry, "title", str(item.get("title", "")))
        add_text(entry, "link", str(item.get("link", "")))
        add_text(entry, "guid", str(item.get("guid", ""))).set("isPermaLink", "false")
        add_text(entry, "pubDate", format_datetime(item.get("pub_date", datetime(1970, 1, 1, tzinfo=timezone.utc))))
        add_text(entry, "author", str(item.get("author", "")))
        add_text(entry, "description", description)

        for category in item.get("tags", []):
            add_text(entry, "category", str(category))
        for model in item.get("models", []):
            add_text(entry, "category", str(model))

    ET.indent(rss, space="  ")
    return ET.ElementTree(rss)


def main() -> int:
    config = load_config()
    sources = config.get("sources") or {}

    if not sources and "source" in config:
        sources = {"default": config["source"]}

    global sources_map
    sources_map = sources

    site = config.get("site") or {}
    feeds = config.get("feeds") or []

    source_data: dict[str, list[dict[str, Any]]] = {}
    for name, source in sources.items():
        source_type = source.get("type", "comfy_workflow")
        print(f"Fetching source: {name} ({source_type})")
        items = fetch_source(source)
        items.sort(key=normalize_date, reverse=True)
        source_data[name] = items
        print(f"  -> {len(items)} items")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for feed in feeds:
        source_name = feed.get("source")
        if source_name and source_name in source_data:
            all_items = source_data[source_name]
        elif len(sources) == 1:
            all_items = next(iter(source_data.values()))
        else:
            fname = feed.get("filename", "?")
            print(f"WARNING: feed '{fname}' references unknown source '{source_name}', skipping")
            continue

        filename = str(feed["filename"])
        if Path(filename).name != filename or not filename.endswith(".xml"):
            raise RuntimeError(f"Unsafe or invalid feed filename: {filename}")

        selected = [item for item in all_items if matches_feed(item, feed)]
        selected = selected[: int(feed.get("limit", 100))]
        output_path = OUTPUT_DIR / filename
        build_feed(selected, feed, site).write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"Generated {output_path.relative_to(ROOT)}: {len(selected)} items")

    # Build index.html
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        '<head><meta charset="utf-8"><title>ComfyUI RSS feeds</title></head>',
        "<body><h1>ComfyUI RSS feeds</h1><ul>",
    ]
    for feed in feeds:
        fname = feed["filename"]
        ftitle = feed["title"]
        lines.append(f'<li><a href="{fname}">{ftitle}</a></li>')
    lines.extend(["</ul></body>", "</html>"])
    (OUTPUT_DIR / "index.html").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
