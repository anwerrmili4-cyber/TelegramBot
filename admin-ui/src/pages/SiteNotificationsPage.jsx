import { useState } from "react";
import { Bell, Send } from "lucide-react";
import { ActionButton, Empty, Field, PageHeader, useRemoteList } from "../admin-kit.jsx";

function when(value) {
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export default function SiteNotificationsPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-notifications", {}, { refreshInterval: 20000 });
  const [kind, setKind] = useState("news");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [offerId, setOfferId] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const offers = result.offers || [];
  const items = result.items || [];

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setDone("");
    try {
      const answer = await onAction({
        action: "site_notify_publish",
        kind,
        title,
        body,
        offer_id: kind === "novelty" ? offerId : "",
      });
      if (answer?.message) {
        setDone(answer.message);
        setTitle("");
        setBody("");
        setOfferId("");
        window.dispatchEvent(new CustomEvent("admin:data-synced"));
      }
    } catch (reason) {
      setError(reason?.message || "La notification n'a pas pu être publiée.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="operations-page">
      <PageHeader
        title="Notifications"
        description="Les clients vérifiés voient la nouveauté, le message ou l'actualité dans leur cloche. Aucun email n'est envoyé."
      />
      <section className="mail-compose" aria-labelledby="notify-form-title">
        <h2 id="notify-form-title">Publier</h2>
        <form className="operation-form" onSubmit={(event) => void submit(event)}>
          <div className="form-grid">
            <Field label="Type">
              <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Type">
                <option value="novelty">Nouveauté</option>
                <option value="admin">Message</option>
                <option value="news">Actualité</option>
              </select>
            </Field>
            {kind === "novelty" ? (
              <Field label="Produit">
                <select value={offerId} onChange={(event) => setOfferId(event.target.value)} required aria-label="Produit">
                  <option value="">Choisir…</option>
                  {offers.map((offer) => (
                    <option key={offer.id} value={offer.id}>{offer.service_name} — {offer.name}</option>
                  ))}
                </select>
              </Field>
            ) : <span />}
          </div>
          <Field label="Titre" wide>
            <input value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} maxLength={120} />
          </Field>
          <Field label="Message" wide>
            <textarea value={body} onChange={(event) => setBody(event.target.value)} required minLength={8} maxLength={2000} rows={6} />
          </Field>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {done ? <p className="form-success" role="status">{done}</p> : null}
          <div className="dialog-actions">
            <ActionButton icon={Send} type="submit" disabled={busy}>
              {busy ? "Publication…" : "Publier"}
            </ActionButton>
          </div>
        </form>
      </section>
      <section className="operations-panel" aria-labelledby="notify-history-title">
        <header className="notify-head">
          <h2 id="notify-history-title">Déjà publiées</h2>
          <span>{loading ? "Chargement…" : `${items.length} notification${items.length > 1 ? "s" : ""}`}</span>
        </header>
        {!loading && !items.length ? (
          <Empty icon={Bell} title="Aucune notification publiée." text="Les nouveautés, messages et actualités apparaîtront ici." />
        ) : null}
        {items.length ? (
          <div className="operation-list">
            {items.map((item) => (
              <article key={item.id} className="operation-card">
                <header>
                  <span className="operation-icon"><Bell size={18} /></span>
                  <div>
                    <small>{item.kind_label} · {when(item.created_at)}</small>
                    <strong>{item.title}</strong>
                  </div>
                </header>
                <p>{item.body}</p>
                <footer>
                  <span>{item.audience_count} client{item.audience_count > 1 ? "s" : ""}</span>
                </footer>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
