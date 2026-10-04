import { useState } from "react";
import { Check, Trash2, UserRound, X } from "lucide-react";
import { ActionButton, Empty, PageHeader, useRemoteList } from "../admin-kit.jsx";
import { dinars } from "../site-format.jsx";

const STATUS = {
  pending: "En attente",
  approved: "Publié",
  rejected: "Refusé",
};

const SOURCE = {
  email: "Depuis l'email",
  account: "Depuis le compte",
};

function when(stamp) {
  if (!stamp) return "—";
  return new Date(stamp * 1000).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

export default function SiteReviewsPage({ onAction, onNavigate }) {
  const [result, loading] = useRemoteList("/admin/api/site-reviews", {}, { refreshInterval: 10000 });
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [count, setCount] = useState(null);
  const items = result.items || [];
  const refresh = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));

  async function run(payload) {
    const completed = await onAction(payload);
    if (completed) {
      setRejecting(null);
      setRemoving(null);
      setNote("");
      refresh();
    }
  }

  return (
    <div className="operations-page">
      <PageHeader title="Avis" description="Un avis envoyé depuis l'email de livraison arrive ici. Il reste privé jusqu'à publication." />
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
            <strong>{item.name || "Client"}</strong>
            <small>{item.score}/5 · {STATUS[item.status] || item.status} · {SOURCE[item.source] || item.source}</small>
            <p>{item.comment}</p>
            <dl className="site-facts">
              <div><dt>Email</dt><dd>{item.email || "—"}</dd></div>
              <div><dt>Téléphone</dt><dd>{item.phone || "—"}</dd></div>
              <div><dt>Client</dt><dd>#{item.customer_id || "—"}{item.email_verified ? " · email vérifié" : ""}</dd></div>
              <div><dt>Compte créé</dt><dd>{when(item.customer_created_at)}</dd></div>
              <div><dt>Commande</dt><dd>#{item.order_id} · {item.cart_reference || "—"}</dd></div>
              <div><dt>Offre</dt><dd>{[item.service_name, item.offer_name].filter(Boolean).join(" · ") || "—"}</dd></div>
              <div><dt>Paiement</dt><dd>{item.payment_label || "—"} · {dinars(item.cart_total_millimes || item.line_total_millimes)}</dd></div>
              <div><dt>Livré le</dt><dd>{when(item.delivered_at)}</dd></div>
              <div><dt>Avis reçu</dt><dd>{when(item.created_at)}</dd></div>
              {item.published_at ? <div><dt>Publié le</dt><dd>{when(item.published_at)}</dd></div> : null}
              {item.admin_note ? <div><dt>Motif</dt><dd>{item.admin_note}</dd></div> : null}
            </dl>
            <div>
              {item.customer_id && onNavigate ? (
                <button type="button" className="site-link" onClick={() => onNavigate("site-customers", item.customer_id, { search: item.email || item.name || "" })}>
                  <UserRound size={14} /> Ouvrir le client
                </button>
              ) : null}
              {item.cart_reference && onNavigate ? (
                <button type="button" className="site-link" onClick={() => onNavigate("site-orders", item.cart_reference, { search: item.cart_reference, status: "all" })}>
                  Voir la commande
                </button>
              ) : null}
              {item.status === "pending" ? (
                <>
                  <ActionButton icon={Check} onClick={() => run({ action: "site_review_approve", review_id: item.id })}>Publier</ActionButton>
                  <ActionButton danger icon={X} onClick={() => { setRejecting(item.id); setRemoving(null); }}>Refuser</ActionButton>
                </>
              ) : null}
              <ActionButton danger icon={Trash2} onClick={() => { setRemoving(item.id); setRejecting(null); }}>Supprimer</ActionButton>
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
              {removing === item.id ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run({ action: "site_review_delete", review_id: item.id });
                  }}
                >
                  <span>Supprimer cet avis ?</span>
                  <button type="submit">Confirmer la suppression</button>
                </form>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
