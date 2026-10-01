import type { ReactNode } from "react";
import type { CoverageItem } from "@/lib/api";
import { n, pct } from "@/lib/format";

export interface BarItem {
  key: string;
  label: string;
  note?: string; // small secondary text under the label
  count: number;
  share: number | null; // 0..1, of the whole list's total
}

/** Horizontal bars, one series. Every bar has its label and value in text, so colour carries nothing alone. */
export function BarList({ items, unit, max: sharedMax }: { items: BarItem[]; unit: string; max?: number }) {
  // Pass `max` when several lists sit together, so bar lengths compare across them.
  const max = sharedMax ?? Math.max(...items.map((i) => i.count), 1);
  return (
    <ul className="bars">
      {items.map((item) => (
        <li key={item.key} title={`${item.label}: ${n(item.count)} ${unit} (${pct(item.share)})`}>
          <div className="bar-label">
            <span>{item.label}</span>
            {item.note && <small>{item.note}</small>}
          </div>
          <div className="bar-track">
            {item.count > 0 && <span className="bar-fill" style={{ width: `${(item.count / max) * 100}%` }} />}
          </div>
          <div className="bar-value">
            {n(item.count)} <small>{pct(item.share)}</small>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** How much of the run the system handled, and how much it couldn't. One stacked bar plus a legend with every value. */
export function CoverageBar({ items }: { items: CoverageItem[] }) {
  const total = items.reduce((sum, i) => sum + i.count, 0);
  return (
    <div className="coverage">
      <div className="coverage-bar" role="img" aria-label={items.map((i) => `${i.label} ${pct(i.share)}`).join(", ")}>
        {total === 0 && <span className="coverage-empty" />}
        {items
          .filter((i) => i.count > 0)
          .map((i) => (
            <span
              key={i.key}
              className={`seg seg-${i.key}`}
              style={{ flexGrow: i.count }}
              title={`${i.label}: ${n(i.count)} (${pct(i.share)})`}
            />
          ))}
      </div>
      <ul className="legend">
        {items.map((i) => (
          <li key={i.key}>
            <span className={`swatch seg-${i.key}`} aria-hidden="true" />
            <span className="legend-label">{i.label}</span>
            <span className="legend-value">
              {n(i.count)} <small>{pct(i.share)}</small>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StatTile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  );
}
