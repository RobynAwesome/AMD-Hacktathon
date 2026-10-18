"""One tiny call to check the endpoint is answering and how fast. Costs one short request.

Usage: python scripts/ping_llm.py              # Gemma, plain text
       python scripts/ping_llm.py --json       # Gemma, JSON mode (tests whether JSON mode is the slow part)
       python scripts/ping_llm.py --model DeepSeek-V4-Flash   # endpoint health check with another model
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from goa import llm, usage  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--json", action="store_true")
ap.add_argument("--model")
ap.add_argument("--timeout", type=float, default=120)
args = ap.parse_args()

r = llm.route("brief")
if not r.key:
    sys.exit("Set TOKEN_FACTORY_API_KEY in .env first.")
model = args.model or r.model
body = {"model": model, "temperature": 0, "max_tokens": 20,
        "messages": [{"role": "system", "content": "Answer briefly."},
                     {"role": "user", "content": 'Reply with {"ok": true}' if args.json else "Reply with OK."}]}
if args.json:
    body["response_format"] = {"type": "json_object"}
print(f"POST {r.base_url}/chat/completions  model={model}  json={args.json}  timeout={args.timeout:.0f}s")
start = time.perf_counter()
try:
    resp = httpx.post(f"{r.base_url}/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {r.key}"}, timeout=args.timeout)
except httpx.TimeoutException:
    sys.exit(f"No answer after {time.perf_counter() - start:.1f} s (timeout).")
ms = int((time.perf_counter() - start) * 1000)
usage.log_call("ping", "token_factory", model, cached=False, latency_ms=ms)
print(f"status {resp.status_code} in {ms} ms")
for k, v in resp.headers.items():
    if k.lower().startswith("x-ratelimit"):
        print(f"  {k}: {v}")
if resp.status_code == 200:
    data = resp.json()
    print("reply:", (data["choices"][0]["message"].get("content") or "").strip()[:200])
    print("usage:", data.get("usage"))
else:
    print(resp.text[:500])
