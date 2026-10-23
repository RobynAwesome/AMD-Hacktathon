# GOA

Describe an outfit freely, from anywhere. Gemma 4 on AMD Token Factory turns it into a brief and parts. Each part is matched by meaning against merchants in seven shopping hubs, then plain Python rules check stock in your size, delivery before your date, and the total within budget with shipping included. Parts nobody can supply show as "not on offer yet" and feed a merchant gap view. One action: a quote request to the merchant.

AMD Developer Hackathon ACT III, Track 3: Reinvent Commerce. Scope: `concept-note.md`. Diagrams: `docs/architecture.html`.

GOA is co-created by Kholofelo Robyn Rababalela and Busi. Busi’s original implementation and source authorship are preserved.

## Release boundaries

This is a fictional-catalogue demo. Brief/look memory, `/tmp` files, quote requests, usage snapshots and rate limits are instance-local and transient on Vercel. State may reset or differ across reloads, instances and devices. The browser replays the brief and selected options to reconstruct a look; that is not durable storage. Requests are prepared in a temporary demo inbox: nothing is emailed and no merchant reply is expected. A failed inbox write returns HTTP 503. Gap rows identify `synthetic_seed` evaluation examples or `transient_demo` results; neither is verified market demand.

Vercel uses Python 3.12 (`.python-version`) and locked dependencies (`requirements.txt`, generated from `requirements.in`). The function entrypoint has a 60-second duration; API model operations share at most 40 seconds including quota waits, retries and transport, with a 5-second response margin. Cached, live, template and opted-in sample/heuristic outcomes are labelled separately; sanitized errors contain no provider bodies or credentials.

`GOA_ALLOW_SAMPLE=1` explicitly enables sample/heuristic brief fallback. `GOA_CACHE_ONLY=1` prevents live model calls. Shared-key rotation requires a separate secure environment update and non-secret receipt; the presence of a key is not proof it was rotated. The public demo has no globally shared limiter or durable inbox.

Release check (one synthetic journey; add `--fresh` only when shared API use is cleared):

```
python scripts/release_smoke.py --base https://goa-creative-commerce.vercel.app --sha <exact-deployed-sha> --out receipt.json
```

The receipt separates fresh inference, durable persistence, credential rotation and mobile evidence; a 200 demo journey does not silently clear those gates.

## What it does

- **Global search, your scope.** Near me, my region, or worldwide. Prices in your currency, shipping and arrival dates included.
- **Worth it from abroad.** With a narrower scope, GOA still shows up to two items from other hubs when they arrive in time and are cheaper or a closer match, within budget or up to 10% over (labelled, never added on its own).
- **Mirror.** `/?mirror=ZA,US,CN` runs one brief for shoppers in three places: each gets their own currency, season, delivery and gaps.
- **Merchant gap view and inbox.** What people wanted that nobody in reach stocks, and the quote requests sent.
- **Honest numbers.** The model never sets a price, date or stock level. Every shown item passes a grounding check (`goa/compose.py: validate_look`).

## Merchants (fictional)

Imbali House (Johannesburg, Black-owned: sculptural tailoring, Karoo mohair, silk printed from paintings by Johannesburg artists), Ridge & Rand (Durban leather: sneakers, loafers, bags), Fynbos Atelier (Cape Town linen, merino and illustrated prints), Ọ̀ṢỌ́ Studio (contemporary Lagos tailoring), Hudson & Pine (New York), Thornbury Lane (London), Via Seta (Milan), Lotus Thread (Shenzhen). 110 items. The African labels are modern design houses, not themed costume. Images are placeholders until licensed photos are added.

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

Any step can be routed to another provider (`goa/providers.json`: OpenAI-compatible endpoints or Claude via the Anthropic SDK) with `GOA_PROVIDER_<STEP>`. `GOA_MODE=submission` rejects a locked step unless its provider, model and endpoint match the approved Gemma/AMD route, before cache or fallback use. The Token Factory client retries 429 with backoff, since the team key is limited to 20 requests a minute in the recorded usage receipt.

## Evaluation

20 briefs written and frozen before tuning (`eval/briefs.json`, SHA-256 in `eval/briefs.freeze.json`), compared with plain keyword search over the same catalogue.

```
python eval/run_eval.py --offline   # reference parses, no model calls
python eval/run_eval.py             # live: shows the Token Factory calls needed, then --yes to run
```

The committed **live evaluation from 18 October 2026** is in [`eval/results_live.md`](eval/results_live.md) and JSON: 20 AMD/Gemma brief calls, 0 cached. Offline results remain separately available in [`eval/results_offline.md`](eval/results_offline.md). These synthetic evaluations do not prove deployed POST behaviour, mobile completion or customer outcomes.

| Live measure | GOA | Keyword search |
| --- | --- | --- |
| Valid complete composition | 55% | 30% |
| Grounding | 100% | 82% |
| Parts filled | 83% | 93% |
| Briefs reaching a sendable enquiry | 80% | 35% |
| Median steps to a sendable enquiry | 3 | 8 |
| Unmet synthetic catalogue parts | 12 | 0 |

The baseline fills more parts. Blind fit sheets are in `eval/blind/`. Do not rerun the live batch without approval for shared-key use; run it on a developer machine, outside web-request limits.

## Protecting the shared AMD quota

The team shares one Token Factory key (20 requests a minute per /v1/usage, 8 concurrent, a daily spend cap in USD).

- Successful model replies are cached on disk. On Vercel those caches are instance-local and may disappear; a rerun can incur a fresh call. `GOA_CACHE_ONLY=1` never calls the model.
- Our per-process limiter stays at 15 requests a minute and 4 in flight. Multiple instances do not share it, so it does not enforce a team-wide cap.
- `max_tokens` is capped per step (brief 1200, explain 600, enquiry 400, ideas 400, vision 300).
- Spend guard: under 25% of the daily cap left, only brief and enquiry call the model; under 10%, cache only. Shown in the page footer. Unknown quota does not establish available spend; use cache-only mode when the shared key is not cleared for use.
- `python scripts/usage.py` prints quota, usage and our recent calls. `cache/calls.jsonl` logs token counts, never prompt text.
- Big jobs (eval, vision tags) print the calls they need and wait for `--yes`.

## Catalogue

```
python catalogue/generate.py      # catalogue.json
python catalogue/placeholders.py  # placeholder images
python catalogue/vision_tag.py    # Gemma vision tags, real photos only, cached
python catalogue/embed.py         # embeddings.npy
```

## Honest numbers

Exchange rates are fixed in `goa/markets.json`, and converted prices are marked approx. Shoe and dress size conversions are approximate and listed in `goa/rules.py`. Merchant emails use example.com; enquiries go to a demo inbox and are never emailed. No revenue or conversion claims.
