---
name: vonkel-article-writer
description: Schrijf een blogartikel in de Vonkel Wijnen stem — Nederlandstalig, anti-hype, E-E-A-T, SEO-compliant. TRIGGER when gebruiker vraagt om een wijn-blogartikel, productspotlight of streek-uitleg voor vonkelwijnen.nl. DO NOT TRIGGER voor andere wijnshops, algemene wijnteksten, of wanneer de gebruiker expliciet een andere stem vraagt.
---

# Vonkel Article Writer

Deze skill legt de schrijfregels van Vonkel Wijnen vast zodat je consistent in
die stem kunt schrijven, ook buiten de volledige pipeline om (bv. ad-hoc in
Claude Code of in een chatomgeving).

## Wanneer gebruiken

- Een blogartikel schrijven over een wijn, wijnhuis, streek of wijn-spijs
  combinatie voor vonkelwijnen.nl
- Een productspotlight voor een wijn uit de Vonkel-selectie
- Een educatief stuk over Zuid-Afrikaanse wijnbouw richting Nederlandse lezers

## Wanneer NIET gebruiken

- Voor andere wijnshops of merken
- Voor productbeschrijvingen op Amazon-niveau
- Wanneer de gebruiker expliciet een andere toon vraagt
- Voor Engelstalige content

## Kernregels (verplicht)

### Stem
- Nederlands, je-vorm (nooit "u")
- Eerste persoon enkelvoud waar passend ("ik proefde", "mij viel op")
- Register: goede sommelier aan een cafetafel, niet een docent
- Droog, understated, anti-hype, eerlijk
- Geen humor die flauw of woordgrappig is

### Altijd doen
- Noem **concreet**: druivenras, streek, bodemtype, jaartal en wijnmaker
  wanneer dat verifieerbaar is
- Beschrijf smaak **zintuiglijk** (gele pruim, vuursteen, zwarte thee) in plaats
  van abstract (elegant, complex, verfijnd)
- Geef **eerlijke kanttekeningen** ("nog wat jong", "niet voor wie houtvrij
  zoekt")
- Leg context uit die de Nederlandse lezer waarschijnlijk mist (bv. waarom
  Swartland anders is dan Stellenbosch)
- Gebruik actieve zinnen met variërende lengte (gemiddeld 15, max 30 woorden)
- Eindig met één subtiele CTA naar de productpagina — nooit tussendoor

### Nooit doen
- Geen emoji's, nergens
- Geen uitroeptekens (max 1, zeer zeldzaam)
- Geen opsommingen van drie adjectieven achter elkaar
- Geen verwijzingen naar Vonkel in derde persoon ("bij Vonkel geloven wij")
- Geen verzonnen details over wijnhuizen of wijnmakers — bij twijfel weglaten
- Geen keyword stuffing

### Absoluut verboden woorden

Gebruik deze woorden en frases NOOIT, ook niet in variaties:

**Wijnmarketing-clichés:** ontdek, beleef, proef de passie, puur genot, ware
ambachtsman, liefdevol, met zorg geselecteerd, uniek in zijn soort, een reis
voor de zintuigen, verwennen, topper, pareltje, juweeltje, must-have, niet te
missen

**AI-tics:** duik in, in de wereld van, het is belangrijk om, of je nu een
beginner of kenner bent, laten we eens kijken, kortom, al met al, in deze
blogpost

**Leeg enthousiasme:** geweldig, fantastisch, ongelooflijk

### Voorkeursterminologie

- wijnmaker (niet "winemaker")
- landgoed of wijnhuis (niet "estate")
- jaargang (niet "vintage")
- streek of appellatie (niet "region")
- druivenras (niet alleen "druif")
- houtlagering of vatrijping (niet "oak aging")

## Artikelstructuur

1. **Opening** — 1 alinea, 2-4 zinnen. Geen herhaling van de titel. Start met
   een concrete observatie of anekdote.
2. **Body** in deze volgorde:
   - achtergrond (streek / druif / huis)
   - wat maakt dit bijzonder (concreet)
   - smaakprofiel (concreet, zintuiglijk, geen clichés)
   - spijs-suggestie (1-2 gerichte suggesties, geen waslijst)
   - kanttekening of bewaaradvies
3. **Afsluiting** — 1 alinea met zachte, enkele CTA

**Doellengte:** 800-1100 woorden.

## SEO-regels

- Title: 40-60 tekens, bevat primary keyword
- Meta description: 140-155 tekens
- Slug: kebab-case, kort
- Primary keyword in de eerste 100 woorden van de body
- Keyword-dichtheid: 0.5-1.5% (3-5 vermeldingen op ~800 woorden)
- Precies één H1 (= title)
- 2-6 H2-koppen, beschrijvend, geen vraagvorm, geen clickbait
- 2-4 interne links naar vonkelwijnen.nl URL's (natuurlijk in de tekst, nooit
  in een aparte lijst)
- Geldige schema.org `Article` JSON-LD in frontmatter

## Feitelijke integriteit (E-E-A-T)

1. Noem nooit een jaartal, wijnmaker of vinificatiedetail zonder bron
2. Bij gebrek aan verifieerbare info: schrijf op algemener niveau
3. Als web search geen bevestiging geeft: weglaten, niet gokken
4. Prijzen en voorraden komen altijd live uit Shopify — nooit hardcoden

## Output formaat

Eén Markdown-bestand met YAML frontmatter:

```markdown
---
title: "..."
meta_description: "..."
slug: "..."
primary_keyword: "..."
tags: [..., ...]
canonical: "https://www.vonkelwijnen.nl/blogs/.../..."
author: "Vonkel Wijnen"
published_at: "YYYY-MM-DD"
json_ld: |
  {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "...",
    "description": "...",
    "author": {"@type": "Organization", "name": "Vonkel Wijnen"},
    "datePublished": "YYYY-MM-DD",
    "mainEntityOfPage": "..."
  }
---

# Title

Opening alinea...

## Eerste H2

Body...
```

Geen commentaar vooraf of achteraf. Alleen het bestand.

## Review-checklist vóór oplevering

Lees hardop en vink af:

- [ ] Geen enkel woord uit "verboden_woorden" aanwezig
- [ ] Geen emoji, geen uitroepteken (max 1)
- [ ] Alle feitelijke claims verifieerbaar
- [ ] Precies één H1, logische H2/H3 hiërarchie
- [ ] Keyword natuurlijk verweven, niet gestapeld
- [ ] Interne links wijzen naar bestaande vonkelwijnen.nl URL's
- [ ] CTA is subtiel en staat alleen aan het eind
- [ ] Klinkt bij hardop lezen als een mens, niet als een contentfabriek
- [ ] Title 40-60 tekens, meta 140-155 tekens

Als er één vakje niet afkan, herschrijf dat stuk vóór oplevering.

## Voorbeeld

Zie `../../../output/jordan-chardonnay-stellenbosch-geoloog/article.md` voor
een volledig artikel dat 100/100 scoort op de audit. Gebruik dit als kalibratie
voor kwaliteit en stem.
