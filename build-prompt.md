# GOA build prompt

Paste everything below the line into a new chat to start the build.

---

I'm building GOA for the AMD Developer Hackathon ACT III (lablab.ai), Track 3: Reinvent Commerce. My co-builder is Robyn. Submission deadline: Sunday 18 October 2026, 12:00 SAST. Hard feature freeze 06:00 Sunday.

Read the final concept note first, it is the source of truth for scope:
https://claude.ai/code/artifact/2dea3ccd-a878-463c-ba7e-913f3300f512
(A copy is also in this project folder as concept-note.md.)

Summary, in case you can't open it:
- GOA lets a person describe a graduation outfit freely. Gemma 4 turns the text into a structured brief and splits the look into parts (dress or suit, shoes, outer layer, accessory).
- Each part is matched by meaning (embeddings) against a small verified catalogue: 40 to 60 items from 3 fictional merchants, with photos, prices, sizes, stock and delivery days.
- Plain Python rules check stock, size, delivery before the event date, and total within budget. Nothing that fails a rule is ever shown.
- The user can remix, swap and save. Parts with no good match show as "not on offer yet" and are logged as unmet demand.
- One commercial action: send a merchant enquiry with a quote request.
- A merchant gap view ranks what people wanted that nobody stocks.
- Evaluation: 20 scripted briefs, written before tuning, compared with plain keyword search over the same catalogue. Measures: valid composition rate, grounding (target 100%), steps to a sendable enquiry, gaps captured, and blind fit ratings. No revenue or conversion claims.

AMD and model requirements:
- Every Gemma call goes through AMD Token Factory (OpenAI-compatible API). I'll paste the base URL and key; read them from environment variables, never commit them.
- Gemma 4 31B is used for brief parsing (JSON output with a schema check and one retry), for vision tagging of catalogue photos (run once, cached), and for explanations and the enquiry text.
- Embeddings run on an AMD GPU if my Developer Cloud credits are live, otherwise on CPU.

Deliverables:
- Deployed web app reachable from a phone
- Public GitHub repo with a README that runs, and the synthetic catalogue generator included
- Results table from the 20-brief evaluation
- Later: slides and a 2 to 3 minute demo video

How I want to work:
- Plain, concise English. No long preambles. Never use em dashes.
- One task at a time. Stay in scope; don't add features the note doesn't list.
- Proof of concept before anything polished.
- Suggested stack: Python backend (FastAPI), a simple web front end, one host. Push back if something faster fits 17 hours.

Start with milestone 1 only:
1. Propose the repo structure and the catalogue JSON schema.
2. Write a minimal script that sends one graduation brief to Gemma via Token Factory and returns valid JSON parts.

Then stop and wait for my go-ahead before the next milestone.
