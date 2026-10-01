import type { Comment } from "@/lib/api";

/** Real customer comments (PII already removed by the backend) with the model's English gist. */
export function CommentList({ comments }: { comments: Comment[] }) {
  return (
    <ul className="comments">
      {comments.map((c) => (
        <li key={c.return_id} id={c.return_id}>
          <blockquote>“{c.text}”</blockquote>
          {c.gist_en && <p className="gist">In English: {c.gist_en}</p>}
          <p className="meta">
            {c.reason_label && <span className="tag">{c.reason_label}</span>}
            {c.fit_direction_label && <span className="tag">{c.fit_direction_label}</span>}
            {c.secondary_reason && <span>Also mentions: {c.secondary_reason}</span>}
            {c.product_name && <span>{c.product_name}{c.size ? `, size ${c.size}` : ""}</span>}
            <span>{c.return_id}</span>
            {c.model_used && c.model_used !== "none" && <span>Read by Model {c.model_used}</span>}
          </p>
        </li>
      ))}
    </ul>
  );
}
