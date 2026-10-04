"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { EmptyState, Loaded, PageHeader, PartialNotice, RunLine } from "@/components/States";
import { SkuDialog } from "@/components/SkuDialog";
import { ReasonCell } from "@/components/VendorCells";
import type { VendorRow, Vendors } from "@/lib/api";
import { n, periodText } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const CATEGORIES = [
  { value: "", label: "All categories" },
  { value: "womenswear", label: "Womenswear" },
  { value: "kidswear", label: "Kidswear" },
  { value: "mens", label: "Men's" },
];

type Sort = { column: string; descending: boolean } | null; // null = flagged first (backend order)

function sortValue(row: VendorRow, column: string): number | string {
  if (column === "vendor") return row.vendor_name.toLowerCase();
  if (column === "category") return row.category_label;
  if (column === "units") return row.units_sold;
  return row.cells.find((c) => c.reason === column)?.rate ?? -1;
}

export default function VendorsPage() {
  const [category, setCategory] = useState("");
  const state = useApi<Vendors>(category ? `/vendors?category=${category}` : "/vendors");

  return (
    <>
      <PageHeader
        title="Vendors"
        explainer="How often each vendor's products come back for each reason, compared with the average for the same category."
      />
      <div className="filters">
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        {state.status === "ready" && (
          <span className="filter-note">
            Period: {periodText(state.data.run)}. To change it, <Link href="/">run the pipeline</Link> with other
            dates.
          </span>
        )}
      </div>
      <Loaded state={state} onRetry={state.reload}>
        {(data) => <VendorTable data={data} />}
      </Loaded>
    </>
  );
}

function VendorTable({ data }: { data: Vendors }) {
  const [sort, setSort] = useState<Sort>(null);
  const [skuRow, setSkuRow] = useState<VendorRow | null>(null);
  const rows = useMemo(() => {
    if (!sort) return data.rows;
    const sorted = [...data.rows].sort((a, b) => {
      const x = sortValue(a, sort.column);
      const y = sortValue(b, sort.column);
      return x < y ? -1 : x > y ? 1 : 0;
    });
    return sort.descending ? sorted.reverse() : sorted;
  }, [data.rows, sort]);

  if (data.rows.length === 0) {
    return (
      <>
        <RunLine run={data.run} />
        <EmptyState title="No vendors to show">Nothing was sold in this category for the period of this run.</EmptyState>
      </>
    );
  }

  const reasonColumns = data.rows[0].cells;
  const flaggedCount = new Set(data.rows.filter((r) => r.flagged).map((r) => r.vendor_id)).size;

  function header(column: string, label: string, numeric = false) {
    const active = sort?.column === column;
    return (
      <th
        key={column}
        scope="col"
        className={numeric ? "num" : undefined}
        aria-sort={active ? (sort.descending ? "descending" : "ascending") : undefined}
      >
        <button
          type="button"
          className="sort"
          onClick={() => setSort({ column, descending: active ? !sort.descending : numeric })}
        >
          {label} <span aria-hidden="true">{active ? (sort.descending ? "↓" : "↑") : "↕"}</span>
        </button>
      </th>
    );
  }

  return (
    <>
      <RunLine run={data.run} />
      <PartialNotice unclassified={data.unclassified} unmatched={data.unmatched} />
      <p className="table-summary">
        {flaggedCount === 0
          ? "No vendor is flagged in this view."
          : `${flaggedCount} ${flaggedCount === 1 ? "vendor is" : "vendors are"} flagged.`}{" "}
        A cell is flagged when the vendor has at least {data.thresholds.min_returns_to_flag} returns for that reason
        and its rate is at least {data.thresholds.lift_threshold}× the category average. Rates are returns per unit
        sold.
        {sort && (
          <>
            {" "}
            <button type="button" className="link-button" onClick={() => setSort(null)}>
              Show flagged vendors first
            </button>
          </>
        )}
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {header("vendor", "Vendor")}
              {header("category", "Category")}
              {header("units", "Units sold", true)}
              <th scope="col">Products</th>
              {reasonColumns.map((c) => header(c.reason, c.can_flag ? c.label : `${c.label} *`, true))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.vendor_id}-${row.category}`}>
                <th scope="row">
                  {row.vendor_name}
                  {row.city && <div className="cell-sub">{row.city}</div>}
                </th>
                <td>{row.category_label}</td>
                <td className="num">{n(row.units_sold)}</td>
                <td>
                  <button
                    type="button"
                    className="link-button nowrap"
                    onClick={() => setSkuRow(row)}
                    aria-haspopup="dialog"
                  >
                    {row.skus.length} {row.skus.length === 1 ? "SKU" : "SKUs"} ▸
                  </button>
                </td>
                {row.cells.map((cell) => (
                  <ReasonCell key={cell.reason} cell={cell} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SkuDialog row={skuRow} onClose={() => setSkuRow(null)} />
      <p className="footnote">
        * Colour or look not matching the photos could be the vendor's fabric or Dhaga's own photos, so it is shown
        but never flagged against a vendor.
      </p>
    </>
  );
}
