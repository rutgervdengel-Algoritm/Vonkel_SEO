"""research.py — keyword + SERP onderzoek voor Vonkel.

Voert voor iedere seed keyword een live SERP-check uit en scoort de kans
voor ons. Geen verzonnen volumes: we gebruiken de structuur van de top-10
(aantal grote retailers vs. kleine boutiques, aantal unieke domeinen,
aanwezigheid van long-tail modifiers) als proxy voor concurrentie.

SERP-bron: DuckDuckGo HTML endpoint (geen API-key, tolerant voor light use).
Bij netwerkproblemen valt het script terug op een heuristische score zodat
de pipeline door kan draaien.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from .utils import (
    KEYWORDS_JSON,
    get_logger,
    load_products,
    load_seo_targets,
    now_iso,
    read_json,
    write_json,
)

log = get_logger("research")

# Grote NL wijn-retailers die bij aanwezigheid in top-10 de concurrentie-score
# omhoog drijven. Boutique-sites tellen als zwakkere concurrentie.
BIG_RETAILERS = {
    "gall.nl",
    "grandcruwijnen.nl",
    "henribloem.nl",
    "wijnbeurs.nl",
    "wijnvoordeel.nl",
    "bol.com",
    "ah.nl",
    "plus.nl",
    "jumbo.com",
    "drinkheroes.nl",
    "budgetwijnen.nl",
    "vinify.nl",
}

SERP_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# SERP fetching
# ---------------------------------------------------------------------------


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_serp(query: str) -> list[dict[str, str]]:
    """Return top results as list of {title, url, snippet}. Empty list on failure."""
    params = {"q": query, "kl": "nl-nl"}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9"}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.post(SERP_URL, data=params, headers=headers)
            resp.raise_for_status()
    except Exception as exc:  # pragma: no cover
        log.warning(f"SERP fetch failed for '{query}': {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict[str, str]] = []
    for r in soup.select("div.result")[:10]:
        a = r.select_one("a.result__a")
        snippet_el = r.select_one("a.result__snippet") or r.select_one(".result__snippet")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = a.get("href", "")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def score_competition_weakness(serp: list[dict[str, str]]) -> float:
    """0 = dichtgetimmerd door grote retailers, 1 = veel ruimte."""
    if not serp:
        return 0.5  # neutral fallback
    domains = [_domain(r["url"]) for r in serp if r.get("url")]
    big_hits = sum(1 for d in domains if d in BIG_RETAILERS)
    unique = len(set(domains))
    big_ratio = big_hits / max(len(domains), 1)
    # Meer unieke domeinen = gefragmenteerder veld = zwakker
    uniqueness = unique / 10
    return max(0.0, min(1.0, (1 - big_ratio) * 0.7 + uniqueness * 0.3))


def score_assortment_relevance(keyword: str, products: list[dict[str, Any]]) -> float:
    """1 = matcht direct met een wijn in onze selectie."""
    kw = keyword.lower()
    best = 0.0
    for p in products:
        hits = 0
        for field in ("title", "producer", "region", "sub_region", "grape", "style"):
            val = str(p.get(field) or "").lower()
            if not val:
                continue
            # Tokenize to avoid partial false positives ('pinot' in 'pinotage')
            tokens = re.findall(r"[a-zà-ÿ]+", val)
            for token in tokens:
                if len(token) >= 4 and token in kw:
                    hits += 1
        score = min(hits / 3.0, 1.0)
        if p.get("rare_in_nl"):
            score = min(score + 0.2, 1.0)
        best = max(best, score)
    return best


def score_long_tail(keyword: str) -> float:
    """Meer woorden + specifieker = meer long-tail potentie = hogere score."""
    words = keyword.split()
    n = len(words)
    if n <= 1:
        return 0.2
    if n == 2:
        return 0.5
    if n == 3:
        return 0.75
    return 0.9


def score_keyword(
    keyword: str,
    serp: list[dict[str, str]],
    products: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, Any]:
    competition = score_competition_weakness(serp)
    relevance = score_assortment_relevance(keyword, products)
    long_tail = score_long_tail(keyword)
    # pillar_coverage_gap wordt pas in de planner berekend; hier neutral
    pillar_gap = 0.5

    composite = (
        weights.get("competition_weakness", 0.4) * competition
        + weights.get("assortment_relevance", 0.35) * relevance
        + weights.get("long_tail_potential", 0.15) * long_tail
        + weights.get("pillar_coverage_gap", 0.10) * pillar_gap
    )
    # Naar 0-100 schaal
    score_100 = round(composite * 100)

    intent = infer_intent(keyword, serp)
    return {
        "keyword": keyword,
        "intent": intent,
        "score": score_100,
        "signals": {
            "competition_weakness": round(competition, 3),
            "assortment_relevance": round(relevance, 3),
            "long_tail_potential": round(long_tail, 3),
        },
        "serp_sample": serp[:5],
        "checked_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# Intent classification (cheap rule-based)
# ---------------------------------------------------------------------------

COMMERCIAL_MARKERS = ("kopen", "bestellen", "online", "prijs", "shop", "cadeau")
INFORMATIONAL_MARKERS = (
    "wat is",
    "uitleg",
    "verschil",
    "geschiedenis",
    "soorten",
    "gids",
    "uitgelegd",
    "uitleggen",
    "hoe",
    "waarom",
)
TRANSACTIONAL_MARKERS = ("beste", "review", "welke", "top 10", "aanbieding")


def infer_intent(keyword: str, serp: list[dict[str, str]]) -> str:
    kw = keyword.lower()
    if any(m in kw for m in COMMERCIAL_MARKERS):
        return "commercial"
    if any(m in kw for m in TRANSACTIONAL_MARKERS):
        return "transactional"
    if any(m in kw for m in INFORMATIONAL_MARKERS):
        return "informational"
    # SERP-based tiebreaker: veel shop-URLs -> commercial
    shop_hits = sum(1 for r in serp if "/product" in r.get("url", "") or "shop" in r.get("url", ""))
    if shop_hits >= 3:
        return "commercial"
    return "informational"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def gather_seeds() -> list[str]:
    seo = load_seo_targets()
    seeds: set[str] = set()

    for seed in seo.get("research_seeds", []):
        seeds.add(seed)

    # Pillar + cluster keywords als seeds meenemen
    for pillar in seo.get("pillars", {}).values():
        if pk := pillar.get("primary_keyword"):
            seeds.add(pk)
        for cluster in pillar.get("clusters", []):
            if ck := cluster.get("keyword"):
                seeds.add(ck)

    return sorted(seeds)


def run(limit: int | None = None, sleep_seconds: float = 1.5) -> dict[str, Any]:
    """Voer SERP research uit voor alle seeds, scoor en schrijf keyword_bank.json."""
    seo = load_seo_targets()
    products = load_products()
    weights = seo.get("scoring", {}).get("weights", {})

    seeds = gather_seeds()
    if limit:
        seeds = seeds[:limit]

    log.info(f"[bold]research[/bold]: {len(seeds)} seeds te onderzoeken")

    scored: list[dict[str, Any]] = []
    for i, seed in enumerate(seeds, 1):
        log.info(f"  [{i}/{len(seeds)}] '{seed}'")
        try:
            serp = fetch_serp(seed)
        except Exception as exc:
            log.warning(f"    fallback: {exc}")
            serp = []
        scored.append(score_keyword(seed, serp, products, weights))
        # Wees niet onbeleefd tegen de SERP-provider
        time.sleep(sleep_seconds)

    scored.sort(key=lambda k: k["score"], reverse=True)

    bank = {
        "_meta": {
            "generated_at": now_iso(),
            "source": "src.research via DuckDuckGo HTML",
            "scoring_scale": "0-100 (hoger = betere SEO-kans voor Vonkel)",
            "seed_count": len(seeds),
        },
        "keywords": scored,
    }
    write_json(KEYWORDS_JSON, bank)
    log.info(f"[green]research klaar[/green] — {len(scored)} kandidaten opgeslagen in {KEYWORDS_JSON.name}")
    return bank


def top_candidates(n: int = 10) -> list[dict[str, Any]]:
    bank = read_json(KEYWORDS_JSON)
    kws = bank.get("keywords", [])
    return sorted(kws, key=lambda k: k.get("score", 0), reverse=True)[:n]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=1.5)
    args = parser.parse_args()
    run(limit=args.limit, sleep_seconds=args.sleep)
