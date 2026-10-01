"use client";

import { EmptyState, Loaded, PageHeader, RunLine } from "@/components/States";
import type { Gaps } from "@/lib/api";
import { n, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function GapsPage() {
  const state = useApi<Gaps>("/gaps");
  return (
    <>
      <PageHeader
        title="Gaps"
        explainer="Everything the system could not handle. These returns are counted here and left out of the vendor numbers, never guessed at."
      />
      <Loaded state={state} onRetry={state.reload}>
        {(data) => {
          const gapTotal = data.buckets.reduce((sum, b) => sum + b.count, 0);
          return (
            <>
              <RunLine run={data.run} />
              {gapTotal === 0 ? (
                <EmptyState title="No gaps in this run">
                  All {n(data.total)} “Other” returns were matched to a vendor and classified.
                </EmptyState>
              ) : (
                <p className="table-summary">
                  {n(gapTotal)} of {n(data.total)} “Other” returns ({pct(data.total ? gapTotal / data.total : null)})
                  are not in the vendor numbers.
                </p>
              )}
              {gapTotal > 0 &&
                data.buckets.map((b) => (
                  <section className="card" key={b.key}>
                    <h2>
                      {b.label} <span className="count">{n(b.count)}</span>
                    </h2>
                    <p className="card-explainer">{b.explainer}</p>
                    {b.count === 0 ? (
                      <p className="muted">None in this run.</p>
                    ) : (
                      <>
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th scope="col">Return</th>
                                <th scope="col">What the customer wrote</th>
                                <th scope="col">Why it's here</th>
                              </tr>
                            </thead>
                            <tbody>
                              {b.examples.map((e) => (
                                <tr key={e.return_id}>
                                  <th scope="row" className="nowrap">{e.return_id}</th>
                                  <td>{e.text ? `“${e.text}”` : <span className="muted">(blank)</span>}</td>
                                  <td>{e.why ?? "No reason recorded"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {b.count > b.examples.length && (
                          <p className="card-foot">Showing {b.examples.length} of {n(b.count)}.</p>
                        )}
                      </>
                    )}
                  </section>
                ))}
            </>
          );
        }}
      </Loaded>
    </>
  );
}
