"use client";

import { useEffect, useRef } from "react";
import type { VendorRow } from "@/lib/api";
import { n, pct } from "@/lib/format";

/** Pop-up listing every SKU a vendor has in one category, with its units sold and return rates. */
export function SkuDialog({ row, onClose }: { row: VendorRow | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (row && !dialog.open) dialog.showModal();
    if (!row && dialog.open) dialog.close();
  }, [row]);

  return (
    // The native dialog closes on Esc (firing onClose); a click on the backdrop lands on the dialog itself.
    <dialog
      ref={ref}
      className="dialog"
      onClose={onClose}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      aria-labelledby="sku-dialog-title"
    >
      {row && (
        <div className="dialog-body">
          <div className="dialog-head">
            <div>
              <h2 id="sku-dialog-title">
                {row.vendor_name} · {row.category_label}
              </h2>
              <p className="card-explainer">
                {row.skus.length} {row.skus.length === 1 ? "product" : "products"}, most returns first. Rates are
                returns per unit sold, for the same period as the vendor table.
              </p>
            </div>
            <button type="button" className="dialog-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
          {row.skus.length === 0 ? (
            <p className="muted">No products on record for this vendor in this category.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">SKU</th>
                    <th scope="col">Product</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="num">Units sold</th>
                    <th scope="col" className="num">Returns</th>
                    {row.cells.map((c) => (
                      <th scope="col" className="num" key={c.reason}>
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {row.skus.map((sku) => (
                    <tr key={sku.sku_id}>
                      <th scope="row" className="nowrap">
                        {sku.sku_id}
                      </th>
                      <td>{sku.product_name ?? "–"}</td>
                      <td className="nowrap">{sku.is_live === false ? "No longer on sale" : "On sale"}</td>
                      <td className="num">{n(sku.units_sold)}</td>
                      <td className="num">{n(sku.returns)}</td>
                      {sku.rates.map((r) => (
                        <td className="num" key={r.reason} title={`${n(r.returns)} returns`}>
                          {r.rate === null ? "–" : pct(r.rate)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}
