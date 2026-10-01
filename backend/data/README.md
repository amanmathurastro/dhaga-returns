# Sample data

**This is a starter set so the app runs. It is not Dhaga's data, and it is not yet
the team's hand-written test data.** Replace or extend it before the pitch.

How it was made:
- `vendors.csv`, `skus.csv`: written by hand (7 vendors, 19 SKUs, two of them pulled).
- The return comments in `returns.csv`: written one by one (by Claude, during the
  build), not sampled from anywhere. Hinglish, English, some Devanagari, typos,
  multi-reason comments, junk, PII, and three returns with no matching order line.
- `orders.csv`, `order_lines.csv`, and which order each return belongs to: produced
  by a script with a fixed random seed, so the volumes are arbitrary.

Honesty rule: every pattern here was put there on purpose, so the dashboard has
something to find. Say so in the pitch. Two vendors were deliberately skewed:
- V01, Jaipur Block Prints: many "runs small" comments (a large vendor, flagged for fit).
- V05, Kolkata Cotton Co.: several "runs large" comments (a small vendor with few units
  sold, also flagged for fit, so a high rate comes from a small count).

Still to do by the team:
- Decide the volume and write the real test set.
- Fill `human_label` for a subset. Each label must be one of the reasons in
  `backend/app/taxonomy.py`, written independently, **before** looking at any model
  output. It is blank for every row on purpose.

The dropdown reasons other than "Other" ("Size issue", "Quality issue", ...) are
invented. What Dhaga's dropdown really contains is an open question for the client.

Load with `python scripts/seed.py` (add `--reset` to wipe existing data and results first).
