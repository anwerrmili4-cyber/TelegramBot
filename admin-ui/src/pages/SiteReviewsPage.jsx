import { useState } from "react";
import { Check, Package, Star, Trash2, UserRound, X } from "lucide-react";
import { ActionButton, Empty, PageHeader, useRemoteList } from "../admin-kit.jsx";
import { dinars } from "../site-format.jsx";

const STATUS = {
  pending: ["En attente", ""],
  approved: ["Publié", "delivered"],
  rejected: ["Refusé", "rejected"],
};

const SOURCE = {
  email: "Depuis l'email",
  account: "Depuis le compte",
};

const FILTERS = [
  ["pending", "En attente"],
  ["approved", "Publiés"],
  ["rejected", "Refusés"],
  ["all", "Tous"],
];

function when(stamp) {
  if (!stamp) return "—";
  return new Date(stamp * 1000).toLocaleString("fr-FR", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Stars({ score }) {
  const value = Math.max(0, Math.min(5, Number(score) || 0));
  return (
    <span className="review-stars" aria-label={`${value} sur 5`}>
      {[1, 2, 3, 4, 5].map((step) => (
        <span key={step} className={step <= value ? "is-on" : ""}>★</span>
      ))}
    </span>
  );
}

export default function SiteReviewsPage({ onAction, onNavigate }) {
  const [result, loading] = useRemoteList("/admin/api/site-reviews", {}, { refreshInterval: 10000 });
  const [note, setNote] = useState("");
  const [filter, setFilter] = useState("pending");
  const [rejecting, setRejecting] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [count, setCount] = useState(null);
  const items = result.items || [];
  const visible = filter === "all" ? items : items.filter((item) => item.status === filter);
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
    <div className="operations-page site-page review-board">
      <PageHeader title="Avis" description="Un avis reste privé jusqu'à publication. Le dossier du client est sur la carte." />
      <div className="review-toolbar">
        <div className="site-tabs" role="tablist" aria-label="Filtrer les avis">
          {FILTERS.map(([id, label]) => {
            const total = id === "all" ? items.length : items.filter((item) => item.status === id).length;
            return (
              <button key={id} type="button" role="tab" aria-selected={filter === id} onClick={() => setFilter(id)}>
                {label} <small>{total}</small>
              </button>
            );
          })}
        </div>
        <button
          type="button"
          className="review-tool"
          onClick={async () => {
            const answer = await onAction({ action: "site_review_backfill" });
            if (answer && typeof answer.count === "number") setCount(answer.count);
          }}
        >
          Emails d'avis manquants{count === null ? "" : ` · ${count}`}
        </button>
      </div>
      {loading && !items.length ? <p>Chargement…</p> : null}
      {!loading && !visible.length ? (
        <Empty
          icon={Star}
          title={items.length ? "Aucun avis dans ce filtre" : "Aucun avis"}
          text={items.length ? "Changez de filtre pour voir les autres avis." : "Les avis envoyés après une livraison apparaîtront ici."}
        />
      ) : null}
      <div className="review-list">
        {visible.map((item) => {
          const [label, statusClass] = STATUS[item.status] || [item.status, ""];
          const initial = (item.name || item.email || "?").trim().slice(0, 1).toUpperCase();
          const pending = item.status === "pending";
          return (
            <article key={item.id} className={`review-card is-${item.status}`}>
              <header>
                <span className="review-avatar" aria-hidden="true">{initial}</span>
                <div className="review-identity">
                  <div className="review-name">
                    <strong>{item.name || "Client"}</strong>
                    <span className={`status ${statusClass}`}>{label}</span>
                  </div>
                  <small>{item.email || "Sans email"}</small>
                  <span>{item.phone || "Pas de téléphone"}</span>
                </div>
              </header>
              <div className="review-score">
                <Stars score={item.score} />
                <b>{item.score}/5</b>
                <em>{SOURCE[item.source] || item.source}</em>
              </div>
              <blockquote>{item.comment}</blockquote>
              <dl className="review-facts">
                <div><dt>Client</dt><dd>#{item.customer_id || "—"}{item.email_verified ? " · vérifié" : ""}</dd></div>
                <div><dt>Compte créé</dt><dd>{when(item.customer_created_at)}</dd></div>
                <div><dt>Commande</dt><dd>#{item.order_id} · {item.cart_reference || "—"}</dd></div>
                <div><dt>Livré le</dt><dd>{when(item.delivered_at)}</dd></div>
                <div><dt>Paiement</dt><dd>{item.payment_label || "—"} · {dinars(item.cart_total_millimes || item.line_total_millimes)}</dd></div>
                <div><dt>Avis reçu</dt><dd>{when(item.created_at)}</dd></div>
                <div className="wide"><dt>Offre</dt><dd>{[item.service_name, item.offer_name].filter(Boolean).join(" · ") || "—"}</dd></div>
                {item.published_at ? <div><dt>Publié le</dt><dd>{when(item.published_at)}</dd></div> : null}
                {item.admin_note ? <div className="wide"><dt>Motif</dt><dd>{item.admin_note}</dd></div> : null}
              </dl>
              <div className="review-links">
                {item.customer_id && onNavigate ? (
                  <button type="button" className="site-link" onClick={() => onNavigate("site-customers", item.customer_id, { search: item.email || item.name || "" })}>
                    <UserRound size={14} /> Ouvrir le client
                  </button>
                ) : null}
                {item.cart_reference && onNavigate ? (
                  <button type="button" className="site-link" onClick={() => onNavigate("site-orders", item.cart_reference, { search: item.cart_reference, status: "all" })}>
                    <Package size={14} /> Voir la commande
                  </button>
                ) : null}
              </div>
              <div className={`review-actions${pending ? " has-publish" : ""}`}>
                {pending ? (
                  <>
                    <ActionButton icon={Check} onClick={() => run({ action: "site_review_approve", review_id: item.id })}>Publier</ActionButton>
                    <ActionButton danger icon={X} onClick={() => { setRejecting(item.id); setRemoving(null); setNote(""); }}>Refuser</ActionButton>
                  </>
                ) : null}
                <ActionButton danger icon={Trash2} onClick={() => { setRemoving(item.id); setRejecting(null); }}>Supprimer</ActionButton>
              </div>
              {rejecting === item.id ? (
                <form
                  className="review-confirm"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run({ action: "site_review_reject", review_id: item.id, admin_note: note });
                  }}
                >
                  <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Motif du refus" required minLength={3} />
                  <div>
                    <button type="button" onClick={() => setRejecting(null)}>Annuler</button>
                    <button type="submit">Confirmer le refus</button>
                  </div>
                </form>
              ) : null}
              {removing === item.id ? (
                <form
                  className="review-confirm"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run({ action: "site_review_delete", review_id: item.id });
                  }}
                >
                  <p>Supprimer cet avis ? Il disparaît aussi de la boutique.</p>
                  <div>
                    <button type="button" onClick={() => setRemoving(null)}>Annuler</button>
                    <button type="submit">Confirmer</button>
                  </div>
                </form>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
