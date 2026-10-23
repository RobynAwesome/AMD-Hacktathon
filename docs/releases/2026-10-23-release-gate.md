# GOA release correction receipt — 23 October 2026

**Implemented, merged and deployed. Full release gate remains HOLD for AMD authentication and actual phone evidence.**

- [PR #4](https://github.com/RobynAwesome/AMD-Hacktathon/pull/4) merged into `main` at `e5193c51d929eeb2d81ae3acb06aee19c5c72975`.
- Public URL: https://goa-creative-commerce.vercel.app/
- Active production deployment: `dpl_AKUeur1pvVP9tXTUB5ombgyvGSec`, **READY**, FastAPI, `iad1`.
- Tested code tree: `867113ce2e9705d12fa2018cc53de171c2ea4f05`, identical between the tested correction commit and the merge.
- Production uses `GOA_MODE=submission`, `GOA_ALLOW_SAMPLE=1`, **`GOA_CACHE_ONLY=1`**.

## Corrections delivered

1. Failed temporary inbox writes return HTTP 503. Successful demo responses explicitly state `delivered=false`, temporary storage and no expected merchant reply. Seeded gaps identify `synthetic_seed`; newly logged demo gaps identify `transient_demo`. UI confirmations, demand view and inbox disclose these limits. Existing browser replay and `/tmp` storage are retained.
2. Submission validates provider, approved AMD endpoint and Gemma model before cache/fallback use. Heuristic/sample fallback requires explicit opt-in. Live, cached and template outcomes carry separate metadata; failures expose sanitized categories rather than provider bodies or secrets. Fallback provenance survives cold-state compose replay.
3. Web model steps share a maximum 40-second budget, including semaphore/rate waits, retries, backoff and cancellable HTTP transport. Vercel entrypoint duration is configured for 60 seconds; the API has a 5-second response margin. Startup quota polling no longer blocks requests. Per-process quota and limiter limits are disclosed.
4. Python minor version 3.12 and all direct/transitive dependencies are pinned. A compatible Pillow 12.3/Fastembed 0.9 set replaces the incompatible trial combination. README now links the existing live evaluation, retains its unfavourable parts-filled comparison, preserves Busi's attribution, and documents the demo boundaries. `scripts/release_smoke.py` records a sanitized journey.

## Validation

A fresh Python 3.12.14 environment installed all **49 locked packages** and passed dependency compatibility checks. **96 tests passed**, including cold replay, write failure, seed provenance, invalid provider/model/endpoint rejection, safe HTTP error reporting, retry deadlines, transport cancellation and limiter wait accounting. Frontend JavaScript syntax and Git diff checks passed. The preview and both production builds reached READY; the build selected Python 3.12 from `.python-version`. Runtime patch versions remain platform-managed.

The final anonymous production demo journey passed:

| Request | HTTP | Elapsed seconds |
| --- | ---: | ---: |
| GET `/api/config` | 200 | 8.43 |
| POST `/api/brief` | 200 | 8.56 |
| POST `/api/compose` | 200 | 8.28 |
| POST `/api/why/e765130bb30e` | 200 | 8.40 |
| POST `/api/enquiry` | 200 | 8.45 |
| GET `/api/enquiries` | 200 | 8.47 |
| GET `/api/gaps` | 200 | 8.60 |

The brief used the bundled Gemma cache. Why/enquiry used labelled templates with `quota_or_cache_only`. All three synthetic enquiries were immediately readable; this proves only that read-after-write. The gap response showed 12 correctly labelled synthetic seed rows. `/api/usage` confirmed `guard=cache_only`, `calls_live=0`, `persistence=transient_instance`, and limiter scope `process_only`.

The desktop browser independently prepared a request from a look built before redeployment. The browser replayed that look against the new deployment and displayed the corrected no-email/no-reply/temporary-state confirmation. The maker Demand and Quote requests views showed the corrected labels and records. This is desktop evidence, not mobile evidence.

## Remaining release blockers

The earlier bounded uncached production journey (same source SHA, deployment `dpl_93BdfPgSQaqHv993X9yKD3gs9FHB`) returned 200 throughout but exposed **`provider_http_401`** for fresh brief, why and enquiry inference. The brief used the explicit heuristic fallback; prose used templates. No successful fresh AMD inference was established. This failed evidence is preserved in the JSON receipt.

Production was then redeployed in cache-only mode without changing or exposing the credential. The encrypted key's existence does not prove rotation. The owner must rotate/replace `TOKEN_FACTORY_API_KEY` securely in Vercel Production, then confirm the update so a bounded uncached check can be run after cache-only is disabled. Never paste the key into chat, Git or receipts.

An actual public phone-browser brief → compose → enquiry result is still required. No physical mobile or mobile-emulation completion is claimed. Cross-instance durable inbox/gap statistics remain outside this explicitly transient demo release.

Filtered runtime logs contained no warning/error records; handled provider failures are nevertheless evidenced by the response trace. The provider's file-tree endpoint returned 404 for this Git deployment, so the configured duration is supported by source and successful build evidence rather than a retrieved function artifact. The existing 20-call live evaluation was not rerun. Issue #2 remains open; no RTC, KC or Cassey approval is claimed.

The companion `2026-10-23-release-gate.json` contains both sanitized production traces, deployment identifiers, source identity, validation and remaining actions. This receipt is committed separately from production code so recording it does not change the tested release SHA.
