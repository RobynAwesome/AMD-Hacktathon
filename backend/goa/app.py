"""FastAPI application for GOA Creative Commerce.

Exposes the customer creation flow (Describe -> Interpret -> Match -> Verify ->
Compose -> Remix/Save -> Authorize Quote Enquiry) and the demo merchant experience
(fictional merchant quote inbox + data-driven unmet-demand dashboard), and serves
the mobile-responsive frontend and original SVG product illustrations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from goa.brief import apply_customer_sizes
from goa.compose import compose_outfit, swap_part_in_composition
from goa.config import DATA_DIR, ROOT_DIR, load_llm_config
from goa.evaluation import run_frozen_evaluation
from goa.examples import CANONICAL_PROMPT
from goa.gaps import aggregate_demand_gaps
from goa.llm import explain_verified_composition, interpret_brief
from goa.rules import ENGINE_VERSION, VerificationError, revalidate_and_build_enquiry
from goa.schemas import (
    SCHEMA_VERSION,
    GapSourceType,
    MatchMethod,
    PartType,
)
from goa.store import GoaStore

REFERENCE_DATE = date(2026, 10, 18)
FRONTEND_DIR = ROOT_DIR / "frontend"


class InterpretBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_prompt: str = Field(min_length=1, default=CANONICAL_PROMPT)
    sizes: dict[PartType, str] = Field(default_factory=dict)
    match_method: MatchMethod = MatchMethod.TAG_OVERLAP


class UpdateSizesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sizes: dict[PartType, str]
    match_method: MatchMethod = MatchMethod.TAG_OVERLAP


class RemixSwapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part_id: str
    product_id: str
    variant_id: str | None = None


class CreateEnquiryRequest(BaseModel):
    """Clients cannot supply `validation_receipt` (`extra='forbid'`); server issues it."""

    model_config = ConfigDict(extra="forbid")
    composition_id: str
    merchant_id: str
    customer_authorized: bool
    part_ids: list[str] | None = None
    notes: str | None = None


def create_app(store: GoaStore | None = None) -> FastAPI:
    app = FastAPI(
        title="GOA Creative Commerce API",
        version=SCHEMA_VERSION,
        description="Imagine freely. Ground every part. Surface unmet demand.",
    )
    db = store or GoaStore(DATA_DIR / "goa_runtime.sqlite3")
    app.state.store = db

    # Seed evaluation demand gaps from the frozen 20-brief evaluation set on startup.
    eval_report, eval_gaps = run_frozen_evaluation(db.list_products())
    db.save_demand_gaps(eval_gaps)
    app.state.eval_report = eval_report

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        cfg = load_llm_config()
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "llm_provider": cfg.public_summary(),
            "merchant_count": len(db.list_merchants()),
            "product_count": len(db.list_products()),
            "canonical_prompt": CANONICAL_PROMPT,
            "disclaimers": [
                "All merchants, inventory and prices are fictional demo data.",
                "Creation, remixing and saving do not constitute purchase intent.",
                "Quote enquiries are simulated demo interactions, not orders, reservations or payments.",
            ],
        }

    @app.get("/api/v1/catalogue")
    def get_catalogue() -> dict[str, Any]:
        return {
            "merchants": [m.model_dump(mode="json") for m in db.list_merchants()],
            "products": [p.model_dump(mode="json") for p in db.list_products()],
        }

    @app.post("/api/v1/briefs/interpret")
    def post_interpret_brief(req: InterpretBriefRequest) -> dict[str, Any]:
        if req.match_method == MatchMethod.EMBEDDING:
            raise HTTPException(
                status_code=400,
                detail="Neural embedding matcher is not enabled in this runtime; use TAG_OVERLAP or KEYWORD_BASELINE.",
            )
        short = uuid.uuid4().hex[:8]
        brief_id = f"brf_{short}"
        session_id = f"ses_{short}"
        brief, llm_receipt = interpret_brief(
            req.raw_prompt,
            brief_id=brief_id,
            session_id=session_id,
            reference_date=REFERENCE_DATE,
            customer_sizes=req.sizes or None,
        )
        products = db.list_products()
        comp, candidates, gaps = compose_outfit(
            brief,
            products,
            evaluated_on=REFERENCE_DATE,
            method=req.match_method,
            composition_id=f"cmp_{short}",
            gap_source_type=GapSourceType.DEMO_SESSION,
        )
        db.save_brief(brief)
        db.save_composition(comp)
        db.save_demand_gaps(gaps)

        return {
            "brief": brief.model_dump(mode="json"),
            "composition": comp.model_dump(mode="json"),
            "candidates_by_part": {
                pid: [c.model_dump(mode="json") for c in clist]
                for pid, clist in candidates.items()
            },
            "explanations": explain_verified_composition(brief, comp),
            "llm_receipt": llm_receipt.to_dict(),
            "match_method_used": req.match_method.value,
        }

    @app.post("/api/v1/briefs/{brief_id}/sizes")
    def post_update_sizes(brief_id: str, req: UpdateSizesRequest) -> dict[str, Any]:
        existing = db.get_brief(brief_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Brief {brief_id} not found.")
        updated_brief = apply_customer_sizes(existing, req.sizes)
        products = db.list_products()
        short = uuid.uuid4().hex[:6]
        comp, candidates, gaps = compose_outfit(
            updated_brief,
            products,
            evaluated_on=REFERENCE_DATE,
            method=req.match_method,
            composition_id=f"cmp_{brief_id[4:]}_{short}",
            gap_source_type=GapSourceType.DEMO_SESSION,
        )
        db.save_brief(updated_brief)
        db.save_composition(comp)
        db.save_demand_gaps(gaps)
        return {
            "brief": updated_brief.model_dump(mode="json"),
            "composition": comp.model_dump(mode="json"),
            "candidates_by_part": {
                pid: [c.model_dump(mode="json") for c in clist]
                for pid, clist in candidates.items()
            },
            "explanations": explain_verified_composition(updated_brief, comp),
            "match_method_used": req.match_method.value,
        }

    @app.post("/api/v1/compositions/{composition_id}/remix")
    def post_remix_composition(composition_id: str, req: RemixSwapRequest) -> dict[str, Any]:
        comp = db.get_composition(composition_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found.")
        brief = db.get_brief(comp.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail=f"Brief {comp.brief_id} not found.")
        try:
            remixed = swap_part_in_composition(
                comp,
                brief,
                part_id=req.part_id,
                new_product_id=req.product_id,
                new_variant_id=req.variant_id,
                catalogue_by_id=db.products_by_id(),
                evaluated_on=REFERENCE_DATE,
                new_composition_id=f"{composition_id}_r{uuid.uuid4().hex[:4]}",
            )
        except VerificationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc

        db.save_composition(remixed)
        return {
            "composition": remixed.model_dump(mode="json"),
            "explanations": explain_verified_composition(brief, remixed),
        }

    @app.post("/api/v1/compositions/{composition_id}/save")
    def post_save_composition(composition_id: str) -> dict[str, Any]:
        comp = db.get_composition(composition_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found.")
        saved_comp = comp.model_copy(update={"saved": True})
        db.save_composition(saved_comp)
        return {
            "composition": saved_comp.model_dump(mode="json"),
            "notice": "Creation saved without commercial commitment. Saving is not purchase intent.",
        }

    @app.post("/api/v1/enquiries")
    def post_create_enquiry(req: CreateEnquiryRequest) -> dict[str, Any]:
        comp = db.get_composition(req.composition_id)
        if comp is None:
            raise HTTPException(status_code=404, detail=f"Composition {req.composition_id} not found.")
        brief = db.get_brief(comp.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail=f"Brief {comp.brief_id} not found.")

        enquiry_id = f"enq_{uuid.uuid4().hex[:8]}"
        try:
            enquiry = revalidate_and_build_enquiry(
                enquiry_id=enquiry_id,
                composition=comp,
                brief=brief,
                merchant_id=req.merchant_id,
                customer_authorized=req.customer_authorized,
                catalogue_by_id=db.products_by_id(),
                evaluated_on=REFERENCE_DATE,
                now=datetime.now(timezone.utc),
                requested_part_ids=req.part_ids,
                notes=req.notes,
            )
        except VerificationError as exc:
            detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
            if exc.receipt is not None:
                detail["validation_receipt"] = exc.receipt.model_dump(mode="json")
            status = 403 if exc.code == "CUSTOMER_AUTHORIZATION_REQUIRED" else 422
            raise HTTPException(status_code=status, detail=detail) from exc

        db.save_enquiry(enquiry)
        return {
            "enquiry": enquiry.model_dump(mode="json"),
            "notice": (
                "DEMO quote enquiry delivered to fictional merchant inbox. "
                "This is not a payment, order or confirmed reservation."
            ),
        }

    @app.get("/api/v1/merchants/{merchant_id}/inbox")
    def get_merchant_inbox(merchant_id: str) -> dict[str, Any]:
        merchants = {m.merchant_id: m for m in db.list_merchants()}
        if merchant_id not in merchants:
            raise HTTPException(status_code=404, detail=f"Merchant {merchant_id} not found.")
        enquiries = db.list_enquiries(merchant_id=merchant_id)
        return {
            "merchant": merchants[merchant_id].model_dump(mode="json"),
            "is_demo_inbox": True,
            "disclaimer": (
                "Simulated demo merchant inbox for a fictional merchant. "
                "Not a live external merchant integration, order or reservation."
            ),
            "enquiry_count": len(enquiries),
            "enquiries": [e.model_dump(mode="json") for e in enquiries],
        }

    @app.get("/api/v1/merchants/gaps")
    def get_merchant_gaps() -> dict[str, Any]:
        eval_gaps_stored = db.list_demand_gaps(source_type=GapSourceType.SCRIPTED_EVALUATION)
        session_gaps_stored = db.list_demand_gaps(source_type=GapSourceType.DEMO_SESSION)
        return {
            "evaluation_set": app.state.eval_report["evaluation_set"],
            "briefs_sha256_lf": app.state.eval_report["briefs_sha256_lf"],
            "briefs_hash_verified": app.state.eval_report["briefs_hash_verified"],
            "evaluation_brief_count": 20,
            "evaluation_gaps_aggregated": aggregate_demand_gaps(eval_gaps_stored, total_briefs=20),
            "demo_session_gaps_aggregated": aggregate_demand_gaps(session_gaps_stored),
            "evaluation_comparison": {
                "goa_tag_overlap": {
                    k: v
                    for k, v in app.state.eval_report["goa_tag_overlap"].items()
                    if k not in ("brief_outcomes", "aggregated_demand_gaps")
                },
                "keyword_baseline": {
                    k: v
                    for k, v in app.state.eval_report["keyword_baseline"].items()
                    if k not in ("brief_outcomes", "aggregated_demand_gaps")
                },
            },
            "disclaimer": (
                "All gap counts are computed from stored GOA scripted evaluation briefs and demo "
                "sessions (missing customer inputs excluded). Not live market demand."
            ),
        }

    if (FRONTEND_DIR / "catalogue").exists():
        app.mount("/catalogue", StaticFiles(directory=str(FRONTEND_DIR / "catalogue")), name="catalogue")

    @app.get("/")
    def index_page() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
