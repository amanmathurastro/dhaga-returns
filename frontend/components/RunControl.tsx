"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type RunInfo, type RunList } from "@/lib/api";
import { dateTime } from "@/lib/format";

const POLL_MS = 1500;

/** "Run pipeline" button, optional order-date period, and the live status of the latest run. */
export function RunControl({ onFinished }: { onFinished: () => void }) {
  const [latest, setLatest] = useState<RunInfo | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      const { run_id } = await api.post<{ run_id: string }>("/pipeline/run", {
        period_start: from || null,
        period_end: to || null,
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
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} disabled={running} />
        </label>
        <label>
          to <span className="optional">(optional)</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} disabled={running} />
        </label>
        <button type="button" className="button primary" onClick={start} disabled={running || badPeriod}>
          {running ? "Running…" : "Run pipeline"}
        </button>
      </div>
      <p className="hint">
        Reads every “Other” return comment for those orders, classifies it, and recalculates the vendor numbers.
        Leave the dates empty to include everything.
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
