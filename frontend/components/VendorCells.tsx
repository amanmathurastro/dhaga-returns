import type { Cell } from "@/lib/api";
import { n, pct, timesAverage } from "@/lib/format";

/** One vendor × reason cell: rate, comparison with the category average, and the flag (icon + word, not colour alone). */
export function ReasonCell({ cell }: { cell: Cell }) {
  if (cell.returns === 0) {
    return <td className="cell cell-none">No returns</td>;
  }
  return (
    <td className={cell.flagged ? "cell cell-flagged" : "cell"}>
      <div className="cell-rate">{pct(cell.rate)}</div>
      <div className="cell-sub">{timesAverage(cell.lift)}</div>
      <div className="cell-sub">
        {n(cell.returns)} {cell.returns === 1 ? "return" : "returns"}
      </div>
      {cell.flagged && (
        <div className="flag">
          <span aria-hidden="true">⚑</span> Flagged
        </div>
      )}
    </td>
  );
}
