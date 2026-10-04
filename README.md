# Dhaga & Co. — Returns Insight

Shows which vendors are driving returns, and why, by reading the free-text
"Other" return reasons (Hinglish included) and linking them to SKU and vendor.
Built for Neha, Category Head.

## What it does
- Classifies each "Other" return comment into a fixed reason list
- Computes return rate per vendor per reason vs the category average
- Flags vendors with unusually high vendor-caused return rates
- Shows real comments as evidence, plus a short internal vendor brief
- Shows everything it could NOT handle (unmatched, junk, unclassified)

It does not contact vendors, change size charts, or decide anything. Neha decides.

## Where the model is called
Two steps use a model, through LangChain and OpenRouter. Everything else is plain code.

| Step | File | Model | Temperature |
|---|---|---|---|
| Classify a comment | `backend/app/pipeline/classify.py` | Model A, then Model B for hard cases | 0 |
| Write a vendor brief | `backend/app/pipeline/brief.py` | Model B | 0.2 |

The models in use (set in `.env` locally and in the Render environment when deployed):

| Role | OpenRouter model | Setting |
|---|---|---|
| Model A, cheap first pass | `google/gemini-3.5-flash-lite` | `MODEL_A_ID` |
| Model B, stronger, OpenAI | `openai/gpt-4.1` | `MODEL_B_ID` |

Both models must support tool calling on OpenRouter (the output schema is sent as a
forced tool call). The prompts are `CLASSIFY_SYSTEM_PROMPT` and `BRIEF_SYSTEM_PROMPT`
in those files.

## Pipeline flow
What happens when "Run pipeline" is pressed, with the function and file that does each step.
`◄── LangChain` marks the only places a model is called; everything else is plain code.

```text
 "Run pipeline" button
        │  POST /pipeline/run
        ▼
 start_run()            routers/pipeline.py   creates a run row, status "running"
        │
        ▼
 execute_run()          pipeline/run.py       runs in the background
        │
        ├─ 1. load tables from the database        db.py
        ├─ 2. build the model functions            build_classifier(A), build_classifier(B),
        │                                          build_brief_writer(B)
        ├─ 3. process()  ◄── the whole chain, below
        └─ 4. save results, mark run "done"        db.py


 process()  in pipeline/run.py
 ─────────────────────────────
 All returns
    │
    ▼
 Keep only "Other" returns          is_other()        load.py
    │
    ▼
 Join return → order line           join_returns()    load.py
      → SKU → vendor
    │
    ├── no vendor found ─────────────────────────────►  UNMATCHED
    ▼
 Remove phone numbers, emails       scrub_pii()       filters.py
    │
    ▼
 Is it junk?                        junk_reason()     filters.py
    │
    ├── blank, "ok", emoji ──────────────────────────►  JUNK
    ▼
 route()                            classify.py       (many comments at once)
    │
    │   Model A classifies                  ◄── LangChain
    │      ├─ valid and confident ──────────►  CLASSIFIED
    │      └─ failed / unsure
    │            ▼
    │   Model B classifies                  ◄── LangChain
    │      ├─ valid and confident ──────────►  CLASSIFIED
    │      └─ failed / still unsure ────────►  UNCLASSIFIED
    ▼
 Rates, category averages, flags    aggregate()       aggregate.py
    │
    ▼
 Pick the flagged vendors           brief_inputs()    run.py
    │
    ▼
 Model B writes a brief             write_brief()     brief.py     ◄── LangChain
    │
    ▼
 Check every number in it           check_brief()     brief.py
    ├─ all match ───────────────────►  brief OK
    └─ a number is wrong ───────────►  brief REJECTED
```

Every "Other" return ends in exactly one of four buckets: CLASSIFIED, JUNK, UNMATCHED or
UNCLASSIFIED. Only the classified ones feed the vendor numbers. The same flow as rendered
diagrams, plus what happens inside one model call, is in `docs/pipeline-flow.md`.

## Run locally (target: under 5 minutes)
You need Python 3.11+, Node 20+, and a Supabase project (any Postgres works).

1. Copy `.env.example` to `.env` and fill in the values. The backend refuses to
   start until every required value is set, and names the missing ones.
2. Create tables: run `supabase/schema.sql` in the Supabase SQL editor.
3. Backend:
   ```bash
   cd backend
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python scripts/seed.py
   uvicorn app.main:app --reload
   ```
4. Frontend (second terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
5. Open http://localhost:3000 and press "Run pipeline".

Check the backend is healthy at http://localhost:8000/health. API docs: http://localhost:8000/docs.

## Tests and evaluation
```bash
cd backend
pytest                    # no test calls the real OpenRouter API
python scripts/eval.py    # accuracy, routing and cost against the hand-labelled subset
```
`eval.py` needs `human_label` filled in `backend/data/returns.csv` (by people,
before they see model output). It is how
`CONFIDENCE_THRESHOLD` gets chosen.

## What it expects
Returns, orders, order lines, SKUs and vendors in Supabase (see `supabase/schema.sql`).
The sample data in `backend/data/` is NOT Dhaga's real data. See `backend/data/README.md`.

## When something goes wrong
- Model call fails or is unsure → retried on a stronger model → else marked "couldn't classify"
- Return can't be matched to an order/vendor → shown as "unmatched"
- Junk text → counted, never sent to a model
- Vendor brief numbers don't match the table → brief hidden, page says why
- Missing config → app refuses to start and names the missing variable
- A whole run fails → it is marked failed with the reason; the previous successful run stays on screen

## Deploying
One repository, two hosts. The frontend never talks to Supabase or OpenRouter; all keys stay on the backend.

**Backend on Render** (config in `render.yaml`)
1. In Render: New > Blueprint > pick this repository.
2. Enter the three values it asks for:
   - `OPENROUTER_API_KEY`
   - `SUPABASE_DB_URL`: the Supabase **Session pooler** string (Connect > Session pooler). The direct
     `db.<project>.supabase.co` host is IPv6 only and will not connect from Render.
     A password containing `@` must be written as `%40`.
   - `FRONTEND_ORIGINS`: the frontend's URL (put `http://localhost:3000` until the frontend is deployed).
3. When it is live, open `https://<your-service>.onrender.com/health`. It should report the database as `ok`.

On the free plan the service sleeps when idle, so the first request after a pause is slow.

**Frontend on Vercel**
1. Import this repository and set Root Directory to `frontend`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL.
3. Put the Vercel URL into `FRONTEND_ORIGINS` on Render, so the browser is allowed to call the backend.

## Discovery note
Date: 2026-10-01 (written before any code; must be agreed and committed by the team before the first code commit)

### The problem (client's language)
"Almost a third of what we sell comes back, and we can't tell which vendors
are causing it or why."

### Who owns it today
Neha, Category Head. Today she reads the "Other" box by hand, a few hundred
at a time.

### Evidence (from the brief)
- Returns are 31% overall (Neha)
- 44% of returns land in "Other" (data table, Returns row)
- "Most of it is about fit, but I can only read a few hundred at a time" (Neha)
- Size charts differ per vendor (data table, Catalogue row)
- ~40 vendor partners (Sourcing row)
- Customers write in Hinglish (Who buys from them; Constraints)

### What it costs them
- Metric they already track: 31% return rate
- Cost per return: NOT in the brief — we will ask
- Our estimate: ~6,547 "Other" returns/week (48,000 × 31% × 44%,
  assuming the rate is per order — to confirm)

### What success looks like
- Short term: share of "Other" returns classified, and Neha no longer
  reading them by hand
- Real outcome: vendor-caused return rate falls for flagged vendors after
  action, measured from the orders and returns data they already hold

### Ranked shortlist
1. Returns by vendor and reason (Neha) — biggest leak (31% of orders),
   plausibly linked to retention, signal already recorded but unread,
   internal output so errors don't reach customers
2. COD return-to-origin (Faizan) — clearest money: ~7,600 RTOs/week ×
   ₹120 ≈ ₹9 lakh/week (our arithmetic). Second because the brief gives
   no cause, so step one would be diagnosis, and prediction looks like
   ML work with no ML engineer
3. "Where is my order" tickets (Arpita) — ~5,200/week (our arithmetic),
   9-hour first response. Efficiency problem, not a revenue leak; very
   buildable but no cost per ticket in the brief
4. Listing time and catalogue data (Vivek) — 6–9 days, lost Tuesday
   spike, messy attributes. Cost unquantified; may be a root cause of
   returns, which problem 1 would help prove
5. Retention at 22% (Ritu) — the outcome the others feed into; not
   directly fixable in an MVP

### Biggest assumption
Every "Other" return can be linked to an order line, SKU and vendor,
including for pulled SKUs. Proven wrong if: the returns table has no
order line ID, or vendor isn't stored per SKU.

### Questions for the client (still open)
1. Does returns data carry the order line ID? Is vendor recorded per SKU,
   including pulled SKUs? (biggest assumption)
2. Is the 31% return rate per order or per unit?
3. What does one return cost (reverse pickup, inspection, refund handling)?
4. Neha: which return reasons do you want to see? (confirm the draft list
   in `backend/app/taxonomy.py`)
5. Who talks to vendors, and would they act on this evidence?
6. Can customer return comments be sent to an external model API?
7. Is the "Other" box the only free text, or do dropdown reasons get
   mis-picked often?

## Build note

> Template. Fill in during the build, max 2 pages.

### Code vs model

| Step | Code or model | Why |
|---|---|---|
| Load returns | Code | Query, no judgment |
| Join return → order line → SKU → vendor | Code | Lookup |
| Junk filter (blank, "ok", single emoji, too short) | Code | Pattern match; saves model cost |
| PII scrub (phone numbers, emails) | Code | Regex; happens before text leaves our server |
| Classify reason from Hinglish free text | Model A | Messy language, judgment |
| Validate output schema + confidence threshold | Code | Comparison |
| Retry hard cases | Model B | Better judgment on ambiguous / mixed text |
| Rates per vendor × reason, category averages, flags | Code | Arithmetic |
| Vendor brief (summary of the pattern) | Model B | Synthesis across many comments |
| Check every number in the brief matches the table | Code | Comparison; stops invented numbers |
| Final decision | Human (Neha) | Commercial consequences with a vendor |

[Update with anything that changed]

### Patterns
- Prompt chaining: [where, what breaks without it]
- Routing: [where, threshold chosen and why, what breaks without it]

### Models and temperatures
- Model A: `google/gemini-3.5-flash-lite` — why: cheap ($0.30 in / $2.50 out per million
  tokens), read Hinglish and Devanagari correctly in our tests, and from a different provider
  than Model B, so its mistakes are less likely to be the same ones Model B makes.
- Model B: `openai/gpt-4.1` — why: the strongest OpenAI model on OpenRouter that accepts a
  temperature setting ($2.00 in / $8.00 out per million tokens). The newer GPT-6 models
  ignore temperature, which would make the temperatures below untrue for Model B.
- Both support structured output / tool calling: checked in OpenRouter's model list
  (`supported_parameters` includes `tools` and `tool_choice`), then confirmed with real calls
  through the chain.
- Temperatures: classify 0, retry 0, brief 0.2 — why: [fill in]
- Measured on the sample data: about 1,140 input and 60 output tokens per classification;
  a full run of 83 comments costs about $0.05.

### Accuracy (from eval.py)
- Model A alone: [x]% ; with routing: [y]% ; routed share: [z]%
- Confidence threshold: [value] — why
- Does confidence separate right from wrong answers? [yes/no, evidence]

### Flag thresholds
- MIN_RETURNS_TO_FLAG: [value] — why
- LIFT_THRESHOLD: [value] — why

### Cost line
```text
Weekly "Other" returns (estimate, our arithmetic):
  48,000 orders/week × 31% returned × 44% "Other" ≈ 6,547
  (ASSUMES the 31% is per order — ASK CLIENT)

Weekly cost =
    (6,547 − junk) × cost_per_call(Model A)
  + (share routed to B) × (6,547 − junk) × cost_per_call(Model B)
  + (number of vendor briefs) × cost_per_brief(Model B)

cost_per_call = (avg input tokens × input price + avg output tokens × output price)
```
[Fill in real OpenRouter prices, and real token counts and routing share from eval.py.
Mark which numbers come from the brief and which are our estimates.]

### The thing that broke that we didn't expect
[Fill in honestly]

## More docs
- `docs/pipeline-flow.md` — the pipeline as rendered diagrams, including what happens inside one model call
