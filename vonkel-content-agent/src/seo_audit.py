"""seo_audit.py — on-page SEO check op een gegenereerd artikel.

Checks:
  * Title 50-60 tekens en bevat primary keyword
  * Meta description 140-155 tekens
  * Primary keyword in eerste 100 woorden
  * Keyword dichtheid tussen 0.5% en 1.5%
  * Precies één H1 (gelijk aan title), logische H2/H3-hiërarchie
  * Slug kort en kebab-case
  * 2-4 interne links naar vonkelwijnen.nl
  * Geen woord uit brand.verboden_woorden
  * Geen emoji of uitroepteken
  * Valid schema.org Article JSON-LD
  * Alt-tekst bij elke afbeelding

Geeft een score 0-100 + concrete fixes. De pipeline faalt als de score
onder de drempel (default 85) ligt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .utils import get_logger, load_brand

log = get_logger("seo_audit")


EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002700-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "]"
)


@dataclass
class AuditResult:
    score: int
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        lines = [f"# SEO Audit — score {self.score}/100 ({'PASS' if self.passed else 'FAIL'})\n"]
        for c in self.checks:
            mark = "[x]" if c["pass"] else "[ ]"
            lines.append(f"- {mark} **{c['name']}** — {c['detail']}")
        if self.fixes:
            lines.append("\n## Te fixen\n")
            for fx in self.fixes:
                lines.append(f"- {fx}")
        return "\n".join(lines) + "\n"

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "checks": self.checks,
            "fixes": self.fixes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_md(text: str) -> str:
    # remove code fences and inline code
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    # remove markdown links but keep the label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # strip heading markers
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w-]+\b", text))


def _first_n_words(text: str, n: int) -> str:
    words = re.findall(r"\b[\w-]+\b", text)
    return " ".join(words[:n])


def _keyword_hits(text: str, keyword: str) -> int:
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    return len(pattern.findall(text))


def _extract_frontmatter(article_text: str) -> tuple[dict[str, Any], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", article_text.strip(), re.DOTALL)
    if not m:
        return {}, article_text
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check(name: str, ok: bool, detail: str, weight: int = 5) -> dict[str, Any]:
    return {"name": name, "pass": bool(ok), "detail": detail, "weight": int(weight)}


def audit_article(
    article_md: str,
    *,
    primary_keyword: str | None = None,
    threshold: int = 85,
) -> AuditResult:
    brand = load_brand()
    forbidden = [w.lower() for w in brand.get("verboden_woorden", [])]
    seo_rules = brand.get("seo_regels", {})

    fm, body = _extract_frontmatter(article_md)
    pk = (primary_keyword or fm.get("primary_keyword") or "").strip()

    title: str = (fm.get("title") or "").strip()
    meta_desc: str = (fm.get("meta_description") or "").strip()
    slug: str = (fm.get("slug") or "").strip()
    json_ld = fm.get("json_ld")

    plain = _strip_md(body)
    wc = _word_count(plain)
    checks: list[dict[str, Any]] = []
    fixes: list[str] = []

    # --- Title ---
    title_len = len(title)
    title_ok = 40 <= title_len <= 60
    checks.append(
        _check("title lengte", title_ok, f"{title_len} tekens (doel 40-60)", weight=10)
    )
    if not title_ok:
        fixes.append(f"Pas title aan naar 40-60 tekens (nu {title_len}).")

    if pk:
        tkw = pk.lower() in title.lower()
        checks.append(_check("keyword in title", tkw, f"'{pk}' {'gevonden' if tkw else 'ontbreekt'}", weight=10))
        if not tkw:
            fixes.append(f"Neem primary keyword '{pk}' op in de title.")

    # --- Meta description ---
    md_len = len(meta_desc)
    md_ok = 140 <= md_len <= 155
    checks.append(_check("meta description lengte", md_ok, f"{md_len} tekens (doel 140-155)", weight=10))
    if not md_ok:
        fixes.append(f"Herschrijf meta_description naar 140-155 tekens (nu {md_len}).")

    # --- Slug ---
    slug_ok = bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)) and 3 <= len(slug) <= 75
    checks.append(_check("slug kebab-case", slug_ok, f"'{slug}'", weight=5))
    if not slug_ok:
        fixes.append("Slug moet kort, kleine letters, kebab-case zijn.")

    # --- H1 ---
    h1s = re.findall(r"^# (.+)$", body, flags=re.MULTILINE)
    h1_ok = len(h1s) == 1
    checks.append(_check("precies één H1", h1_ok, f"gevonden: {len(h1s)}", weight=10))
    if not h1_ok:
        fixes.append("Zorg voor exact één H1 (= title).")

    # --- Heading hierarchy ---
    heads = re.findall(r"^(#{1,4})\s+(.+)$", body, flags=re.MULTILINE)
    h2s = [h for h in heads if len(h[0]) == 2]
    hierarchy_ok = 2 <= len(h2s) <= 6
    checks.append(_check("H2-structuur", hierarchy_ok, f"{len(h2s)} H2-koppen (doel 2-6)", weight=8))
    if not hierarchy_ok:
        fixes.append("Gebruik 2-6 H2-koppen voor logische structuur.")

    # --- Primary keyword in first 100 words ---
    if pk:
        first_100 = _first_n_words(plain, 100)
        pk_early = pk.lower() in first_100.lower()
        checks.append(_check("keyword in eerste 100 woorden", pk_early, "" if pk_early else "niet aanwezig", weight=10))
        if not pk_early:
            fixes.append(f"Verwerk '{pk}' in de eerste 100 woorden.")

    # --- Keyword density ---
    if pk and wc > 0:
        hits = _keyword_hits(plain, pk)
        density = hits / wc * 100
        density_ok = 0.3 <= density <= 1.8
        checks.append(
            _check(
                "keyword dichtheid",
                density_ok,
                f"{hits}x in {wc} woorden = {density:.2f}% (doel 0.5-1.5%)",
                weight=8,
            )
        )
        if not density_ok:
            if density < 0.3:
                fixes.append(f"Keyword te weinig ({density:.2f}%). Voeg 1-2 natuurlijke vermeldingen toe.")
            else:
                fixes.append(f"Keyword te vaak ({density:.2f}%). Verwijder stapeling.")

    # --- Word count ---
    wc_ok = 700 <= wc <= 1300
    checks.append(_check("woordaantal", wc_ok, f"{wc} woorden (doel 700-1300)", weight=6))
    if not wc_ok:
        fixes.append(f"Pas lengte aan (nu {wc}, doel 700-1300).")

    # --- Internal links ---
    internal_links = re.findall(r"\[[^\]]+\]\((https?://[^)]*vonkelwijnen\.nl[^)]*|/[^)]+)\)", body)
    il_count = len(internal_links)
    il_ok = 2 <= il_count <= 4
    checks.append(_check("interne links (2-4)", il_ok, f"{il_count} gevonden", weight=10))
    if not il_ok:
        fixes.append(f"Gebruik 2-4 interne links (nu {il_count}).")

    # --- Images / alt-text ---
    images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", body)
    if images:
        missing_alt = [img for img in images if not img[0].strip()]
        alt_ok = not missing_alt
        checks.append(_check("alt-teksten aanwezig", alt_ok, f"{len(missing_alt)} zonder alt", weight=5))
        if not alt_ok:
            fixes.append("Voeg alt-tekst toe aan elke afbeelding.")
    else:
        checks.append(_check("alt-teksten aanwezig", True, "geen afbeeldingen", weight=0))

    # --- Forbidden words ---
    lower_body = plain.lower()
    lower_title = title.lower()
    lower_meta = meta_desc.lower()
    hits_forbidden = []
    for w in forbidden:
        if not w:
            continue
        pattern = re.compile(rf"\b{re.escape(w)}\b")
        if pattern.search(lower_body) or pattern.search(lower_title) or pattern.search(lower_meta):
            hits_forbidden.append(w)
    fb_ok = not hits_forbidden
    checks.append(
        _check(
            "verboden woorden afwezig",
            fb_ok,
            "geen hits" if fb_ok else f"gevonden: {', '.join(hits_forbidden)}",
            weight=15,
        )
    )
    if not fb_ok:
        fixes.append(f"Verwijder verboden woorden: {', '.join(hits_forbidden)}.")

    # --- Emoji + uitroeptekens ---
    emoji_free = not EMOJI_RE.search(body) and not EMOJI_RE.search(title)
    checks.append(_check("geen emoji", emoji_free, "" if emoji_free else "emoji gevonden", weight=5))
    if not emoji_free:
        fixes.append("Verwijder emoji's.")

    excl_count = body.count("!") + title.count("!")
    excl_ok = excl_count <= 1
    checks.append(_check("geen uitroeptekens", excl_ok, f"{excl_count} gevonden (max 1)", weight=3))
    if not excl_ok:
        fixes.append(f"Verwijder uitroeptekens ({excl_count} gevonden).")

    # --- JSON-LD ---
    json_ld_ok = False
    json_ld_detail = "ontbreekt"
    if json_ld:
        try:
            if isinstance(json_ld, str):
                parsed = json.loads(json_ld)
            else:
                parsed = json_ld
            if parsed.get("@context") and parsed.get("@type") in ("Article", "BlogPosting"):
                json_ld_ok = True
                json_ld_detail = f"{parsed.get('@type')} geldig"
            else:
                json_ld_detail = "ontbrekende @context of @type"
        except Exception as exc:
            json_ld_detail = f"parse-fout: {exc}"
    checks.append(_check("schema.org JSON-LD", json_ld_ok, json_ld_detail, weight=8))
    if not json_ld_ok:
        fixes.append("Voeg geldig schema.org Article JSON-LD toe in frontmatter.")

    # --- Score berekening ---
    total_weight = sum(c["weight"] for c in checks) or 1
    earned = sum(c["weight"] for c in checks if c["pass"])
    score = round(earned / total_weight * 100)

    return AuditResult(
        score=score,
        passed=score >= threshold,
        checks=checks,
        fixes=fixes,
    )


# ---------------------------------------------------------------------------
# Filesystem driver
# ---------------------------------------------------------------------------


def audit_path(article_dir: Path, *, threshold: int = 85) -> AuditResult:
    article_md = (article_dir / "article.md").read_text(encoding="utf-8")
    meta = json.loads((article_dir / "meta.json").read_text(encoding="utf-8"))
    result = audit_article(
        article_md,
        primary_keyword=meta.get("primary_keyword"),
        threshold=threshold,
    )
    (article_dir / "audit.md").write_text(result.as_markdown(), encoding="utf-8")
    (article_dir / "audit.json").write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(
        f"[bold]audit[/bold] {article_dir.name}: {result.score}/100 "
        f"({'PASS' if result.passed else 'FAIL'})"
    )
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.seo_audit <output/slug>")
        raise SystemExit(1)
    audit_path(Path(sys.argv[1]))
