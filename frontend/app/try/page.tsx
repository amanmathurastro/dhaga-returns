"use client";

import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/States";
import { api, ApiError, type Preview } from "@/lib/api";

const EXAMPLES = [
  "size bahut chhota hai, L manga tha par M jaisa fit aaya",
  "size chhota aur colour bhi photo se alag hai",
  "packet phata hua aaya, saree pe daag lag gaya tha",
  "pls call 9812345678 silai khul gayi",
  "accha nahi laga",
  "👍",
];

type Result = { status: "idle" } | { status: "loading" } | { status: "error"; message: string } | { status: "done"; data: Preview };

export default function TryPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Result>({ status: "idle" });

  async function classify(event?: FormEvent) {
    event?.preventDefault();
    setResult({ status: "loading" });
    try {
      setResult({ status: "done", data: await api.post<Preview>("/classify/preview", { text }) });
    } catch (err) {
      setResult({ status: "error", message: err instanceof ApiError ? err.message : "Something went wrong." });
    }
  }

  return (
    <>
      <PageHeader
        title="Try a comment"
        explainer="Paste one return comment and see exactly what the system does with it, including when it fails."
      />
      <form className="card" onSubmit={classify}>
        <label htmlFor="comment">Return comment (Hinglish, Hindi or English)</label>
        <textarea
          id="comment"
          rows={3}
          maxLength={2000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. kurta tight hai shoulders pe"
        />
        <div className="examples">
          <span>Examples:</span>
          {EXAMPLES.map((example) => (
            <button type="button" className="chip" key={example} onClick={() => setText(example)}>
              {example}
            </button>
          ))}
        </div>
        <button type="submit" className="button primary" disabled={result.status === "loading"}>
          {result.status === "loading" ? "Classifying…" : "Classify"}
        </button>
      </form>

      {result.status === "loading" && (
        <div className="state" role="status">
          <span className="spinner" aria-hidden="true" /> Asking the model…
        </div>
      )}
      {result.status === "error" && (
        <div className="state state-error" role="alert">
          <strong>Couldn't classify this comment.</strong>
          <p>{result.message}</p>
        </div>
      )}
      {result.status === "done" && <PreviewResult data={result.data} />}
    </>
  );
}

function PreviewResult({ data }: { data: Preview }) {
  const c = data.classification;
  const sent = <Row label={data.status === "junk" ? "After removing phone numbers and emails" : "What was sent to the model"} value={data.scrubbed_text || "(blank)"} />;

  if (data.status === "junk") {
    return (
      <section className="card" aria-live="polite">
        <p className="eyebrow">Result</p>
        <h2>Junk text</h2>
        <dl className="result">
          {sent}
          <Row label="What happened" value={data.detail ?? "Not sent to a model."} />
        </dl>
      </section>
    );
  }

  if (data.status === "unclassified" || !c) {
    return (
      <section className="card" aria-live="polite">
        <p className="eyebrow">Result</p>
        <div className="state state-error" role="alert">
          <strong>Couldn't classify</strong>
          <p>
            Both models were tried and neither gave an answer the system trusts, so this comment would be left for a
            person instead of being forced into a reason.
          </p>
          {data.detail && <p>{data.detail}</p>}
        </div>
        <dl className="result">
          {sent}
          <Row label="Confidence needed" value={data.confidence_threshold.toFixed(2)} />
        </dl>
      </section>
    );
  }

  return (
    <section className="card" aria-live="polite">
      <p className="eyebrow">Result</p>
      <h2>{data.reason_label}</h2>
      <dl className="result">
        {data.fit_direction_label && <Row label="Kind of fit problem" value={data.fit_direction_label} />}
        {c.fit_area && <Row label="Where" value={c.fit_area} />}
        {c.secondary_reason && <Row label="Also mentions" value={c.secondary_reason} />}
        <Row label="In English" value={c.gist_en} />
        <Row label="Likely owner (fixed rule)" value={data.likely_owner ?? "–"} />
        <Row
          label="Read by"
          value={data.model_used === "B" ? "Model B, after Model A failed or was unsure" : "Model A, first pass"}
        />
        <Row
          label="Confidence"
          value={`${c.confidence.toFixed(2)} (needs at least ${data.confidence_threshold.toFixed(2)})`}
        />
        {sent}
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
