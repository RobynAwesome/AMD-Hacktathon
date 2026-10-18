# GOA

Describe an outfit freely, from anywhere. Gemma 4 on AMD Token Factory turns it into a brief and parts. Each part is matched by meaning against merchants in seven shopping hubs, then plain Python rules check stock in your size, delivery before your date, and the total within budget with shipping included. Parts nobody can supply show as "not on offer yet" and feed a merchant gap view. One action: a quote request to the merchant.

AMD Developer Hackathon ACT III, Track 3: Reinvent Commerce. Scope: `concept-note.md`. Diagrams: `docs/architecture.html`.

## What it does

- **Global search, your scope.** Near me, my region, or worldwide. Prices in your currency, shipping and arrival dates included.
- **Worth it from abroad.** With a narrower scope, GOA still shows up to two items from other hubs when they arrive in time and are cheaper or a closer match, within budget or up to 10% over (labelled, never added on its own).
- **Mirror.** `/?mirror=ZA,US,CN` runs one brief for shoppers in three places: each gets their own currency, season, delivery and gaps.
- **Merchant gap view and inbox.** What people wanted that nobody in reach stocks, and the quote requests sent.
- **Honest numbers.** The model never sets a price, date or stock level. Every shown item passes a grounding check (`goa/compose.py: validate_look`).

## Merchants (fictional)

Imbali House (Johannesburg, Black-owned, shweshwe tailoring and Ndebele-inspired beadwork), Adire Atelier (Lagos, adire indigo and Ankara), Fynbos Atelier (Cape Town), Hudson & Pine (New York), Thornbury Lane (London), Via Seta (Milan), Lotus Thread (Shenzhen). 105 items. Images are placeholders until licensed photos are added.

## Run

```
pip install -r requirements.txt
cp .env.example .env              # TOKEN_FACTORY_API_KEY (team key, rc-...)
python scripts/check_llm.py        # routing per step and prize-lock status
python scripts/check_llm.py --models
uvicorn app.main:app --reload      # http://localhost:8000
pytest
```

Offline demo without a key: `GOA_ALLOW_SAMPLE=1 uvicorn app.main:app`. The Thandi brief then uses a hand-written sample, labelled on screen as "sample brief (no model call)".

## Models and AMD

| Step | Default | Locked for prizes |
| --- | --- | --- |
| brief, vision, explain, enquiry | Gemma-4-31B-IT on AMD Token Factory | yes: AMD Track 3 and the Google Gemma prize |
| ideas | Gemma-4-31B-IT on AMD Token Factory | no |
| embeddings | bge-small via fastembed on CPU (Token Factory has no embeddings endpoint) | no |

Any step can be routed to another provider (`goa/providers.json`: OpenAI-compatible endpoints or Claude via the Anthropic SDK) with `GOA_PROVIDER_<STEP>`. `GOA_MODE=submission` refuses to start if a locked step leaves Token Factory. The Token Factory client retries 429 with backoff, since the team key is limited to 30 requests a minute.

## Catalogue

```
python catalogue/generate.py      # catalogue.json
python catalogue/placeholders.py  # placeholder images
python catalogue/vision_tag.py    # Gemma vision tags, real photos only, cached
python catalogue/embed.py         # embeddings.npy
```

## Honest numbers

Exchange rates are fixed in `goa/markets.json`, and converted prices are marked approx. Shoe and dress size conversions are approximate and listed in `goa/rules.py`. Merchant emails use example.com; enquiries go to a demo inbox and are never emailed. No revenue or conversion claims.
