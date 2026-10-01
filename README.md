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

## Docs
- `docs/discovery-note.md` — why this problem
- `docs/build-note.md` — code vs model, patterns, cost, what broke
