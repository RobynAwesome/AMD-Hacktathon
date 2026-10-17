# AG Ingress and CCP/PKA Receipt — Round 1

`I_AM_STATELESS_RENTER_NOT_LANDLORD`

- **Actor / renter:** AG (identity) · RTC Seat 10 · platform Google Antigravity · task role Lead Developer (scoped to this repository and branch `feat/goa-schema-foundation`).
- **Observed:** 2026-10-17 ~19:15 SAST.
- **Authority:** Product specification = the owner-issued Round 1 directive plus the GOA "Final Concept Note" (17 Oct 2026). Robyn's sign-off on that note is recorded in the note itself as an open decision; this receipt does not claim it.

## Sources inspected (summarised; no private content copied)

| Population | Locator | Result |
|---|---|---|
| Cloud GSMB | `RobynAwesome/Introduction-to-MCP` `AGENTS.md`, root `NOW.md` (head `0e5d23ca…`, committed 2026-10-12) | Read. Canonical entry order, renter assertion and receipt-before-closure rules applied. No GOA/AMD lane is recorded in `NOW.md`; this repository is a separate product. |
| Cloud GSMB | `MAIN-BRAIN/KC_AGENT_STATUS.md`, `CASSEY_AGENT_STATUS.md` | Read. Documentary status pages dated 2026-06-15. **No callable activation interface (CLI, endpoint, MCP tool) was found.** KC/Cassey activation: **NOT EXECUTED**. No approval from either is claimed. |
| Local GSMB | `OneDrive\...\Introduction to MCP\Schematics` | Directory accessible; top-level listing observed only. Not reconciled with Cloud. No content copied. |
| Google Drive | — | Not accessed. |

## Environment evidence

- Remote `RobynAwesome/AMD-Hacktathon` was empty (`isEmpty: true`, no branches) before this renter wrote.
- Python 3.12.13 (uv-managed), Pydantic 2.14.1, FastAPI 0.143.3, Node v24.14.1.
- AMD / Gemma provider: **no provider environment variables present** at ingress. Endpoint, model id and credentials are `UNKNOWN`; none are hard-coded.

## PKA

**Y — fixed invariants:** creation ≠ purchase intent; customer is author; AI cannot override customer choices or invent price/stock/delivery; every purchasable item traces to catalogue; unknown fails closed; unmet parts never shown as available; enquiry ≠ payment/order/reservation; every merchant interaction labelled demo; integer ZAR cents; GOA is isolated from Aya/Ayakha and KasiMargin.

**X — changeable implementation choices:** SQLite document store; tag-overlap matcher until embeddings are verified; rule-based interpretation fallback; SVG illustrations as catalogue imagery until licensed photos exist; fictional merchant names (owner decision still open).

**UNKNOWN:** Token Factory endpoint/model/credentials; AMD GPU availability for embeddings; owner choice of merchant names; whether Gemma vision tagging will run.

## Implementation decisions flagged for owner review

1. **Missing customer size.** The canonical prompt has no sizes. Size eligibility is therefore `UNKNOWN` and fails closed. Such parts show `NOT_ON_OFFER_YET` with reason `CUSTOMER_SIZE_REQUIRED`, the UI asks for the size, and these are **not** recorded as demand gaps (enforced in the `DemandGap` schema).
2. **Event year.** "12 December" resolves to the next occurrence (2026-12-12); the inference is recorded in `CreativeBrief.uncertainties`.
3. **Delivery rule.** Feasible only if `evaluated_on + delivery_lead_days < event_date` (arrival strictly before the event day).
4. **Internal status.** `PENDING_VERIFICATION` exists only before verification and is never rendered as available.
