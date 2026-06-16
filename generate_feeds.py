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


def workflow_date(item: dict[str, Any]) -> datetime:
    return parse_date(item.get("date") or item.get("publish_time"))


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


def searchable_text(item: dict[str, Any]) -> str:
    values = [
        workflow_title(item),
        workflow_description(item),
        workflow_name(item),
        workflow_author(item),
        str(item.get("mediaType") or item.get("media_type") or ""),
        *as_text_list(item.get("tags")),
        *as_text_list(item.get("models")),
        *as_text_list(item.get("requiresCustomNodes")),
    ]
    return " ".join(values).casefold()


def matches_feed(item: dict[str, Any], feed: dict[str, Any]) -> bool:
    media_type = feed.get("media_type")
    if media_type:
        actual = str(item.get("mediaType") or item.get("media_type") or "")
        if actual.casefold() != str(media_type).casefold():
            return False

    required_tag = feed.get("tag")
    if required_tag:
        tags = {tag.casefold() for tag in as_text_list(item.get("tags"))}
        if str(required_tag).casefold() not in tags:
            return False

    required_model = feed.get("model")
    if required_model:
        models = {model.casefold() for model in as_text_list(item.get("models"))}
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


def build_feed(items: list[dict[str, Any]], feed: dict[str, Any], site: dict[str, Any]) -> ET.ElementTree:
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    filename = str(feed["filename"])
    base_url = str(site.get("base_url") or "").rstrip("/")
    feed_url = f"{base_url}/{filename}" if base_url else ""

    add_text(channel, "title", str(feed["title"]))
    add_text(channel, "link", "https://comfy.org/workflows")
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
        link = workflow_url(item)
        guid = workflow_share_id(item) or link
        description = workflow_description(item)
        thumbnail = str(item.get("thumbnailUrl") or item.get("thumbnail_url") or "")
        if thumbnail:
            description = f'<p><img src="{thumbnail}" alt=""></p><p>{description}</p>'

        add_text(entry, "title", workflow_title(item))
        add_text(entry, "link", link)
        add_text(entry, "guid", guid).set("isPermaLink", "false")
        add_text(entry, "pubDate", format_datetime(workflow_date(item)))
        add_text(entry, "author", workflow_author(item))
        add_text(entry, "description", description)

        for category in as_text_list(item.get("tags")):
            add_text(entry, "category", category)
        for model in as_text_list(item.get("models")):
            add_text(entry, "category", model)

    ET.indent(rss, space="  ")
    return ET.ElementTree(rss)


def normalize_api_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        workflows = payload.get("workflows")
        if isinstance(workflows, list):
            return [item for item in workflows if isinstance(item, dict)]
    raise RuntimeError("Unexpected API response format: expected a list or {'workflows': [...]}.")


def main() -> int:
    config = load_config()
    source = config["source"]
    site = config.get("site") or {}
    feeds = config.get("feeds") or []

    payload = fetch_json(str(source["url"]), int(source.get("timeout_seconds", 30)))
    all_items = normalize_api_payload(payload)
    all_items.sort(key=workflow_date, reverse=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for feed in feeds:
        filename = str(feed["filename"])
        if Path(filename).name != filename or not filename.endswith(".xml"):
            raise RuntimeError(f"Unsafe or invalid feed filename: {filename}")
        selected = [item for item in all_items if matches_feed(item, feed)]
        selected = selected[: int(feed.get("limit", 100))]
        output_path = OUTPUT_DIR / filename
        build_feed(selected, feed, site).write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"Generated {output_path.relative_to(ROOT)}: {len(selected)} items")

    index = [
        "<!doctype html>",
        '<html lang="en">',
        "<head><meta charset=\"utf-8\"><title>ComfyUI RSS feeds</title></head>",
        "<body><h1>ComfyUI RSS feeds</h1><ul>",
    ]
    for feed in feeds:
        index.append(f'<li><a href="{feed["filename"]}">{feed["title"]}</a></li>')
    index.extend(["</ul></body>", "</html>"])
    (OUTPUT_DIR / "index.html").write_text("\n".join(index) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
