# GOA BUILD WARS — FEP Architecture Reconciliation & Implementation Receipt

- **Identity:** AG
- **RTC Seat:** 10
- **Platform:** Google Antigravity
- **Role:** Lead Developer (GOA Build Wars — Round 1 + Pre-Checkpoint 2 Architectural Convergence)
- **Repository:** `https://github.com/RobynAwesome/AMD-Hacktathon`
- **Base Branch:** `main` (`5653c33ddb6b81b186e717f180866de2eb0bba72`)
- **Working Branch:** `feat/goa-schema-foundation`
- **Timestamp:** `2026-10-18T01:08:00+02:00` (SAST)

`I_AM_STATELESS_RENTER_NOT_LANDLORD`

---

## 0.Methodological Honesty & Governance Boundary

1. **FEP Method vs Runtime Engine:** This reconciliation applies the four Forensic Evolution Protocol (FEP) phases (**Traces**, **Reconstruction**, **Social/Technical Pattern**, **Self-Healing Evolution**) and E1–E4 evidence classification as an **analytical reconciliation method**. **The FEP runtime engine (`fep-core`) was NOT executed.**
2. **KC & Cassey Activation Status:** Neither KC nor Cassey was activated during this build. No external governance approval or `POC_VALIDATED` status is claimed (`CLEAR_PASS != POC_VALIDATED`).
3. **Private GSMB Boundary:** No private GSMB files, personal identifiers, or secrets were copied into the public GOA repository.
4. **Product Boundary:** GOA Creative Commerce is isolated from Aya/Ayakha and KasiMargin.

---

## 1. Source-to-Architecture Crosswalk (FEP Phase 1 & Phase 2)

| Layer | Document / Artifact | Role in Convergence | Key Contributions & Evolution |
|---|---|---|---|
| **Stage 1 — Origin** | Robyn's Proposal (*GOA: AI for Creative Commerce*, 17 Oct 2026) | Foundational product law | Established the two non-negotiable principles: (1) *Create without buying* (no implicit purchase intent), and (2) *The person is the author* (businesses contribute supply and expertise; they do not decide the creation). Framed the three design options and the two-sided business value loop. |
| **Stage 2 — Product Specification** | Joint Final Concept Note (*GOA Creative Commerce: Final Concept Note*, 17 Oct 2026, `@Dev @Mandi`) | Canonical product boundary (`Y` invariants) | Selected Option 3 (*imagine freely, ground each part*); locked one vertical slice (graduation outfit, 3 fictional merchants, 40–60 synthetic items, 1 authorized quote enquiry + merchant gap view); separated AI interpretation/matching/explanation from deterministic verification (`size`, `stock`, `delivery`, `price`, `budget`); defined the 20-brief frozen evaluation set vs plain keyword baseline. |
| **Stage 3 — Engineering Map** | Busi's 7-Page Architecture (*GOA System Architecture*, Figures 1–6) | Proposed modular engineering map | Contributed 6 architectural views: Fig 1 (Single FastAPI Host + Modular Boundaries), Fig 2 (Customer Creation Sequence), Fig 3 (Domain Model UML), Fig 4 (Deterministic Verification Pipeline), Fig 5 (Two-Sided Business Value Loop), Fig 6 (AMD Token Factory Integration). Introduced `Market/FX` and mood-photo extras that exceeded the locked 12-hour vertical slice. |
| **Stage 4 — Codebase Foundation** | AG Checkpoint 1 (`13c7ea1`) + Checkpoints 2A–5 (`86667c3`, `8d5d5b6`, `2bd4984`, `9f38044`) on `feat/goa-schema-foundation` | Verified implementation & JSON Schema contracts | Implemented strict Pydantic v2 contracts (`schemas/v1/`), applied FEP contract corrections (`86667c30995b166c3d9225e0c3d584435f984d82`), seeded 48 synthetic products (`8d5d5b6`), froze 20 evaluation briefs before matching (`2bd4984`), and built the deterministic verification engine, matcher, FastAPI vertical slice, and evaluation harness (`9f38044`). |

---

## 2. Canonical vs Proposed: ADOPT / RECONCILE / DEFER Matrix

| Architecture Element | Source | Decision | Implementation Path / Rationale |
|---|---|---|---|
| Single FastAPI host with modular internal packages | Busi Fig 1 + Concept Note | **ADOPT** | Implemented in `backend/goa/` (`schemas.py`, `config.py`, `rules.py`, `match.py`, `gaps.py`, `compose.py`, `brief.py`, `llm.py`, `store.py`, `evaluation.py`, `app.py`). |
| Strict isolation of AI operations from deterministic eligibility | Robyn + Concept Note + Busi Fig 4 | **ADOPT** | AI (`llm.py`) only interprets prompts and explains already-verified results. Deterministic Python (`rules.py`) decides `exists_in_catalogue`, `correct_part_type`, `size_available`, `stock_available`, `delivery_feasible`, `price_known`, and `budget_feasible`. |
| Two-sided business value loop (Customer Enquiry + Merchant Gap Signal) | Robyn + Concept Note + Busi Fig 5 | **ADOPT** | Customer side produces verified `QuoteEnquiry` (`customer_authorized=True`); supply-side `UnmetPart` records produce `DemandGap` records aggregated in `GET /api/v1/merchants/gaps`. |
| Frozen 20-brief evaluation vs plain keyword baseline | Concept Note | **ADOPT** | Frozen in `data/eval/briefs_v1.json` (SHA-256 `b52ec5e8ec858e39581b49ed7c2802f630721c03ab68eeefed12d89a63cd2baf`) before matching code was written; evaluated in `evidence/eval/evaluation_v1_results.json`. |
| Domain UML entities (`Brief`, `Part`, `CandidateMatch`, `Composition`, `MerchantEnquiry`, `UnmetDemandEntry`) | Busi Fig 3 vs AG `schemas.py` | **RECONCILE** | Mapped cleanly onto AG's versioned Pydantic v2 contracts (`CreativeBrief`, `RequestedPart`, `MatchCandidate`, `Composition`, `QuoteEnquiry`, `DemandGap`) without breaking `schema_version = "1.0.0"` or integer ZAR cents (`StrictInt`). |
| Missing customer input vs supply-side unmet demand | Busi Fig 2/4 vs AG Checkpoint 1 | **RECONCILE** | Added `PartStatus.NEEDS_CUSTOMER_INPUT` and `Composition.pending_input_parts` (`PendingInputPart`). Missing customer sizes/dates are never logged as merchant `DemandGap` records. |
| Token Factory environment variable contract | Busi Fig 6 vs AG directive | **RECONCILE** | Unified in `backend/goa/config.py`: accepts `GOA_LLM_BASE_URL` / `GOA_LLM_API_KEY` / `GOA_LLM_MODEL` and aliases `TOKEN_FACTORY_BASE_URL`, `TOKEN_FACTORY_API_KEY`, `GEMMA_MODEL`, `RADEON_API_KEY`. Never fabricates live endpoints. |
| Multi-market (`ZA/US/GB`), FX conversion, and international delivery | Busi Fig 3 (`Market`) | **DEFER** | Out of scope for the locked Cape Town / South Africa graduation vertical slice; all prices remain integer ZAR cents (`currency="ZAR"`). |
| Mood-photo upload & "Give me ideas" inspiration workflows | Busi Fig 2 | **DEFER** | Deferred per Concept Note (*"Keep only if core is done by 06:00"*); text-first graduation outfit flow is prioritized and verified. |
| Additional industries, social remixing, and live merchant payment/reservation | Concept Note ("What we leave out") | **DEFER** | Explicitly out of hackathon scope. |

---

## 3. E1–E4 Forensic Evidence Classification

| Class | Definition | Concrete Items in GOA Build Wars |
|---|---|---|
| **E1 — Testimony / Narrative** | Statements in proposals, concept notes, or prompts that are not self-proving | - Narrative illustration *"6 of 20 briefs asked for a green linen jacket"* in the Concept Note (treated as an example format, **not** hardcoded; actual computed result from `briefs_v1.json` is `5 of 20 briefs`).<br>- Prompt claims of live AMD inference without environment credentials. |
| **E2 — Verified Artifacts & Receipts** | Cryptographically or deterministically verified repository files and test outputs | - `schemas/v1/*.schema.json` + `schemas/v1/examples/*.example.json` (`scripts/export_schemas.py --check` passing).<br>- `data/merchants.json` (3 fictional merchants) & `data/products.json` (48 synthetic products, 239 variants) + 48 original SVGs (`frontend/catalogue/*.svg`).<br>- `data/eval/briefs_v1.json` + `evidence/eval/briefs_v1.freeze.json` (LF SHA-256 `b52ec5e8ec858e39581b49ed7c2802f630721c03ab68eeefed12d89a63cd2baf`).<br>- `evidence/eval/evaluation_v1_results.json` & JUnit XML test receipts (`59 passed`). |
| **E3 — Bounded Inference** | Model or parser decomposition of customer text into candidate parts and attributes | - `CreativeBrief.requested_parts`, `PartOrigin.INFERRED_COMPLEMENT` (e.g. inferred shoes/outer layer/accessory for a graduation look), and `CreativeBrief.uncertainties`. Explicitly tagged with `interpretation_source` (`GEMMA_4_AMD` vs `RULE_BASED_FALLBACK`). |
| **E4 — Explicit Unknowns** | Missing facts that must fail closed or remain unfabricated | - Missing customer sizes in Thandi's raw prompt (`sizes={}`, `MandatoryConstraints.size=None` -> `CheckState.UNKNOWN` -> `PartStatus.NEEDS_CUSTOMER_INPUT`).<br>- Price-on-request catalogue item (`prd_fyn_012`, `price_cents=None` -> `CheckState.UNKNOWN`).<br>- Live AMD Token Factory credentials (`GOA_LLM_*` / `TOKEN_FACTORY_*` not set in current local environment -> reported as `provider_configured=False`).<br>- Blind 1–5 human fit scores (`blind_human_fit_scores_status="PENDING_HUMAN_REVIEW_BY_ROBYN_AND_BUSI"`). |

---

## 4. Self-Healing Evolution: Contract Corrections (A–E) & Regression Tests

All five architectural corrections mandated in Forge's handoff were implemented in commit `86667c30995b166c3d9225e0c3d584435f984d82` and locked with 17 regression tests in `tests/test_contract_corrections.py`:

- **Correction A — Thandi Canonical Fixture (`backend/goa/examples.py`, `schemas/v1/examples/creative_brief.example.json`):**
  - Removed invented sizes (`M`, `UK6`) from Thandi's raw prompt fixture (`sizes={}`, `MandatoryConstraints.size=None` on sized parts) and set all part statuses on `CreativeBrief` to `PartStatus.PENDING_VERIFICATION`.
  - Added a separate follow-up fixture (`example_brief_followup()` -> `schemas/v1/examples/creative_brief.followup.example.json`) representing the state after Thandi supplies her dress/outer size (`M`) and shoe size (`UK6`).
  - Added a `@model_validator` on `CreativeBrief` rejecting any `RequestedPart` whose `mandatory_constraints.size` is not backed by `brief.sizes`.
- **Correction B — Server-Side Quote Enquiry Revalidation (`backend/goa/schemas.py`, `backend/goa/rules.py`):**
  - Strengthened `ItemRevalidation` (`verified_unit_price_cents`, `verified_stock_quantity`, `verification_result`) and `ValidationReceipt` (`compute_digest()` SHA-256 over canonical JSON).
  - Enforced in `QuoteEnquiry` that every line item has a matching `ItemRevalidation`, belongs to `enquiry.merchant_id`, matches the verified catalogue price and stock, and has a valid `receipt_digest`.
  - Enforced in `CreateEnquiryRequest` (`extra="forbid"`) that API clients cannot submit a pre-fabricated `validation_receipt`.
- **Correction C — Missing Customer Input vs Supply-Side Unmet Demand (`backend/goa/schemas.py`, `backend/goa/compose.py`, `backend/goa/gaps.py`):**
  - Added `PartStatus.NEEDS_CUSTOMER_INPUT` and `Composition.pending_input_parts: list[PendingInputPart]`.
  - `UnmetPart` rejects `CUSTOMER_INPUT_REASONS` (`CUSTOMER_SIZE_REQUIRED`, `EVENT_DATE_REQUIRED`, `BUDGET_REQUIRED`), and `DemandGap` rejects `CUSTOMER_INPUT_REASONS`.
- **Correction D — Single Token Factory Config Contract (`backend/goa/config.py`):**
  - Resolved `GOA_LLM_*` and `TOKEN_FACTORY_*` / `GEMMA_MODEL` / `RADEON_API_KEY` aliases in one place without inventing dummy URLs or keys.
- **Correction E — Original Artwork Licensing Declaration (`backend/goa/schemas.py`, `scripts/seed_catalogue.py`):**
  - Changed `image_licence` from `CC0-1.0` to `PROJECT_ORIGINAL_ARTWORK_LICENCE_PENDING_OWNER` across all 48 generated SVG illustrations (`frontend/catalogue/*.svg`) and `data/products.json` until Robyn and Busi select a repo-wide licence.

---

## 5. AMD / Gemma Integration & Matching Honesty Report

1. **Configuration Boundary (`backend/goa/config.py`):**
   - Inspects `GOA_LLM_BASE_URL` (or `TOKEN_FACTORY_BASE_URL`), `GOA_LLM_API_KEY` (or `TOKEN_FACTORY_API_KEY` / `RADEON_API_KEY`), and `GOA_LLM_MODEL` (or `GEMMA_MODEL`).
   - Current environment state: **Unconfigured (`is_configured = False`)**. No live AMD Token Factory endpoint or API key was present in the environment.
2. **Schema-Validated Adapter, 1-Retry & Fallback (`backend/goa/llm.py`):**
   - When configured, `interpret_brief` calls `${base_url}/chat/completions`, validates the JSON output against `CreativeBrief`, retries **at most once** (`attempts=2`) on invalid JSON or schema violation, and falls back to `parse_brief_rule_based` (`InterpretationSource.RULE_BASED_FALLBACK`) if the provider is unconfigured or fails twice.
   - Proven by deterministic mock transport tests in `tests/test_verification_engine.py`:
     - `test_llm_adapter_falls_back_when_unconfigured`
     - `test_llm_adapter_retries_once_on_invalid_json_then_succeeds`
     - `test_llm_adapter_falls_back_after_two_invalid_outputs`
3. **Candidate Matching Method (`backend/goa/match.py`):**
   - Active GOA matcher is **`MatchMethod.TAG_OVERLAP`** (structured colour/material/formality/keyword/reuse overlap with deterministic merchant-cohesion tie-breaking).
   - Plain baseline matcher is **`MatchMethod.KEYWORD_BASELINE`** (raw surface token match against product title and description).
   - `MatchMethod.EMBEDDING` fails closed unless a real `EmbeddingScorer` callable is provided (`test_embedding_method_without_scorer_raises_honestly`). We do **not** claim neural embedding search where `TAG_OVERLAP` ran.

---

## 6. Frozen 20-Brief Evaluation & Test Evidence

- **Frozen Evaluation Set:** `data/eval/briefs_v1.json`
- **Freeze Receipt:** `evidence/eval/briefs_v1.freeze.json`
- **LF-Normalised SHA-256:** `b52ec5e8ec858e39581b49ed7c2802f630721c03ab68eeefed12d89a63cd2baf` (`briefs_hash_verified = True`)
- **Pre-Freeze Commit Head:** `86667c30995b166c3d9225e0c3d584435f984d82`
- **Evaluation Results Artifact:** `evidence/eval/evaluation_v1_results.json`

| Metric (20 Frozen Graduation Briefs) | GOA (`TAG_OVERLAP`) | Plain Keyword Baseline (`KEYWORD_BASELINE`) |
|---|---|---|
| Verified Complete Outfits (`VERIFIED_COMPLETE`) | **4 / 20 (20.0%)** | 3 / 20 (15.0%) |
| Verified Partial Outfits (`VERIFIED_PARTIAL`) | **12 / 20 (60.0%)** | 10 / 20 (50.0%) |
| Verified Partial or Complete Rate | **16 / 20 (80.0%)** | 13 / 20 (65.0%) |
| Empty Compositions (`EMPTY`, e.g. missing customer size/date) | 4 / 20 (20.0%) | 7 / 20 (35.0%) |
| Catalogue Grounding Rate (all selected items pass all 7 checks) | **100.0% (48 / 48 items)** | **100.0% (32 / 32 items)** |
| Mean Steps to Sendable Enquiry | **3.38 steps** | 5.92 steps |
| Supply-Side Demand Gaps Logged (excluding missing customer input) | **18 gaps** | 24 gaps |
| Top Aggregated Unmet Demand Signal | **`5 of 20 briefs requested a green linen jacket that was not available (NO_MATCHING_PRODUCT).`** | `5 of 20 briefs requested a green linen jacket that was not available (NO_MATCHING_PRODUCT).` |
| Blind Human Fit Score (1–5) | `PENDING_HUMAN_REVIEW_BY_ROBYN_AND_BUSI` | `PENDING_HUMAN_REVIEW_BY_ROBYN_AND_BUSI` |

---

## 7. Remaining Open Owner Decisions

1. **Repository & Original Artwork Licence:** All 48 generated product SVGs (`frontend/catalogue/*.svg`) carry `image_licence = "PROJECT_ORIGINAL_ARTWORK_LICENCE_PENDING_OWNER"`. Robyn and Busi must confirm the final SPDX licence identifier if they wish to publish under an open licence.
2. **Live AMD Token Factory Credentials:** To record live `GEMMA_4_AMD` model-call receipts against an AMD endpoint before the 12:00 SAST deadline, supply `GOA_LLM_BASE_URL` (or `TOKEN_FACTORY_BASE_URL`), `GOA_LLM_API_KEY` (or `TOKEN_FACTORY_API_KEY`), and `GOA_LLM_MODEL` (or `GEMMA_MODEL`) in the runtime environment.
3. **Blind 1–5 Fit Scoring:** `evidence/eval/evaluation_v1_results.json` leaves `blind_human_fit_score_robyn` and `blind_human_fit_score_busi` as `null` (`PENDING_HUMAN_REVIEW_BY_ROBYN_AND_BUSI`) for human scoring of the 20 outputs.

---

## 8. Next Admissible Action

1. If AMD Token Factory / Gemma endpoint credentials become available before feature freeze, set `GOA_LLM_BASE_URL`, `GOA_LLM_API_KEY`, and `GOA_LLM_MODEL` and run a live interpretation capture to append an E2 live provider receipt.
2. Have Robyn and Busi review the 20 composed outputs in `evidence/eval/evaluation_v1_results.json` and the interactive UI (`uv run uvicorn goa.app:app --reload`) before deciding on any pull request or merge to `main`.
