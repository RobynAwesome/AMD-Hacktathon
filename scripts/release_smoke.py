"""Sanitized public POST receipt. --fresh performs one uncached demo journey, never an eval batch."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid


def run(base: str, sha: str, fresh: bool = False) -> dict:
    marker = "Alice-release-audit-" + uuid.uuid4().hex[:8]
    trace = {"release_sha": sha, "base_url": base, "started_at": datetime.now(timezone.utc).isoformat(),
             "synthetic": True, "steps": []}

    def call(path, body=None):
        start = time.monotonic()
        req = urllib.request.Request(base.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "User-Agent": "GOA-release-smoke/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=50) as response:
                status, data = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, data = error.code, {"error": "http_failure"}
        except Exception as error:
            status, data = None, {"error": type(error).__name__}
        row = {"path": path, "method": "POST" if body is not None else "GET", "status": status,
               "seconds": round(time.monotonic() - start, 2)}
        if isinstance(data, dict):
            for key in ("release_sha", "mode", "routes", "calls", "sample", "provider", "model", "cached",
                        "latency_ms", "error", "persistence", "delivered", "web_budget_seconds"):
                if key in data:
                    row[key] = data[key]
            if "look" in data:
                row["look"] = {k: data["look"].get(k) for k in ("budget_status", "total_local", "chosen")}
            if "enquiries" in data:
                row["enquiries"] = [{k: q.get(k) for k in ("merchant_id", "message_source", "message_cached",
                    "model", "model_error", "status", "persistence")} for q in data["enquiries"]]
        if isinstance(data, list):
            row["count"] = len(data)
            if path == "/api/enquiries":
                row["matching_synthetic_records"] = sum(q.get("from") == marker for q in data)
            if path == "/api/gaps":
                row["sources"] = sorted({q.get("source", "unknown") for q in data})
        trace["steps"].append(row)
        print(json.dumps(row), flush=True)
        return status, data

    status, config = call("/api/config")
    if status != 200 or config.get("release_sha") not in ("", sha):
        trace["error"] = "release_identity_or_config_failed"
        return trace
    text = ("Graduation in Cape Town on 12 December, outdoor, warm. Green, elegant but not formal, "
            "something I can wear again. Budget R2,500.")
    if fresh:
        text += f" Synthetic release check {marker}."
    status, brief = call("/api/brief", {"text": text, "market": "ZA"})
    if status == 200:
        trace["fresh_brief_verified"] = not brief.get("sample") and any(
            c.get("provider") == "token_factory" and c.get("model") == "Gemma-4-31B-IT"
            and c.get("cached") is False for c in brief.get("calls", []))
        compose = {"brief_id": brief["brief_id"], "brief": brief["brief"], "sample": brief["sample"],
                   "market": "ZA", "scope": "global", "size": "M", "shoe_size": "38"}
        status, look = call("/api/compose", compose)
        if status == 200:
            state = {"brief": look["brief"], "compose": compose, "chosen": look["look"]["chosen"]}
            call("/api/why/" + look["look_id"], state)
            call("/api/enquiry", {"look_id": look["look_id"], "name": marker,
                 "note": "Synthetic smoke test; fictional catalogue; no email.", **state})
    call("/api/enquiries")
    call("/api/gaps")
    trace["post_journey_passed"] = len(trace["steps"]) == 7 and all(s["status"] == 200 for s in trace["steps"])
    trace["durable_persistence_verified"] = False
    trace["mobile_verified"] = False
    trace["credential_rotation_verified"] = False
    trace["finished_at"] = datetime.now(timezone.utc).isoformat()
    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fresh", action="store_true", help="Use an uncached synthetic brief; consumes shared API quota")
    args = parser.parse_args()
    result = run(args.base, args.sha, args.fresh)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    raise SystemExit(0 if result.get("post_journey_passed") else 1)
