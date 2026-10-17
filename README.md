# GOA

Describe an outfit freely. Gemma 4 on AMD Token Factory turns it into a brief and parts, each part is matched by meaning against a small verified catalogue, and plain Python rules check stock, size, delivery and budget. Parts nobody sells show as "not on offer yet" and feed a merchant gap view.

AMD Developer Hackathon ACT III, Track 3: Reinvent Commerce. Scope: `concept-note.md`. Diagrams: `docs/architecture.html`.

## Run

```
pip install -r requirements.txt
cp .env.example .env          # Token Factory base URL, key, model
python scripts/check_llm.py   # lists model IDs, set GEMMA_MODEL
python scripts/parse_brief.py --market ZA
pytest
```

## Catalogue

Three fictional merchants (Cape Town, New York, London), 48 items. Rebuild with:

```
python catalogue/generate.py      # catalogue.json
python catalogue/placeholders.py  # placeholder images
python catalogue/vision_tag.py    # Gemma vision tags, real photos only, cached
python catalogue/embed.py         # embeddings.npy
```

Images are placeholders. Replace `catalogue/images/<id>.png` with licensed photos and set `image_credit` in `generate.py`.

## Honest numbers

Exchange rates are fixed in `goa/markets.json` and prices converted with them are marked approx. Merchant emails use example.com. No revenue or conversion claims.
