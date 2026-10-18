"""GOA web app: one FastAPI service that serves the API and the single-page front end.

Run: uvicorn app.main:app --reload
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from goa import compose as C
from goa import gaps, llm, narrate, rules
from goa.brief import BriefError, parse_brief
from goa.catalogue import CATALOGUE_DIR, ROOT, load
from goa.schemas import Brief

HERE = Path(__file__).resolve().parent
SAMPLE_BRIEFS = ROOT / "eval" / "sample_briefs.json"

@asynccontextmanager
async def lifespan(_app):
    llm.check_submission()  # in GOA_MODE=submission, refuse to start if a prize-locked step left Token Factory
    load()
    yield


app = FastAPI(title="GOA", lifespan=lifespan)
app.mount("/images", StaticFiles(directory=CATALOGUE_DIR / "images"), name="images")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

LOOKS: dict[str, dict] = {}  # look_id to {"look": Look, "brief": Brief}; in memory, no accounts


class LookRequest(BaseModel):
    text: str
    market: str = "ZA"
    scope: str = "global"
    size: str | None = None
    shoe_size: str | None = None
    images: list[str] = []  # data URLs, resized in the browser
    mirror: bool = False  # mirror view: the shopper is in their own market's city, not the brief's


class SwapRequest(BaseModel):
    look_id: str
    part: int
    option: int


class EnquiryRequest(BaseModel):
    look_id: str
    name: str = ""
    note: str = ""


def _sample_brief(text: str, market: str) -> Brief | None:
    """Offline demo only (GOA_ALLOW_SAMPLE=1): a hand-written brief, clearly labelled on screen."""
    if os.environ.get("GOA_ALLOW_SAMPLE") != "1" or not SAMPLE_BRIEFS.exists():
        return None
    for s in json.loads(SAMPLE_BRIEFS.read_text()):
        if s["text"].strip().lower() == text.strip().lower():
            return Brief.model_validate({**s["brief"], "market": market})
    return None


def _images(data_urls: list[str]) -> list[llm.Image]:
    out = []
    for url in data_urls[:3]:
        head, _, b64 = url.partition(",")
        mime = head.removeprefix("data:").split(";")[0] or "image/jpeg"
        out.append(llm.Image(base64.b64decode(b64), mime))
    return out


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/config")
def config() -> dict:
    cat = load()
    routes = [{"step": s, "provider": llm.route(s).provider, "model": llm.route(s).model,
               "locked_to": llm.route(s).locked_to} for s in llm.STEPS]
    return {
        "markets": [m.model_dump() for m in cat.markets.values()],
        "merchants": [{"id": m.id, "name": m.name, "city": m.city, "market": m.market, "about": m.about}
                      for m in cat.merchants.values()],
        "scopes": C.SCOPES, "routes": routes, "mode": llm.mode(),
    }


@app.post("/api/look")
def make_look(req: LookRequest) -> dict:
    cat = load()
    if req.market not in cat.markets:
        raise HTTPException(400, f"Unknown market {req.market}.")
    calls = []
    text = req.text
    if req.images:
        try:
            mood = narrate.mood_notes(_images(req.images))
            text += f"\nMood photos: {mood.text}"
            calls.append({"step": "vision", "provider": mood.source, "model": mood.model, "latency_ms": mood.latency_ms})
        except Exception as e:  # mood photos are optional; say so instead of failing the look
            calls.append({"step": "vision", "error": f"Mood photos skipped: {e}"})
    sample = None
    try:
        res = parse_brief(text, market=req.market)
        brief = res.brief
        calls.append({"step": "brief", "provider": res.provider, "model": res.model,
                      "latency_ms": res.latency_ms, "attempts": res.attempts, "cached": res.cached})
    except (llm.LLMConfigError, BriefError, Exception) as e:
        sample = _sample_brief(req.text, req.market)
        if sample is None:
            raise HTTPException(503, f"Could not read the brief: {e}")
        brief = sample
        calls.append({"step": "brief", "provider": "sample brief (no model call)", "latency_ms": 0})
    if req.mirror:
        # Same request, different shopper: the event happens where they are, and code sets the season.
        mk = cat.markets[req.market]
        when = brief.event_date or date.today()
        brief = brief.model_copy(update={
            "location": mk.default_city, "market": req.market,
            "weather": f"{rules.season(mk.hemisphere, when)} in {mk.default_city}"})
    look = C.compose(cat, brief, market=req.market, scope=req.scope, size=req.size, shoe_size=req.shoe_size)
    why = narrate.explain(cat, look, brief)
    calls.append({"step": "explain", "provider": why.source, "model": why.model, "latency_ms": why.latency_ms})
    for p in look.parts:
        for o in p.options:
            o.why = why.text.get(o.item_id, "") if isinstance(why.text, dict) else ""
    look_id = uuid.uuid4().hex[:12]
    LOOKS[look_id] = {"look": look, "brief": brief}
    return {"look_id": look_id, "look": look.to_dict(), "brief": brief.model_dump(mode="json"),
            "calls": calls, "sample": sample is not None, "today": date.today().isoformat()}


@app.post("/api/swap")
def swap(req: SwapRequest) -> dict:
    entry = LOOKS.get(req.look_id)
    if not entry:
        raise HTTPException(404, "That look has expired. Make it again.")
    try:
        look = C.swap(entry["look"], req.part, req.option)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"look_id": req.look_id, "look": look.to_dict()}


@app.post("/api/enquiry")
def send_enquiry(req: EnquiryRequest) -> dict:
    entry = LOOKS.get(req.look_id)
    if not entry:
        raise HTTPException(404, "That look has expired. Make it again.")
    look = entry["look"]
    if look.budget_status == "over":
        raise HTTPException(400, "This look is over budget. Swap a part before sending an enquiry.")
    if look.size is None and any(p.part["slot"] in ("garment", "outer_layer") for p in look.parts if p.status == "available"):
        raise HTTPException(400, "Add your clothing size before sending an enquiry.")
    return {"enquiries": narrate.enquiry(load(), look, entry["brief"], req.name, req.note)}


@app.get("/api/enquiries")
def enquiries() -> list[dict]:
    if not narrate.ENQUIRIES_LOG.exists():
        return []
    rows = [json.loads(x) for x in narrate.ENQUIRIES_LOG.read_text().splitlines() if x.strip()]
    return rows[::-1][:50]


@app.get("/api/gaps")
def gap_view(market: str | None = None) -> list[dict]:
    return gaps.ranked(load(), market)


@app.get("/api/ideas")
def get_ideas(occasion: str = "graduation", market: str = "ZA", notes: str = "") -> dict:
    n = narrate.ideas(occasion, market, notes)
    return {"ideas": n.text, "provider": n.source, "latency_ms": n.latency_ms}
