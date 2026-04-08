# Vonkel Content Agent

Een lokaal draaiende SEO content pipeline voor [vonkelwijnen.nl](https://www.vonkelwijnen.nl).
Doel: wekelijks een SEO-geoptimaliseerd blogartikel genereren, in de Vonkel-stem,
E-E-A-T-compliant, met interne links en schema.org markup, en als **draft** in
Shopify klaar zetten voor redactie.

Geen publicatie gebeurt automatisch. Je reviewt altijd zelf.

---

## Hoe het werkt

```
research  ─►  plan  ─►  write  ─►  audit  ─►  publish (draft)
  │              │         │          │            │
  ▼              ▼         ▼          ▼            ▼
keyword     content    Claude    on-page     Shopify
bank        brief      API       SEO check   Admin API
```

1. **`research.py`** — haalt live SERP op voor alle seeds in `config/seo_targets.yaml`
   (via DuckDuckGo HTML, geen API-key nodig), classificeert intent en scoort
   iedere kandidaat op concurrentie-zwakte, assortiments-relevantie en long-tail
   potentie. Output: `data/keyword_bank.json`.
2. **`planner.py`** — kiest het volgende artikel uit de cluster-candidates in
   `seo_targets.yaml`, dedupt tegen `data/published.json`, blendt handmatige
   opportunity-score met live SERP-signalen en pillar coverage-gap. Output: een
   `Brief` (pillar, keyword, intent, angle, interne links, CTA).
3. **`writer.py`** — bouwt een system prompt uit `config/brand.yaml`, stuurt de
   brief naar Claude (Sonnet 4.5 of Opus 4.6), parseert het antwoord als
   YAML frontmatter + Markdown body en schrijft naar `output/<slug>/`.
4. **`seo_audit.py`** — scoort het artikel (0-100) op 15+ on-page checks:
   title/meta lengte, keyword placement en dichtheid, H1/H2 structuur,
   verboden woorden, JSON-LD, interne links, emoji's, alt-teksten. Faalt de
   pipeline onder 85.
5. **`publisher.py`** — post als **draft** naar de Shopify Blog API. In dry-run
   schrijft hij alleen de payload lokaal naar `shopify_payload.json`.
6. **`pipeline.py`** — orkestreert alles met uitgebreide logging en is
   idempotent (dedup via `published.json`; hervatbaar met `--resume`).

---

## Setup

Eenmalig:

```bash
cd vonkel-content-agent
uv sync                  # installeert deps uit pyproject.toml
cp .env.example .env     # vul daarna ANTHROPIC_API_KEY en Shopify velden in
```

Vul in `.env`:

| Variabele | Betekenis |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude API sleutel |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` (sneller/goedkoper) of `claude-opus-4-6` (scherper) |
| `SHOPIFY_STORE` | bv. `vonkelwijnen.myshopify.com` |
| `SHOPIFY_ADMIN_TOKEN` | Admin API token uit een custom app |
| `SHOPIFY_BLOG_ID` | ID van de blog waarin drafts moeten landen |
| `AGENT_DEFAULT_DRY_RUN` | `true` (aanrader) — nooit per ongeluk live |
| `AGENT_MIN_SEO_SCORE` | drempel waaronder de pipeline faalt, default 85 |

---

## Wekelijkse workflow

```bash
# 1. Sync producten uit Shopify (doe dit zodra je assortiment wijzigt)
uv run python -m src.publisher --sync-products

# 2. Genereer 1 artikel als draft (default dry-run = alleen lokaal)
uv run python -m src.pipeline --count 1

# 3. Open output/<slug>/article.md en lees het hardop
#    Kijk ook naar output/<slug>/audit.md voor de SEO-score

# 4. Tevreden? Publiceer als echte draft in Shopify:
uv run python -m src.pipeline --resume output/<slug> --no-dry-run

# 5. In Shopify Admin > Blogs > [blog]: review, eventueel editen, en pas
#    daar zelf op 'Publish'. De agent zet nooit iets live.
```

Alternatieve flows:

```bash
# Meerdere artikelen in één run
uv run python -m src.pipeline --count 3

# Overslaan van research (gebruik de bestaande keyword_bank)
uv run python -m src.pipeline --count 1 --skip-research

# Alleen research draaien (bv. handmatig om keyword_bank.json bij te werken)
uv run python -m src.research

# Alleen audit op een reeds gegenereerd artikel
uv run python -m src.seo_audit output/<slug>
```

---

## Configuratie

### `config/brand.yaml` — de merkstem

Dit bestand wordt één-op-één als system prompt in Claude geladen. Wat je hier
verandert, merk je direct in de volgende generatie.

Praktische tuning:

- **Stem scherper?** Voeg extra items toe aan `voice.attitude` of aan `dont`.
- **Een specifieke frase komt terug uit de AI?** Zet hem in `verboden_woorden`.
  De audit zal generaties met die frase hard afkeuren.
- **Andere artikelstructuur?** Pas `artikel_structuur_default.body` aan en de
  `lengte_woorden_default`.
- **Andere CTA-stijl?** Herschrijf `cta_voorbeelden`.

Na iedere wijziging kun je gewoon opnieuw genereren — geen extra build-stap.

### `config/seo_targets.yaml` — topic clusters

De agent gebruikt het **topic cluster model**: brede pillars met long-tail
clusters eronder, die naar elkaar linken.

Een nieuwe pillar toevoegen:

```yaml
pillars:
  nieuwe_pillar_key:
    title: "Pillar titel voor mensen"
    slug: pillar-slug
    coverage_target: 8            # aantal artikelen dat je uiteindelijk wilt
    description: >
      Korte uitleg wat deze pillar dekt en voor welke zoeker.
    primary_keyword: "hoofd keyword"
    search_intent: informational   # of commercial / transactional
    target_url_path: /blogs/nieuwe-pillar
    clusters:
      - title: "Eerste cluster-titel (mag ook ruw zijn)"
        keyword: "concreet long-tail keyword"
        intent: informational
        opportunity_score: 75      # 0-100, je eigen inschatting
        angle: "wat is de haak / inzicht"
        linked_products: [handle-uit-products-json]
```

De planner pikt automatisch op nieuwe pillars. Er is geen register dat je
apart moet bijwerken.

Een nieuwe cluster onder een bestaande pillar toevoegen: kopieer een bestaand
`clusters:`-item en vul in. De `opportunity_score` is jouw inschatting van
hoe aantrekkelijk dit keyword voor ons is; `research.py` voegt later live
signalen toe en de planner blendt beide.

### `data/products.json`

De ingevoerde seed heeft 9 placeholder-entries op basis van de wijnen die in
de brief genoemd zijn (Jordan, Creation, Mullineux, Sadie, Alheit, Storm,
Kanonkop, Boekenhoutskloof, Graham Beck). **Draai één keer**
`uv run python -m src.publisher --sync-products` om de echte lijst uit
Shopify op te halen. Doe dit telkens als het assortiment wijzigt.

---

## Output formaat

Per artikel krijg je:

```
output/<slug>/
├── article.md              # YAML frontmatter + Markdown body
├── meta.json               # gestructureerd: title, meta, tags, brief, JSON-LD
├── audit.md                # leesbare SEO-score + fixes
├── audit.json              # machine-leesbare audit
└── shopify_payload.json    # (alleen bij --dry-run) de exacte payload die
                            #  naar Shopify zou gaan
```

---

## Voorbeeldartikel

`output/jordan-chardonnay-stellenbosch-geoloog/` bevat een volledig
handgegenereerd voorbeeld in het exacte formaat dat `writer.py` produceert.
Audit-score: **100/100**. Bedoeld om de kwaliteitsbar zichtbaar te maken
vóór je de eerste echte API-run doet.

Open `article.md` en lees hem hardop. Als je iets hoort dat niet klopt
met de stem die je wilt, pas `brand.yaml` aan voordat je de pipeline draait.

---

## Herbruikbare skill

`skills/vonkel-article-writer/` bevat een herbruikbare Claude Code skill die
de brand-voice en structurele regels encapsuleert. Je kunt die skill ook
buiten deze pipeline gebruiken (bv. in Claude Code) om ad-hoc artikelen te
schrijven zonder de hele pipeline te draaien.

---

## Harde veiligheden

- Publicatie is altijd als **draft**. De code zet `published: false` in elke
  Shopify payload; er is geen flag om dat om te zeilen.
- `AGENT_DEFAULT_DRY_RUN=true` in `.env.example`. Je moet bewust
  `--no-dry-run` meegeven om daadwerkelijk iets naar Shopify te sturen.
- De audit faalt de pipeline onder score 85. Voor publicatie (ook als draft)
  moet een artikel alle verboden woorden vermijden, een geldige JSON-LD hebben
  en alle structurele checks halen.
- `research.py` gebruikt alleen webbronnen, nooit verzonnen volumes.
- `writer.py` is gebonden aan `feitelijke_integriteit.regels` in `brand.yaml`:
  geen jaartallen, wijnmakers of vinificatiedetails zonder bron.

---

## Troubleshooting

**"Research faalt / geen resultaten"** — DuckDuckGo HTML kan rate-limiten.
Verhoog `--sleep` of voer `--skip-research` en werk `keyword_bank.json`
handmatig bij.

**"Audit score te laag"** — lees `audit.md`, fix het meest zware check, en
draai opnieuw. De belangrijkste wegingen liggen op keyword placement,
verboden woorden en interne links.

**"Claude geeft onbruikbare output"** — controleer of `brand.yaml` geen
tegenstrijdige regels bevat, en probeer `CLAUDE_MODEL=claude-opus-4-6`.

---

## Bekende zwakke punten

Deze staan óók in de handover-samenvatting. Voor je live gaat:

1. **Products.json is een seed.** De 9 wijnen zijn op basis van publieke
   bronnen ingevoerd, niet uit jouw Shopify. Draai de sync voordat je
   serieus genereert, anders staan er foute producer-links in de artikelen.
2. **Geen externe keyword-volumes.** De agent gebruikt SERP-structuur als
   proxy voor concurrentie, maar weet niks van exacte zoekvolumes. Voor
   prioritering op schaal zou je later een Ahrefs/Semrush/DataForSEO
   connector kunnen toevoegen.
3. **Geen image generation.** Featured images worden nog niet gegenereerd;
   de Shopify payload bevat alleen tekst. Voeg zelf een image-service toe
   of upload ze handmatig bij review.
