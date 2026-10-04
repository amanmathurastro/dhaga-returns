"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type DateRange, type RunInfo, type RunList } from "@/lib/api";
import { dateTime, day } from "@/lib/format";

const POLL_MS = 1500;

/**
 * "Run pipeline" button, the order-date period, and the live status of the latest run.
 *
 * The period starts filled with the dates of the results on screen (`shownRun`): its own
 * period if it had one, otherwise the first and last order dates in the data.
 */
export function RunControl({ onFinished, shownRun }: { onFinished: () => void; shownRun?: RunInfo | null }) {
  const [latest, setLatest] = useState<RunInfo | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [range, setRange] = useState<DateRange | null>(null);
  const [edited, setEdited] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api
      .get<DateRange>("/pipeline/date-range")
      .then(setRange)
      .catch(() => {
        // Without the range the boxes just start empty, which still means "all dates".
      });
  }, []);

  // Follow the results on screen until the person types their own dates.
  useEffect(() => {
    if (edited) return;
    setFrom(shownRun?.period_start ?? range?.first_order_date ?? "");
    setTo(shownRun?.period_end ?? range?.last_order_date ?? "");
  }, [shownRun, range, edited]);

  const poll = useCallback(
    (runId: string) => {
      timer.current = setTimeout(async () => {
        try {
          const run = await api.get<RunInfo>(`/pipeline/runs/${runId}`);
          setLatest(run);
          if (run.status === "running") poll(runId);
          else onFinished();
        } catch (err) {
          setProblem(err instanceof ApiError ? err.message : "Lost track of the run. Reload the page.");
        }
      }, POLL_MS);
    },
    [onFinished],
  );

  useEffect(() => {
    api
      .get<RunList>("/pipeline/runs?limit=1")
      .then(({ runs }) => {
        const run = runs[0] ?? null;
        setLatest(run);
        if (run?.status === "running") poll(run.run_id);
      })
      .catch(() => {
        // The page body below already shows the backend error.
      });
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll]);

  const running = starting || latest?.status === "running";
  const badPeriod = Boolean(from && to && from > to);

  async function start() {
    setProblem(null);
    setStarting(true);
    try {
      // The whole span of the data means "all dates": send no filter, so returns that
      // can't be matched to an order (dated by their return date) are not cut off.
      const wholeRange = from === range?.first_order_date && to === range?.last_order_date;
      const { run_id } = await api.post<{ run_id: string }>("/pipeline/run", {
        period_start: wholeRange ? null : from || null,
        period_end: wholeRange ? null : to || null,
      });
      setLatest({ run_id, status: "running" } as RunInfo);
      poll(run_id);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : "Couldn't start the run.");
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="card run-control" aria-label="Run the pipeline">
      <div className="run-fields">
        <label>
          Orders placed from <span className="optional">(optional)</span>
          <input
            type="date"
            value={from}
            min={range?.first_order_date ?? undefined}
            max={range?.last_order_date ?? undefined}
            onChange={(e) => {
              setEdited(true);
              setFrom(e.target.value);
            }}
            disabled={running}
          />
        </label>
        <label>
          to <span className="optional">(optional)</span>
          <input
            type="date"
            value={to}
            min={range?.first_order_date ?? undefined}
            max={range?.last_order_date ?? undefined}
            onChange={(e) => {
              setEdited(true);
              setTo(e.target.value);
            }}
            disabled={running}
          />
        </label>
        <button type="button" className="button primary" onClick={start} disabled={running || badPeriod}>
          {running ? "Running…" : "Run pipeline"}
        </button>
      </div>
      <p className="hint">
        Reads every “Other” return comment for orders placed in these dates, classifies it, and recalculates the
        vendor numbers. The dates start as the period of the results shown below
        {range?.first_order_date && range?.last_order_date
          ? `; the data covers ${day(range.first_order_date)} to ${day(range.last_order_date)}.`
          : "."}{" "}
        Clear both boxes to include everything.
      </p>
      {badPeriod && <p className="inline-error">The “from” date is after the “to” date.</p>}
      {running && (
        <p className="status-line" role="status">
          <span className="spinner" aria-hidden="true" /> Pipeline is running. This page updates when it finishes.
        </p>
      )}
      {problem && (
        <p className="inline-error" role="alert">
          {problem}
        </p>
      )}
      {!running && latest?.status === "failed" && (
        <div className="state state-error" role="alert">
          <strong>The last run failed ({dateTime(latest.finished_at)}).</strong>
          <p>{latest.error ?? "No reason was recorded."}</p>
          <p>Anything shown below is from the last run that finished successfully.</p>
        </div>
      )}
    </section>
  );
}
