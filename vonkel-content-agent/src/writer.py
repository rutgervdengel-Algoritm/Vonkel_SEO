"""writer.py — genereert het artikel via de Claude API.

Laadt brand.yaml als system prompt en bouwt een user-prompt uit de Brief.
Output is een compleet artikel-bestand (YAML frontmatter + Markdown body)
dat door seo_audit.py gecontroleerd wordt.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .planner import Brief
from .utils import OUTPUT_DIR, env, get_logger, load_brand, now_iso

log = get_logger("writer")


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt(brand: dict[str, Any]) -> str:
    """Zet brand.yaml om in een stringent system prompt."""
    b = brand["brand"]
    voice = brand["voice"]
    do = brand["do"]
    dont = brand["dont"]
    forbidden = brand["verboden_woorden"]
    terms = brand["voorkeurs_terminologie"]
    style = brand["stijl_regels"]
    structure = brand["artikel_structuur_default"]
    integrity = brand["feitelijke_integriteit"]["regels"]
    seo_rules = brand["seo_regels"]

    return f"""Je bent de hoofdredacteur van {b['name']} ({b['url']}), een kleine Nederlandse
boutique die zich volledig richt op Zuid-Afrikaanse wijnen.

POSITIONERING
{b['positioning'].strip()}

DOELGROEP
{b['audience'].strip()}

STEM
- Persoon: {voice['person']} (nooit "u", nooit "wij als Vonkel team")
- Perspectief: {voice['perspective']}
- Register: {voice['register']}
- Houding: {', '.join(voice['attitude'])}
- Humor: {voice['humor']}

DOEN (verplicht)
{chr(10).join(f"- {x}" for x in do)}

NIET DOEN (absolute no-go's)
{chr(10).join(f"- {x}" for x in dont)}

ABSOLUUT VERBODEN WOORDEN EN FRASES (gebruik NOOIT, ook niet in variaties)
{', '.join(forbidden)}

VOORKEURSTERMINOLOGIE (Nederlandse vakterm ipv Engels)
{chr(10).join(f"- {k}: {v}" for k, v in terms.items())}

STIJLREGELS
- Gemiddelde zinslengte: ~{style['zinslengte_gemiddeld_woorden']} woorden
- Maximale zinslengte: {style['max_zin_woorden']} woorden
- Max alinealengte: {style['alinea_max_zinnen']} zinnen
- Tussenkopjes: {style['tussenkopjes_stijl']}
- Opsommingstekens: {style['gebruik_opsommingstekens']}
- Cijfers: {style['cijfers']}

ARTIKELSTRUCTUUR
- Opening: {structure['opening']}
- Body (in volgorde): {', '.join(structure['body'])}
- Afsluiting: {structure['afsluiting']}
- Doellengte: {structure['lengte_woorden_default']} woorden

FEITELIJKE INTEGRITEIT (E-E-A-T)
{chr(10).join(f"- {r}" for r in integrity)}

SEO-REGELS
- Title: max {seo_rules['title_max_tekens']} tekens
- Meta description: {seo_rules['meta_description_tekens']} tekens
- Primary keyword in eerste 100 woorden: {seo_rules['keyword_in_eerste_100_woorden']}
- Keyword-dichtheid: {seo_rules['keyword_dichtheid_percent']}%
- Interne links: {seo_rules['interne_links_min']}-{seo_rules['interne_links_max']}
- Alt-teksten verplicht voor elke afbeelding

OUTPUT FORMAAT
Je levert ÉÉN Markdown-bestand met:
1. YAML frontmatter tussen --- met velden: title, meta_description, slug,
   primary_keyword, tags, canonical, author, published_at, json_ld (een valid
   schema.org Article JSON-LD als string).
2. Na de frontmatter: de body in Markdown met precies één H1 (gelijk aan title),
   gevolgd door H2/H3. Geen emoji's, geen uitroeptekens.
3. Geen uitleg, geen commentaar, geen "hier is het artikel". Alleen het bestand.
"""


# ---------------------------------------------------------------------------
# User prompt (brief -> instructions)
# ---------------------------------------------------------------------------


def build_user_prompt(brief: Brief) -> str:
    products_block = ""
    if brief.linked_products:
        products_block = "\n\nWIJN(EN) UIT ONZE SELECTIE DIE IN DIT ARTIKEL RELEVANT ZIJN:\n"
        for p in brief.linked_products:
            bits = [
                f"- {p['title']} ({p.get('producer', '')})",
                f"  Wijnmaker: {p.get('winemaker', 'onbekend')}",
                f"  Streek: {p.get('region', '')}"
                + (f" / {p['sub_region']}" if p.get("sub_region") else ""),
                f"  Druivenras: {p.get('grape', '')}",
                f"  Stijl: {p.get('style', '')}",
                f"  URL: {p.get('url', '')}",
            ]
            if p.get("notes"):
                bits.append(f"  Context/notes: {p['notes']}")
            products_block += "\n".join(bits) + "\n"

    links_block = "\n".join(
        f"- [{link['label']}]({link['url']}) — {link['reason']}"
        for link in brief.internal_link_targets
    )

    wc_min, wc_max = brief.target_word_count
    return f"""BRIEF

Pillar: {brief.pillar}
Cluster-titel (richtlijn, niet verplicht letterlijk): {brief.cluster_title}
Primary keyword (natuurlijk verwerken, 3-5 keer max): {brief.keyword}
Search intent: {brief.intent}
Doelomvang: {wc_min}-{wc_max} woorden

ANGLE
{brief.angle}
{products_block}
INTERNE LINKS (2-4 stuks, natuurlijk in de tekst, nooit in lijsten):
{links_block}

VERPLICHTE CTA AAN HET EIND (subtiel, één alinea, niet schreeuwerig):
Basis: {brief.cta_template}
Je mag deze herformuleren binnen de merkstem, maar niet drie varianten erbij.

TAAK
Schrijf het volledige artikel nu, volgens alle regels uit je system prompt.
Zorg dat:
- De title max 60 tekens is en de primary keyword bevat
- De meta_description 140-155 tekens is
- De slug kort kebab-case is
- Er precies één H1 is (= title)
- Er 2-4 H2-koppen zijn, geen vraagvorm
- De primary keyword in de eerste 100 woorden voorkomt
- Er 2-4 interne links zijn, zoals hierboven gespecificeerd
- Er eindigt met exact één subtiele CTA
- De json_ld een valide schema.org Article JSON-LD string is

Geef alleen het bestand terug. Geen uitleg vooraf of achteraf.
"""


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------


def call_claude(system: str, user: str, model: str, max_tokens: int = 4000) -> str:
    from anthropic import Anthropic

    api_key = env("ANTHROPIC_API_KEY", required=True)
    client = Anthropic(api_key=api_key)

    log.info(f"Calling {model} (max_tokens={max_tokens})...")
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # Concat text blocks
    out = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    return out.strip()


# ---------------------------------------------------------------------------
# Parse + persist
# ---------------------------------------------------------------------------


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_article(raw: str) -> tuple[dict[str, Any], str]:
    """Split frontmatter YAML from body Markdown."""
    raw = raw.strip()
    # Strip code fences if the model wrapped output in ```markdown ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)

    m = FRONTMATTER_RE.match(raw)
    if not m:
        raise ValueError("Artikel mist geldige YAML frontmatter (--- ... ---).")
    fm_raw, body = m.group(1), m.group(2).strip()
    fm = yaml.safe_load(fm_raw) or {}
    return fm, body


def write_outputs(brief: Brief, frontmatter: dict[str, Any], body: str) -> Path:
    slug = frontmatter.get("slug") or "ongetiteld"
    slug = re.sub(r"[^a-z0-9-]", "", slug.lower())
    target_dir = OUTPUT_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    article_md = target_dir / "article.md"
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    article_md.write_text(f"---\n{fm_yaml}\n---\n\n{body}\n", encoding="utf-8")

    meta_path = target_dir / "meta.json"
    meta = {
        "title": frontmatter.get("title"),
        "meta_description": frontmatter.get("meta_description"),
        "slug": slug,
        "primary_keyword": frontmatter.get("primary_keyword"),
        "tags": frontmatter.get("tags", []),
        "canonical": frontmatter.get("canonical"),
        "json_ld": frontmatter.get("json_ld"),
        "pillar": brief.pillar,
        "cluster_title": brief.cluster_title,
        "brief": asdict(brief),
        "generated_at": now_iso(),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")

    log.info(f"[green]artikel geschreven[/green] -> {article_md.relative_to(OUTPUT_DIR.parent)}")
    return target_dir


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def write_article(brief: Brief, *, model: str) -> Path:
    brand = load_brand()
    system = build_system_prompt(brand)
    user = build_user_prompt(brief)
    raw = call_claude(system, user, model=model)
    fm, body = parse_article(raw)
    return write_outputs(brief, fm, body)


if __name__ == "__main__":
    from .planner import pick_next

    brief = pick_next()
    if not brief:
        raise SystemExit("Geen brief beschikbaar")
    write_article(brief, model=env("CLAUDE_MODEL") or "claude-sonnet-4-5")
