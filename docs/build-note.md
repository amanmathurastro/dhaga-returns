# Build note

> Template. Fill in during the build, max 2 pages.

## Code vs model

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

## Patterns
- Prompt chaining: [where, what breaks without it]
- Routing: [where, threshold chosen and why, what breaks without it]

## Models and temperatures
- Model A: [OpenRouter ID] — why: [cost/latency/quality]
- Model B: [OpenRouter ID] — why
- Both support structured output / tool calling: [how we checked]
- Temperatures: classify 0, retry 0, brief 0.2 — why

## Accuracy (from eval.py)
- Model A alone: [x]% ; with routing: [y]% ; routed share: [z]%
- Confidence threshold: [value] — why
- Does confidence separate right from wrong answers? [yes/no, evidence]

## Flag thresholds
- MIN_RETURNS_TO_FLAG: [value] — why
- LIFT_THRESHOLD: [value] — why

## Cost line
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

## The thing that broke that we didn't expect
[Fill in honestly]
