import { useState } from "react";
import { Check, X } from "lucide-react";
import { ActionButton, Empty, PageHeader, useRemoteList } from "../admin-kit.jsx";

const STATUS = {
  pending: "En attente",
  approved: "Publié",
  rejected: "Refusé",
};

export default function SiteReviewsPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-reviews", {}, { refreshInterval: 10000 });
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(null);
  const [count, setCount] = useState(null);
  const items = result.items || [];
  const refresh = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));

  async function run(payload) {
    const completed = await onAction(payload);
    if (completed) {
      setRejecting(null);
      setNote("");
      refresh();
    }
  }

  return (
    <div className="operations-page">
      <PageHeader title="Avis" description="Un avis reste privé jusqu'à publication. Le nom affiché est celui du compte." />
      <p>
        <button
          type="button"
          onClick={async () => {
            const answer = await onAction({ action: "site_review_backfill" });
            if (answer && typeof answer.count === "number") setCount(answer.count);
          }}
        >
          Compter les emails d'avis non envoyés{count === null ? "" : ` (${count})`}
        </button>
      </p>
      {loading && !items.length ? <p>Chargement…</p> : null}
      {!loading && !items.length ? <Empty title="Aucun avis" text="Les avis envoyés après une livraison apparaîtront ici." /> : null}
      <div className="order-list">
        {items.map((item) => (
          <article key={item.id}>
            <strong>{item.name}</strong>
            <small>{item.email} · {item.offer_name} · {item.score}/5 · {STATUS[item.status] || item.status}</small>
            <p>{item.comment}</p>
            {item.admin_note ? <small>Motif : {item.admin_note}</small> : null}
            {item.status === "pending" ? (
              <div>
                <ActionButton icon={Check} onClick={() => run({ action: "site_review_approve", review_id: item.id })}>Publier</ActionButton>
                <ActionButton danger icon={X} onClick={() => setRejecting(item.id)}>Refuser</ActionButton>
                {rejecting === item.id ? (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void run({ action: "site_review_reject", review_id: item.id, admin_note: note });
                    }}
                  >
                    <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Motif du refus" required minLength={3} />
                    <button type="submit">Confirmer le refus</button>
                  </form>
                ) : null}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
