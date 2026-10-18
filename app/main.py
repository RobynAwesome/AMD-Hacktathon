"""GOA web app: one FastAPI service that serves the API and the single-page front end.

Run: uvicorn app.main:app --reload
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from goa import compose as C
from goa import gaps, llm, narrate, preread, rules, usage
from goa.brief import BriefError, parse_brief
from goa.catalogue import CATALOGUE_DIR, ROOT, load
from goa.schemas import Brief, Budget

HERE = Path(__file__).resolve().parent
SAMPLE_BRIEFS = ROOT / "eval" / "sample_briefs.json"

def _usage_poller(stop: threading.Event) -> None:
    """Refresh Token Factory usage every 5 minutes so the spend guard has current numbers."""
    while not stop.wait(300):
        llm.refresh_usage()


@asynccontextmanager
async def lifespan(_app):
    llm.check_submission()  # in GOA_MODE=submission, refuse to start if a prize-locked step left Token Factory
    load()
    llm.refresh_usage()
    stop = threading.Event()
    threading.Thread(target=_usage_poller, args=(stop,), daemon=True).start()
    yield
    stop.set()


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
    brief: dict | None = None
    compose: dict | None = None
    chosen: list[int | None] | None = None


class EnquiryRequest(BaseModel):
    look_id: str
    name: str = ""
    note: str = ""
    brief: dict | None = None
    compose: dict | None = None
    chosen: list[int | None] | None = None


class WhyRequest(BaseModel):
    brief: dict | None = None
    compose: dict | None = None
    chosen: list[int | None] | None = None


def _sample_brief(text: str, market: str) -> Brief | None:
    """Offline demo only (GOA_ALLOW_SAMPLE=1): a hand-written brief, clearly labelled on screen."""
    if os.environ.get("GOA_ALLOW_SAMPLE") != "1" or not SAMPLE_BRIEFS.exists():
        return None
    time.sleep(float(os.environ.get("GOA_SAMPLE_DELAY", 0)))  # rehearsal only: imitate the live wait
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


class PrefsIn(BaseModel):
    no_heels: bool = False
    local_first: bool = False
    rewearable: bool = False
    liked: list[str] = []


class BriefRequest(BaseModel):
    text: str
    market: str = "ZA"
    images: list[str] = []


class ComposeRequest(BaseModel):
    brief_id: str
    market: str = "ZA"
    scope: str = "global"
    size: str | None = None
    shoe_size: str | None = None
    prefs: PrefsIn = PrefsIn()
    overrides: dict = {}  # chip corrections: occasion, event_date, location, budget {amount, currency}
    brief: dict | None = None


class MirrorRequest(BaseModel):
    text: str
    markets: list[str]
    size: str | None = "M"
    shoe_size: str | None = "38"


BRIEFS: dict[str, dict] = {}  # brief_id to {"brief": Brief, "sample": bool}; in memory


def _read_brief(text: str, market: str, images: list[str]) -> tuple[Brief, list[dict], bool]:
    """The one slow step: Gemma reads the brief (and mood photos). Everything after it is code."""
    calls = []
    if images:
        try:
            mood = narrate.mood_notes(_images(images))
            text += f"\nMood photos: {mood.text}"
            calls.append({"step": "vision", "provider": mood.source, "model": mood.model, "latency_ms": mood.latency_ms})
        except Exception as e:  # mood photos are optional; say so instead of failing the look
            calls.append({"step": "vision", "error": f"Mood photos skipped: {e}"})
    try:
        res = parse_brief(text, market=market)
        calls.append({"step": "brief", "provider": res.provider, "model": res.model,
                      "latency_ms": res.latency_ms, "attempts": res.attempts, "cached": res.cached})
        return res.brief, calls, False
    except Exception as e:
        sample = _sample_brief(text, market)
        if sample is None:
            raise HTTPException(503, f"Could not read the brief: {e}")
        calls.append({"step": "brief", "provider": "sample brief (no model call)", "latency_ms": 0})
        return sample, calls, True


def _apply_overrides(brief: Brief, overrides: dict) -> Brief:
    update = {}
    if overrides.get("occasion"):
        update["occasion"] = str(overrides["occasion"])
    if overrides.get("location"):
        update["location"] = str(overrides["location"])
    if overrides.get("event_date"):
        update["event_date"] = date.fromisoformat(str(overrides["event_date"]))
    b = overrides.get("budget")
    if b and float(b.get("amount", 0)) > 0:
        update["budget"] = Budget(amount=float(b["amount"]), currency=str(b.get("currency") or brief.market))
    return brief.model_copy(update=update) if update else brief


def _for_shopper(cat, brief: Brief, market: str) -> Brief:
    """Mirror: the same request for a shopper elsewhere. Code sets their city and season, no model call."""
    mk = cat.markets[market]
    when = brief.event_date or date.today()
    return brief.model_copy(update={"location": mk.default_city, "market": market,
                                    "weather": f"{rules.season(mk.hemisphere, when)} in {mk.default_city}"})


def _store_look(look, brief) -> str:
    look_id = uuid.uuid4().hex[:12]
    LOOKS[look_id] = {"look": look, "brief": brief}
    return look_id


def _resolve_look(look_id: str, brief_data: dict | None = None, compose_data: dict | None = None,
                  chosen: list[int | None] | None = None) -> dict | None:
    entry = LOOKS.get(look_id)
    if entry:
        return entry
    if not brief_data:
        return None
    cat = load()
    brief = Brief.model_validate(brief_data)
    cd = compose_data or {}
    market = cd.get("market") or brief.market
    if market not in cat.markets:
        market = "ZA"
    brief = _apply_overrides(brief, cd.get("overrides") or {})
    prefs_in = PrefsIn.model_validate(cd.get("prefs") or {})
    look = C.compose(
        cat, brief, market=market, scope=cd.get("scope") or "global",
        size=cd.get("size"), shoe_size=cd.get("shoe_size"),
        prefs=C.Prefs(**prefs_in.model_dump()), log_gaps=False,
    )
    if chosen and len(chosen) == len(look.parts):
        for idx, opt_idx in enumerate(chosen):
            if opt_idx is not None and opt_idx != look.chosen[idx] and 0 <= opt_idx < len(look.parts[idx].options):
                look = C.swap(look, idx, opt_idx)
    entry = {"look": look, "brief": brief}
    LOOKS[look_id] = entry
    return entry


@app.post("/api/preread")
def api_preread(req: BriefRequest) -> dict:
    """Instant, no model call: chips from the text and a first glance of nearby pieces."""
    return preread.preread(load(), req.text, req.market)


@app.post("/api/brief")
def api_brief(req: BriefRequest) -> dict:
    if req.market not in load().markets:
        raise HTTPException(400, f"Unknown market {req.market}.")
    brief, calls, sample = _read_brief(req.text, req.market, req.images)
    brief_id = uuid.uuid4().hex[:12]
    BRIEFS[brief_id] = {"brief": brief, "sample": sample}
    return {"brief_id": brief_id, "brief": brief.model_dump(mode="json"), "calls": calls, "sample": sample}


@app.post("/api/compose")
def api_compose(req: ComposeRequest) -> dict:
    """Instant, no model call. Re-run freely when sizes, toggles or chips change."""
    cat = load()
    entry = BRIEFS.get(req.brief_id)
    if not entry and req.brief:
        entry = {"brief": Brief.model_validate(req.brief), "sample": False}
        BRIEFS[req.brief_id] = entry
    if not entry:
        raise HTTPException(404, "That brief has expired. Build the look again.")
    if req.market not in cat.markets:
        raise HTTPException(400, f"Unknown market {req.market}.")
    brief = _apply_overrides(entry["brief"], req.overrides)
    look = C.compose(cat, brief, market=req.market, scope=req.scope, size=req.size, shoe_size=req.shoe_size,
                     prefs=C.Prefs(**req.prefs.model_dump()))
    return {"look_id": _store_look(look, brief), "look": look.to_dict(), "brief": brief.model_dump(mode="json"),
            "sample": entry["sample"]}


@app.post("/api/why/{look_id}")
def api_why(look_id: str, req: WhyRequest | None = None) -> dict:
    """Why these pieces: one batch call, only when the shopper asks."""
    entry = _resolve_look(look_id, req.brief if req else None, req.compose if req else None, req.chosen if req else None)
    if not entry:
        raise HTTPException(404, "That look has expired. Make it again.")
    why = narrate.explain(load(), entry["look"], entry["brief"])
    lines = why.text if isinstance(why.text, dict) else {}
    for p in entry["look"].parts:
        for o in p.options:
            o.why = lines.get(o.item_id, o.why)
    return {"why": lines, "provider": why.source, "model": why.model, "latency_ms": why.latency_ms}


@app.post("/api/mirror")
def api_mirror(req: MirrorRequest) -> dict:
    """One brief call, then a look per shopper by code."""
    cat = load()
    markets = [m for m in req.markets if m in cat.markets][:4]
    if not markets:
        raise HTTPException(400, "Pick at least one market.")
    brief, calls, sample = _read_brief(req.text, markets[0], [])
    out = []
    for m in markets:
        b = _for_shopper(cat, brief, m)
        look = C.compose(cat, b, market=m, scope="global", size=req.size, shoe_size=req.shoe_size)
        out.append({"market": m, "look_id": _store_look(look, b), "look": look.to_dict(), "brief": b.model_dump(mode="json")})
    return {"shoppers": out, "calls": calls, "sample": sample}


@app.post("/api/look")
def make_look(req: LookRequest) -> dict:
    """Brief plus compose in one request (used by scripts and tests). The page uses /api/brief then /api/compose."""
    cat = load()
    if req.market not in cat.markets:
        raise HTTPException(400, f"Unknown market {req.market}.")
    brief, calls, sample = _read_brief(req.text, req.market, req.images)
    if req.mirror:
        brief = _for_shopper(cat, brief, req.market)
    look = C.compose(cat, brief, market=req.market, scope=req.scope, size=req.size, shoe_size=req.shoe_size)
    return {"look_id": _store_look(look, brief), "look": look.to_dict(), "brief": brief.model_dump(mode="json"),
            "calls": calls, "sample": sample, "today": date.today().isoformat()}


@app.post("/api/swap")
def swap(req: SwapRequest) -> dict:
    entry = _resolve_look(req.look_id, req.brief, req.compose, req.chosen)
    if not entry:
        raise HTTPException(404, "That look has expired. Make it again.")
    try:
        look = C.swap(entry["look"], req.part, req.option)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"look_id": req.look_id, "look": look.to_dict()}


@app.post("/api/enquiry")
def send_enquiry(req: EnquiryRequest) -> dict:
    entry = _resolve_look(req.look_id, req.brief, req.compose, req.chosen)
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


@app.get("/api/usage")
def get_usage() -> dict:
    return usage.summary()
