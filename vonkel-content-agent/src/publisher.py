"""publisher.py — post een artikel als DRAFT naar Shopify, nooit live.

Gebruikt de Shopify Admin REST API (Articles endpoint onder Blog).
In dry-run schrijft hij alleen de payload weg als voorbeeld-request.

Sync van products is ook hier: `python -m src.publisher --sync-products` haalt
de actuele productlijst uit Shopify en update data/products.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .utils import (
    PRODUCTS_JSON,
    PUBLISHED_JSON,
    env,
    get_logger,
    now_iso,
    read_json,
    write_json,
)

log = get_logger("publisher")


# ---------------------------------------------------------------------------
# Shopify client
# ---------------------------------------------------------------------------


def _client() -> httpx.Client:
    token = env("SHOPIFY_ADMIN_TOKEN", required=True)
    store = env("SHOPIFY_STORE", required=True)
    api_version = env("SHOPIFY_API_VERSION", "2024-10")
    base = f"https://{store}/admin/api/{api_version}"
    return httpx.Client(
        base_url=base,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30.0,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=15))
def _post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(path, json=payload)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=15))
def _get(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = client.get(path, params=params or {})
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Product sync
# ---------------------------------------------------------------------------


def sync_products() -> None:
    """Haal alle producten op uit Shopify en schrijf naar data/products.json."""
    log.info("[bold]sync_products[/bold]: ophalen uit Shopify")
    with _client() as client:
        # Pagination via Link header kan uitgebreid; 9 wijnen past ruim in 1 page
        data = _get(client, "/products.json", {"limit": 250})

    products: list[dict[str, Any]] = []
    store = env("SHOPIFY_STORE", "").replace(".myshopify.com", "")
    domain = f"https://www.{store}.nl" if store else "https://www.vonkelwijnen.nl"

    for p in data.get("products", []):
        products.append(
            {
                "handle": p.get("handle"),
                "title": p.get("title"),
                "producer": p.get("vendor"),
                "region": None,  # vul aan via metafields als die bestaan
                "grape": None,
                "style": p.get("product_type"),
                "url": f"{domain}/products/{p.get('handle')}",
                "in_stock": any(v.get("inventory_quantity", 0) > 0 for v in p.get("variants", [])),
                "price_eur": float(p["variants"][0]["price"]) if p.get("variants") else None,
            }
        )

    write_json(
        PRODUCTS_JSON,
        {
            "_meta": {
                "synced_at": now_iso(),
                "source": "Shopify Admin API",
                "count": len(products),
            },
            "products": products,
        },
    )
    log.info(f"[green]synced {len(products)} producten[/green]")


# ---------------------------------------------------------------------------
# Publish article
# ---------------------------------------------------------------------------


def _markdown_to_html(md: str) -> str:
    from markdown_it import MarkdownIt

    md_it = MarkdownIt("commonmark", {"html": False, "linkify": True})
    return md_it.render(md)


def publish_article(article_dir: Path, *, dry_run: bool) -> dict[str, Any]:
    article_md = (article_dir / "article.md").read_text(encoding="utf-8")
    meta = json.loads((article_dir / "meta.json").read_text(encoding="utf-8"))

    # Strip frontmatter from body for HTML conversion
    import re

    m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)$", article_md, re.DOTALL)
    body = m.group(1).strip() if m else article_md

    html = _markdown_to_html(body)

    # Inject JSON-LD at the end of the body
    json_ld = meta.get("json_ld")
    if json_ld:
        if isinstance(json_ld, dict):
            ld_str = json.dumps(json_ld, ensure_ascii=False)
        else:
            ld_str = str(json_ld)
        html += f'\n<script type="application/ld+json">{ld_str}</script>'

    article_payload = {
        "article": {
            "title": meta["title"],
            "body_html": html,
            "published": False,  # STRIKT: altijd draft
            "handle": meta["slug"],
            "tags": ", ".join(meta.get("tags", []) or []),
            "summary_html": meta.get("meta_description", ""),
            "metafields": [
                {
                    "namespace": "global",
                    "key": "description_tag",
                    "value": meta.get("meta_description", ""),
                    "type": "single_line_text_field",
                },
                {
                    "namespace": "global",
                    "key": "title_tag",
                    "value": meta["title"],
                    "type": "single_line_text_field",
                },
            ],
        }
    }

    if dry_run:
        dry_path = article_dir / "shopify_payload.json"
        dry_path.write_text(
            json.dumps(article_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"[yellow]DRY-RUN[/yellow]: payload geschreven naar {dry_path.name}")
        return {"dry_run": True, "payload_path": str(dry_path)}

    blog_id = env("SHOPIFY_BLOG_ID", required=True)
    with _client() as client:
        result = _post(client, f"/blogs/{blog_id}/articles.json", article_payload)

    log.info(f"[green]DRAFT aangemaakt[/green]: article_id={result.get('article', {}).get('id')}")
    return result


# ---------------------------------------------------------------------------
# Published log
# ---------------------------------------------------------------------------


def log_published(article_dir: Path, publish_result: dict[str, Any], *, dry_run: bool) -> None:
    meta = json.loads((article_dir / "meta.json").read_text(encoding="utf-8"))
    log_data = read_json(PUBLISHED_JSON)
    entries = log_data.get("articles", [])
    entries.append(
        {
            "slug": meta["slug"],
            "title": meta["title"],
            "keyword": meta.get("primary_keyword"),
            "pillar": meta.get("pillar"),
            "cluster_title": meta.get("cluster_title"),
            "generated_at": meta.get("generated_at"),
            "dry_run": dry_run,
            "shopify_article_id": (publish_result.get("article") or {}).get("id") if not dry_run else None,
            "status": "draft_dry_run" if dry_run else "draft",
        }
    )
    log_data["articles"] = entries
    write_json(PUBLISHED_JSON, log_data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-products", action="store_true")
    parser.add_argument("--article", type=str, help="pad naar output/<slug>")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.sync_products:
        sync_products()
        return

    if args.article:
        result = publish_article(Path(args.article), dry_run=args.dry_run)
        log_published(Path(args.article), result, dry_run=args.dry_run)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
