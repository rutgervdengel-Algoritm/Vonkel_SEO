"""planner.py — kiest het volgende artikel en bouwt een brief voor writer.py.

Logica:
  1. Laad keyword_bank (van research.py). Als leeg: gebruik seo_targets cluster definities.
  2. Dedup tegen published.json (nooit twee keer hetzelfde onderwerp).
  3. Combineer de kandidaat-score met pillar coverage gap.
  4. Genereer een Brief met doel, keyword, intent, target length, angle,
     interne linktargets en CTA.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .utils import (
    PUBLISHED_JSON,
    get_logger,
    load_products,
    load_seo_targets,
    read_json,
)
from .research import top_candidates

log = get_logger("planner")


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------


@dataclass
class Brief:
    pillar: str
    cluster_title: str
    keyword: str
    intent: str
    target_word_count: tuple[int, int]
    angle: str
    linked_products: list[dict[str, Any]] = field(default_factory=list)
    internal_link_targets: list[dict[str, str]] = field(default_factory=list)
    cta_template: str = ""
    seo_signals: dict[str, Any] = field(default_factory=dict)
    score: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Coverage + dedup
# ---------------------------------------------------------------------------


def published_keywords() -> set[str]:
    data = read_json(PUBLISHED_JSON)
    return {a.get("keyword", "").lower() for a in data.get("articles", [])}


def published_slugs() -> set[str]:
    data = read_json(PUBLISHED_JSON)
    return {a.get("slug", "") for a in data.get("articles", [])}


def pillar_coverage() -> dict[str, float]:
    """Hoeveel van elke pillar is al afgedekt (0-1)."""
    seo = load_seo_targets()
    published = read_json(PUBLISHED_JSON).get("articles", [])
    pub_by_pillar: dict[str, int] = {}
    for art in published:
        pub_by_pillar[art.get("pillar", "")] = pub_by_pillar.get(art.get("pillar", ""), 0) + 1

    coverage: dict[str, float] = {}
    for pillar_key, pillar in seo.get("pillars", {}).items():
        target = max(int(pillar.get("coverage_target", 1)), 1)
        have = pub_by_pillar.get(pillar_key, 0)
        coverage[pillar_key] = min(have / target, 1.0)
    return coverage


# ---------------------------------------------------------------------------
# Candidate gathering from seo_targets (fallback when keyword_bank leeg is)
# ---------------------------------------------------------------------------


def cluster_candidates() -> list[dict[str, Any]]:
    """Fallback: gebruik de hand-gedefinieerde clusters in seo_targets.yaml."""
    seo = load_seo_targets()
    candidates: list[dict[str, Any]] = []
    for pillar_key, pillar in seo.get("pillars", {}).items():
        for cluster in pillar.get("clusters", []):
            candidates.append(
                {
                    "pillar": pillar_key,
                    "pillar_title": pillar.get("title", pillar_key),
                    "cluster_title": cluster.get("title"),
                    "keyword": cluster.get("keyword"),
                    "intent": cluster.get("intent", pillar.get("search_intent", "informational")),
                    "opportunity_score": cluster.get("opportunity_score", 50),
                    "angle": cluster.get("angle", ""),
                    "linked_products": cluster.get("linked_products", []) or [],
                }
            )
    return candidates


def _match_candidate_to_pillar(keyword: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Zoek in seo_targets welke pillar+cluster bij een keyword uit keyword_bank hoort."""
    seo = load_seo_targets()
    kw = keyword.lower()
    for pillar_key, pillar in seo.get("pillars", {}).items():
        for cluster in pillar.get("clusters", []):
            if (cluster.get("keyword") or "").lower() == kw:
                return pillar_key, pillar, cluster
    # Geen directe match: gebruik eerste pillar
    first_key = next(iter(seo.get("pillars", {}).keys()), "")
    first = seo.get("pillars", {}).get(first_key, {})
    return (first_key, first, {}) if first else None


# ---------------------------------------------------------------------------
# Brief builder
# ---------------------------------------------------------------------------


def build_brief(candidate: dict[str, Any]) -> Brief:
    seo = load_seo_targets()
    products = load_products()

    pillar_key = candidate["pillar"]
    pillar = seo["pillars"][pillar_key]
    linked_product_handles = candidate.get("linked_products") or []
    linked_products = [p for p in products if p["handle"] in linked_product_handles]

    # Interne link targets: de pillar-pagina + (indien beschikbaar) 1-2 andere clusters
    internal_link_targets: list[dict[str, str]] = [
        {
            "label": pillar["title"],
            "url": pillar.get("target_url_path", "/blogs/zuid-afrika"),
            "reason": "pillar anchor (topic cluster model)",
        }
    ]
    for other_cluster in pillar.get("clusters", []):
        if other_cluster.get("title") == candidate.get("cluster_title"):
            continue
        if len(internal_link_targets) >= 3:
            break
        internal_link_targets.append(
            {
                "label": other_cluster.get("title", ""),
                "url": f"{pillar.get('target_url_path', '/blogs/zuid-afrika')}/{_slugify(other_cluster.get('title', ''))}",
                "reason": "cluster sibling",
            }
        )

    # Extra product-link (CTA target)
    for p in linked_products:
        internal_link_targets.append(
            {
                "label": p["title"],
                "url": p["url"],
                "reason": "productpagina (CTA target)",
            }
        )

    # CTA
    brand_cta = {
        "naam": linked_products[0]["title"] if linked_products else pillar.get("title", ""),
        "streek": linked_products[0]["region"] if linked_products else "Zuid-Afrika",
        "wijn": linked_products[0]["title"] if linked_products else "",
    }
    from .utils import load_brand

    brand = load_brand()
    cta_template_raw = (brand.get("cta_voorbeelden") or ["{naam} staat in onze selectie."])[0]
    try:
        cta = cta_template_raw.format(**brand_cta)
    except (KeyError, IndexError):
        cta = cta_template_raw

    length_range = _parse_length(
        brand.get("artikel_structuur_default", {}).get("lengte_woorden_default", "800-1100")
    )

    return Brief(
        pillar=pillar_key,
        cluster_title=candidate["cluster_title"],
        keyword=candidate["keyword"],
        intent=candidate["intent"],
        target_word_count=length_range,
        angle=candidate.get("angle", ""),
        linked_products=linked_products,
        internal_link_targets=internal_link_targets,
        cta_template=cta,
        seo_signals=candidate.get("signals", {}),
        score=int(candidate.get("opportunity_score", candidate.get("score", 50))),
    )


def _parse_length(spec: str | list[int]) -> tuple[int, int]:
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return int(spec[0]), int(spec[1])
    if isinstance(spec, str) and "-" in spec:
        a, b = spec.split("-", 1)
        return int(a.strip()), int(b.strip())
    return 800, 1100


def _slugify(text: str) -> str:
    from slugify import slugify

    return slugify(text, max_length=60)


# ---------------------------------------------------------------------------
# Public: pick_next
# ---------------------------------------------------------------------------


def pick_next() -> Brief | None:
    """Selecteer het volgende te schrijven artikel."""
    published_kws = published_keywords()
    published_slug_set = published_slugs()
    coverage = pillar_coverage()

    # Prefer live keyword_bank als die data bevat
    bank_candidates = top_candidates(30)
    seo_clusters = cluster_candidates()

    # Bouw een kandidatenlijst op: geef voorrang aan cluster-candidates
    # zodat de topic-cluster-structuur klopt, maar her-scoor met live signals.
    merged: list[dict[str, Any]] = []

    for cluster in seo_clusters:
        slug = _slugify(cluster["cluster_title"])
        if cluster["keyword"].lower() in published_kws or slug in published_slug_set:
            continue

        # Zoek live signals voor dit keyword
        live = next(
            (k for k in bank_candidates if k.get("keyword", "").lower() == cluster["keyword"].lower()),
            None,
        )
        live_score = (live or {}).get("score", 0)
        base = int(cluster.get("opportunity_score", 50))
        gap = 1 - coverage.get(cluster["pillar"], 0)

        # Blend: 50% hand score, 30% live, 20% gap bonus
        final = round(base * 0.5 + live_score * 0.3 + gap * 100 * 0.2)
        merged.append({**cluster, "opportunity_score": final, "signals": (live or {}).get("signals", {})})

    if not merged:
        log.warning("Geen kandidaten beschikbaar — alles gepubliceerd of configuratie leeg.")
        return None

    merged.sort(key=lambda c: c["opportunity_score"], reverse=True)
    winner = merged[0]
    log.info(
        f"[bold]pick_next[/bold] -> '{winner['cluster_title']}' "
        f"(pillar={winner['pillar']}, score={winner['opportunity_score']})"
    )
    return build_brief(winner)


if __name__ == "__main__":
    brief = pick_next()
    if brief:
        print(brief.to_json())
    else:
        print("No candidates.")
