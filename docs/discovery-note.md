# Discovery note — Dhaga & Co.
Date: 2026-10-01 (written before any code; must be agreed and committed by the team before the first code commit)

## The problem (client's language)
"Almost a third of what we sell comes back, and we can't tell which vendors
are causing it or why."

## Who owns it today
Neha, Category Head. Today she reads the "Other" box by hand, a few hundred
at a time.

## Evidence (from the brief)
- Returns are 31% overall (Neha)
- 44% of returns land in "Other" (data table, Returns row)
- "Most of it is about fit, but I can only read a few hundred at a time" (Neha)
- Size charts differ per vendor (data table, Catalogue row)
- ~40 vendor partners (Sourcing row)
- Customers write in Hinglish (Who buys from them; Constraints)

## What it costs them
- Metric they already track: 31% return rate
- Cost per return: NOT in the brief — we will ask
- Our estimate: ~6,547 "Other" returns/week (48,000 × 31% × 44%,
  assuming the rate is per order — to confirm)

## What success looks like
- Short term: share of "Other" returns classified, and Neha no longer
  reading them by hand
- Real outcome: vendor-caused return rate falls for flagged vendors after
  action, measured from the orders and returns data they already hold

## Ranked shortlist
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

## Biggest assumption
Every "Other" return can be linked to an order line, SKU and vendor,
including for pulled SKUs. Proven wrong if: the returns table has no
order line ID, or vendor isn't stored per SKU.

## Questions for the client (still open)
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
