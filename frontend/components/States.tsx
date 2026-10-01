"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { ApiError, RunInfo } from "@/lib/api";
import type { ApiState } from "@/lib/useApi";
import { dateTime, periodText } from "@/lib/format";

export function PageHeader({ title, explainer, children }: { title: string; explainer: string; children?: ReactNode }) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      <p className="explainer">{explainer}</p>
      {children}
    </header>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden="true" /> {what}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>This page couldn't load.</strong>
      <p>{error.message}</p>
      {onRetry && (
        <button type="button" className="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

/** Renders loading / error / "no run yet", and the page body only when data is ready. */
export function Loaded<T>({
  state,
  onRetry,
  children,
}: {
  state: ApiState<T>;
  onRetry: () => void;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <Loading />;
  if (state.status === "error") {
    if (state.error.code === "no_run") {
      return (
        <EmptyState title="No results yet">
          The pipeline hasn't finished a run. Go to <Link href="/">Summary</Link> and press “Run pipeline”.
        </EmptyState>
      );
    }
    return <ErrorState error={state.error} onRetry={onRetry} />;
  }
  return <>{children(state.data)}</>;
}

export function RunLine({ run }: { run: RunInfo }) {
  return (
    <p className="run-line">
      Results from the run finished {dateTime(run.finished_at)}, covering {periodText(run)}.
    </p>
  );
}

/** Partial state: some comments are missing from the numbers, and the page says so. */
export function PartialNotice({ unclassified, unmatched }: { unclassified: number; unmatched: number }) {
  if (!unclassified && !unmatched) return null;
  const parts = [];
  if (unclassified) parts.push(`${unclassified} couldn't be classified`);
  if (unmatched) parts.push(`${unmatched} couldn't be matched to a vendor`);
  return (
    <div className="notice" role="note">
      <span aria-hidden="true">◐</span>
      <span>
        <strong>These numbers are partial.</strong> Of the comments in this run, {parts.join(" and ")}, so they are
        not counted here. <Link href="/gaps">See what was left out</Link>
      </span>
    </div>
  );
}
