import type { RunInfo } from "./api";

const number = new Intl.NumberFormat("en-IN");

export const n = (value: number) => number.format(value);

/** 0.0842 -> "8.4%" */
export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "–";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Lift is shown in plain words, never as "lift". 3.11 -> "3.1× category average" */
export function timesAverage(lift: number | null | undefined): string {
  if (lift === null || lift === undefined) return "no category average to compare";
  return `${lift.toFixed(1)}× category average`;
}

const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
});

export function day(iso: string | null): string {
  return iso ? dateFmt.format(new Date(`${iso}T00:00:00`)) : "";
}

export function dateTime(iso: string | null): string {
  return iso ? dateTimeFmt.format(new Date(iso)) : "";
}

export function periodText(run: Pick<RunInfo, "period_start" | "period_end">): string {
  const { period_start: from, period_end: to } = run;
  if (from && to) return `orders placed ${day(from)} to ${day(to)}`;
  if (from) return `orders placed from ${day(from)}`;
  if (to) return `orders placed up to ${day(to)}`;
  return "orders from all dates";
}
