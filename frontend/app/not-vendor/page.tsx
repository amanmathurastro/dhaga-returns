"use client";

import { CommentList } from "@/components/Comments";
import { EmptyState, Loaded, PageHeader, RunLine } from "@/components/States";
import type { NonVendor } from "@/lib/api";
import { n, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function NotVendorPage() {
  const state = useApi<NonVendor>("/non-vendor");
  return (
    <>
      <PageHeader
        title="Not the vendor"
        explainer="Returns where the comment points at the courier, the warehouse or the customer. These are kept out of the vendor numbers."
      />
      <Loaded state={state} onRetry={state.reload}>
        {(data) => (
          <>
            <RunLine run={data.run} />
            {data.groups.every((g) => g.count === 0) ? (
              <EmptyState title="No returns of this kind in this run">
                {data.classified_total === 0
                  ? "Nothing was classified in this run, so there is nothing to show here."
                  : `None of the ${n(data.classified_total)} classified comments pointed at the courier, warehouse or customer.`}
              </EmptyState>
            ) : (
              data.groups.map((g) => (
                <section className="card" key={g.reason}>
                  <h2>{g.label}</h2>
                  <p className="card-explainer">
                    Likely owner: <strong>{g.likely_owner}</strong>. {n(g.count)} {g.count === 1 ? "return" : "returns"},{" "}
                    {pct(g.share)} of classified comments.
                  </p>
                  {g.count === 0 ? (
                    <p className="muted">None in this run.</p>
                  ) : (
                    <>
                      <CommentList comments={g.examples} />
                      {g.count > g.examples.length && (
                        <p className="card-foot">Showing {g.examples.length} of {n(g.count)}.</p>
                      )}
                    </>
                  )}
                </section>
              ))
            )}
          </>
        )}
      </Loaded>
    </>
  );
}
