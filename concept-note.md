# GOA Creative Commerce: Final Concept Note

17 October 2026 · Busi Ndlovu and Robyn · Live version: https://claude.ai/code/artifact/2dea3ccd-a878-463c-ba7e-913f3300f512

GOA lets a person imagine something freely, then shows them which parts real businesses can make happen today. The parts nobody sells are kept as unmet demand that merchants can see.

We build one experience for the AMD ACT III Reinvent Commerce track: a graduation outfit, matched against a small verified catalogue from three fictional merchants. It ends in one real commercial action, a merchant enquiry with a quote. The deadline is Sunday 18 October 2026 at 12:00 SAST.

This note turns Robyn's proposal of 17 October into the version we build. It is a joint GOA decision once Robyn signs off; Aya/Ayakha stays separate and out of this hackathon.

## Principles we keep

Robyn's two principles stay at the centre, unchanged.

- **Create without buying.** People can explore, remix and save without committing. Nothing they try is treated as intent to spend.
- **The person is the author.** Businesses contribute products, availability and expertise. They respond to the creation; they do not decide it.
- **Honest numbers.** Deterministic rules check price, size, stock and delivery date. We never show AI-generated figures as real results.

## Our answer: imagine freely, ground each part

We take Robyn's third option: creation starts free, and availability is checked part by part rather than up front.

| Robyn's question | Problem if chosen alone | What GOA does |
| --- | --- | --- |
| 1. Create freely first, and let businesses respond? | Many creations lead nowhere, so the commercial action is weak | The person creates freely; the AI splits the creation into parts |
| 2. Start from verified products only? | It becomes a catalogue with a chatbot, and loses the creative point | Each part is matched to verified items and checked by rules |

Each part ends in one of two states:

- **Available:** matched, priced and checked, so it can go into an enquiry right away.
- **Not on offer yet:** kept as unmet demand, shown to the person honestly and logged for merchants.

This is what lifts GOA above a shopping assistant. Imagination becomes a demand signal merchants can act on, without ever being treated as a purchase.

## How it works

One person, one merchant view, one action.

1. **Describe.** Thandi types: "Graduation in Cape Town on 12 December, outdoor, warm. Green, elegant but not formal, something I can wear again. Budget R2,500." She can add a reference photo.
2. **Interpret.** Gemma 4 on AMD turns this into a structured brief (occasion, date, budget, colours, formality, constraints) and splits the look into parts: dress or suit, shoes, outer layer, accessory.
3. **Match.** Each part is searched against the catalogue by meaning, not keywords.
4. **Verify.** Rules check every candidate: in stock, in her size, delivered before the date, and the full look within budget. Anything that fails is dropped, never shown.
5. **Compose and remix.** Thandi sees the look with prices, swaps parts, asks for alternatives, or saves it. A part with no good match shows as "not on offer yet".
6. **Act.** When ready, she sends one enquiry: the merchant receives the verified items, size, date and a quote request.
7. **Merchant gap view.** Merchants see what people asked for that nobody stocked. For example: "7 of 20 graduation looks wanted a green linen jacket. You stock none."

## Scope by Sunday 12:00

One experience done well beats three half-built ones.

| In | Out (roadmap only) |
| --- | --- |
| Graduation outfit, one person | Sport, itineraries and other experiences |
| 40 to 60 verified items from 3 fictional merchants, with photos, prices, sizes, stock and delivery days | Real merchant integrations or payments |
| Gemma brief and part split, meaning-based matching, rule checks | Social remixing and collaborative creation |
| Remix, swap and save | Accounts and long-term profiles |
| One action: merchant enquiry with quote request | Checkout and booking |
| Merchant gap view built from the evaluation briefs | Live demand dashboards across many merchants |
| English | Other languages (one isiXhosa example only if time allows) |

## Fit to the Reinvent Commerce brief

Each "good projects will show" point in the brief has a concrete answer.

| Brief asks for | GOA shows |
| --- | --- |
| A real customer or merchant problem | Customers can't find a look they have in mind by browsing static catalogues; merchants can't see demand for things they don't stock |
| A useful commercial action | A verified, priced merchant enquiry with quote request |
| Relevant recommendations or personalisation | Matched to stated style, budget, size and date, never to inferred clicks |
| A measurable effect | Valid compositions, steps to a sendable enquiry and captured gaps, against catalogue search (see How we measure) |
| Turning disconnected data into decisions | Joins customer intent, product data, stock and delivery into one decision for each side |

GOA makes no demand forecast, so the "no LLM-only forecasting" rule doesn't bite. Even so, every price, stock and delivery claim is checked by code, not by the model.

## Where AMD, the models and the rules work

The AI interprets and matches; code decides what is true.

| Step | Runs on | What it does |
| --- | --- | --- |
| Understand the brief | Gemma 4 31B via AMD Token Factory | Turns free text (and an optional photo) into a structured brief and a list of parts, as JSON |
| Tag the catalogue | Gemma 4 vision via Token Factory, once in advance | Describes each product photo (colour, fabric, style, formality) so matching uses what items look like |
| Match parts to items | Embedding model: on an AMD GPU if credits are live, otherwise on CPU (to confirm tonight) | Finds the closest items for each part by meaning |
| Verify | Plain Python rules | Stock, size, delivery before the event date, total within budget |
| Explain and remix | Gemma 4 via Token Factory | Says why each item fits, offers alternatives, writes the enquiry |
| Gap view | Plain Python | Counts unmatched parts across briefs and ranks them for merchants |

Using Gemma also enters us for the Google prize. The demo video shows the AMD call live, with its latency.

## How we measure, honestly

We test against a fair baseline and report only what we measured.

- **Test set:** 20 scripted creative briefs written before we tune anything, varied in budget, style and difficulty, including some that no merchant can fully serve.
- **Baseline:** plain keyword search over the same catalogue, the way a static store works.
- **Measures:**
    1. Valid composition rate: share of briefs that produce a complete look passing every rule.
    2. Grounding: share of shown items that exist in the catalogue and pass the rules. Target 100%, enforced by the validator.
    3. Steps to a sendable enquiry, counted per brief, GOA against baseline.
    4. Gaps captured: unmet parts logged, and whether they make sense on a quick manual check.
    5. Fit: the two of us blind-rate whether each look matches its brief, on a 1 to 5 scale.
- **What we will not claim:** revenue, conversion or retention uplift. Those need real users, and the slides say so.

## Build plan to the deadline

About 17 hours 45 minutes remain from 18:15 on Saturday. Feature freeze is at 06:00 so the morning is for evidence and submission.

| When (SAST) | Work | Done when |
| --- | --- | --- |
| Sat 18:15 to 19:00 | Sign off this note; split owners; Token Factory key; one Gemma call working | A brief comes back as valid JSON |
| Sat 19:00 to 21:00 | Catalogue of 40 to 60 items with photos; Gemma vision tags; embeddings | Every item tagged and searchable |
| Sat 21:00 to 00:30 | Brief to parts, matching, rule checks, compose and remix screen | A full look renders for one brief |
| Sun 00:30 to 02:30 | Enquiry action and merchant gap view | Enquiry sends; gap view shows counts |
| Sun 02:30 to 06:00 | Deploy, public repo with README, sleep in shifts | Live URL works from a phone |
| Sun 06:00 to 08:00 | Run the 20 briefs and the baseline; fill the results table | Numbers in the slides |
| Sun 08:00 to 10:30 | Slides, cover image, 2 to 3 minute demo video | Video uploaded |
| Sun 10:30 to 11:30 | Submit on lablab.ai | Submission confirmed |
| Sun 11:30 to 12:00 | Buffer only | Nothing new is started |

## Risks, fallbacks and open decisions

| Risk | Fallback |
| --- | --- |
| Token Factory slow, limited or down | Cache responses for the 20 briefs; show one live call in the video |
| No AMD GPU for embeddings | Run embeddings on CPU; AMD still powers every Gemma call |
| Gemma returns broken JSON | Schema check with one retry, then a plain fallback parser |
| It looks like a shopping chatbot | Lead the demo with the "not on offer yet" moment and the merchant gap view |
| Catalogue photos and licensing | Use our own photos or clearly licensed stock images, credited in the README |
| Running out of time | Cut remix first, then the photo input; never cut the enquiry or the gap view |

Open decisions for tonight:

- [ ] Robyn signs off on this version
- [ ] Who owns the backend, frontend, catalogue, evidence and video
- [ ] Product name stays GOA, or something else
- [ ] Names of the three fictional merchants
- [ ] Stack (suggested: Python backend, simple web front end, one host)
