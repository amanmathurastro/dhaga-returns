"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { BarList } from "@/components/Charts";
import { CommentList } from "@/components/Comments";
import { EmptyState, Loaded, PageHeader, RunLine } from "@/components/States";
import { ReasonCell } from "@/components/VendorCells";
import type { Brief, LabelCount, VendorDetail } from "@/lib/api";
import { n, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const state = useApi<VendorDetail>(`/vendors/${encodeURIComponent(id)}`);

  return (
    <>
      <p className="back">
        <Link href="/vendors">← All vendors</Link>
      </p>
      <Loaded state={state} onRetry={state.reload}>
        {(data) => <Detail data={data} />}
      </Loaded>
    </>
  );
}

function Detail({ data }: { data: VendorDetail }) {
  const fitTotal = data.fit_directions.reduce((sum, d) => sum + d.count, 0);
  const fitMax = Math.max(...data.fit_directions.map((d) => d.count), 1);
  const bars = (items: LabelCount[], total: number) =>
    items.map((d) => ({ key: d.key, label: d.label, count: d.count, share: total ? d.count / total : null }));

  return (
    <>
      <PageHeader
        title={data.vendor_name}
        explainer={`${data.city ? `${data.city}. ` : ""}What comes back from this vendor, why, and what customers actually wrote.`}
      />
      <RunLine run={data.run} />

      <BriefCard brief={data.brief} />

      <section className="card">
        <h2>Return rates against the category average</h2>
        {data.segments.length === 0 ? (
          <EmptyState title="Nothing sold in this period">This vendor has no sales or returns in this run.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col" className="num">Units sold</th>
                  {data.segments[0].cells.map((c) => (
                    <th scope="col" className="num" key={c.reason}>
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.segments.map((s) => (
                  <tr key={s.category}>
                    <th scope="row">{s.category_label}</th>
                    <td className="num">{n(s.units_sold)}</td>
                    {s.cells.map((c) => (
                      <ReasonCell key={c.reason} cell={c} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>What kind of fit problem</h2>
        {fitTotal === 0 ? (
          <EmptyState title="No fit returns for this vendor in this run" />
        ) : (
          <>
            <p className="card-explainer">Of the {n(fitTotal)} returns about fit.</p>
            <BarList unit="returns" max={fitMax} items={bars(data.fit_directions, fitTotal)} />
            {data.fit_areas.length > 0 && (
              <div className="bar-group">
                <h3>Where on the body, when the customer said</h3>
                <BarList unit="returns" max={fitMax} items={bars(data.fit_areas, fitTotal)} />
              </div>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2>Products with the most returns</h2>
        {data.top_skus.length === 0 ? (
          <EmptyState title="No classified returns for this vendor in this run" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Product</th>
                  <th scope="col" className="num">Units sold</th>
                  <th scope="col" className="num">Returns</th>
                  <th scope="col" className="num">Rate</th>
                  <th scope="col">Most common reason</th>
                </tr>
              </thead>
              <tbody>
                {data.top_skus.map((s) => (
                  <tr key={s.sku_id}>
                    <th scope="row">
                      {s.product_name ?? s.sku_id}
                      <div className="cell-sub">
                        {s.sku_id} · {s.category_label}
                        {s.is_live === false && " · no longer on sale"}
                      </div>
                    </th>
                    <td className="num">{n(s.units_sold)}</td>
                    <td className="num">{n(s.returns)}</td>
                    <td className="num">{pct(s.rate)}</td>
                    <td>{s.top_reason_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>What customers wrote</h2>
        {data.comments.length === 0 ? (
          <EmptyState title="No classified comments for this vendor in this run" />
        ) : (
          <>
            <p className="card-explainer">
              The customer's own words, with phone numbers and emails removed, and a one-line English gist.
              {data.comments_total > data.comments.length &&
                ` Showing ${data.comments.length} of ${n(data.comments_total)}.`}
            </p>
            <CommentList comments={data.comments} />
          </>
        )}
      </section>
    </>
  );
}

function BriefCard({ brief }: { brief: Brief }) {
  if (brief.status === "ok" && brief.brief) {
    const b = brief.brief;
    return (
      <section className="card brief">
        <p className="eyebrow">Vendor brief · written by a model, numbers checked by code · internal only</p>
        <h2>{b.headline}</h2>
        <ul className="claims">
          {b.claims.map((c, i) => (
            <li key={i}>{c.text}</li>
          ))}
        </ul>
        <h3>Keep in mind</h3>
        <ul>
          <li>This describes a pattern in returns. It does not prove the cause.</li>
          {b.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
        {b.example_comment_ids.length > 0 && (
          <p className="card-foot">
            Example comments:{" "}
            {b.example_comment_ids.map((id, i) => (
              <span key={id}>
                {i > 0 && ", "}
                <a href={`#${id}`}>{id}</a>
              </span>
            ))}
          </p>
        )}
      </section>
    );
  }
  if (brief.status === "not_written") {
    return (
      <section className="card brief">
        <p className="eyebrow">Vendor brief</p>
        <p>No brief for this vendor: nothing is flagged, so there is no pattern to summarise.</p>
      </section>
    );
  }
  const mismatch = brief.status === "rejected_numbers_mismatch";
  return (
    <section className="card brief">
      <p className="eyebrow">Vendor brief</p>
      <div className="state state-error" role="alert">
        <strong>{mismatch ? "Brief unavailable — numbers didn't match" : "Brief unavailable"}</strong>
        <p>
          {mismatch
            ? "The model wrote a brief, but it contained numbers that don't match the table below, so it is not shown. The table and comments on this page are unaffected."
            : "The brief could not be written for this run. The table and comments on this page are unaffected."}
        </p>
        {brief.problems.length > 0 && (
          <ul>
            {brief.problems.slice(0, 5).map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
