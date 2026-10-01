"use client";

import Link from "next/link";
import { BarList, CoverageBar, StatTile } from "@/components/Charts";
import { RunControl } from "@/components/RunControl";
import { EmptyState, ErrorState, Loading, PageHeader, RunLine } from "@/components/States";
import type { ReasonGroup, Summary } from "@/lib/api";
import { n, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const GROUP_TITLES: Record<ReasonGroup, string> = {
  vendor: "Likely the vendor",
  unclear: "Owner unclear",
  not_vendor: "Not the vendor",
  other: "No clear reason",
};
const GROUP_ORDER: ReasonGroup[] = ["vendor", "unclear", "not_vendor", "other"];

export default function SummaryPage() {
  const summary = useApi<Summary>("/summary");

  return (
    <>
      <PageHeader
        title="Summary"
        explainer="What customers wrote when they picked “Other” as their return reason, sorted into reasons, and how much the system couldn't handle."
      />
      <RunControl onFinished={summary.reload} />

      {summary.status === "loading" && <Loading what="Loading the latest results" />}
      {summary.status === "error" &&
        (summary.error.code === "no_run" ? (
          <EmptyState title="No results yet">Press “Run pipeline” above to read the return comments.</EmptyState>
        ) : (
          <ErrorState error={summary.error} onRetry={summary.reload} />
        ))}
      {summary.status === "ready" && <SummaryBody data={summary.data} />}
    </>
  );
}

function SummaryBody({ data }: { data: Summary }) {
  const classified = data.coverage.find((c) => c.key === "classified");
  const notHandled = data.other_returns - (classified?.count ?? 0);
  const maxReason = Math.max(...data.reasons.map((r) => r.count), 1);

  if (data.other_returns === 0) {
    return (
      <>
        <RunLine run={data.run} />
        <EmptyState title="No “Other” returns in this period">
          The run finished, but there were no return comments to read for these dates. Try a wider period.
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <RunLine run={data.run} />

      <section className="tiles">
        <StatTile label="“Other” returns read" value={n(data.other_returns)} note={`from ${n(data.units_sold)} units sold`} />
        <StatTile
          label="Sorted into a reason"
          value={pct(classified?.share, 0)}
          note={`${n(classified?.count ?? 0)} of ${n(data.other_returns)}`}
        />
        <StatTile
          label="Vendors flagged"
          value={n(data.flagged_vendors)}
          note={<Link href="/vendors">See the vendor table</Link>}
        />
        <StatTile
          label="Needed the stronger model"
          value={n(data.routed_to_model_b)}
          note="comments Model A failed on or was unsure about"
        />
      </section>

      <section className="card">
        <h2>How much the system handled</h2>
        <p className="card-explainer">
          Every “Other” return ends up in exactly one of these. Nothing is dropped silently.
        </p>
        <CoverageBar items={data.coverage} />
        {notHandled > 0 && (
          <p className="card-foot">
            {n(notHandled)} {notHandled === 1 ? "return is" : "returns are"} not in any reason below.{" "}
            <Link href="/gaps">See what was left out and why</Link>
          </p>
        )}
      </section>

      <section className="card">
        <h2>Why things came back</h2>
        <p className="card-explainer">
          Share of the {n(classified?.count ?? 0)} classified comments. Who is likely responsible is set by a fixed
          rule, not by the model.
        </p>
        {classified?.count ? (
          GROUP_ORDER.map((group) => {
            const reasons = data.reasons.filter((r) => r.group === group);
            if (!reasons.length) return null;
            return (
              <div key={group} className="bar-group">
                <h3>{GROUP_TITLES[group]}</h3>
                <BarList
                  unit="returns"
                  max={maxReason}
                  items={reasons.map((r) => ({
                    key: r.reason,
                    label: r.label,
                    note: group === "vendor" ? undefined : r.likely_owner,
                    count: r.count,
                    share: r.share,
                  }))}
                />
              </div>
            );
          })
        ) : (
          <EmptyState title="Nothing was classified in this run">
            Every comment ended up in a gap. <Link href="/gaps">The Gaps page says why.</Link>
          </EmptyState>
        )}
      </section>

      <p className="footnote">
        {data.dropdown_returns_not_analysed > 0 && (
          <>
            {n(data.dropdown_returns_not_analysed)} other returns had a reason picked from the dropdown. They have no
            comment to read and are not part of these numbers.{" "}
          </>
        )}
        Models used: {data.run.model_a_id} (first pass), {data.run.model_b_id} (hard cases). Cost of this run:{" "}
        {data.run.cost_usd === null ? "not tracked" : `$${data.run.cost_usd.toFixed(4)}`}.
      </p>
    </>
  );
}
