import { useEffect, useState } from "react";
import { Mail, Send } from "lucide-react";
import { ActionButton, Empty, Field, PageHeader, useRemoteList } from "../admin-kit.jsx";

const STATUS = {
  queued: "En file",
  sent: "Envoyé",
  delivered: "Livré",
  bounced: "Rejeté",
  complained: "Signalé",
};

function when(value) {
  if (!value) return "—";
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export default function SiteMailPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-mail", {}, { refreshInterval: 20000 });
  const [audience, setAudience] = useState("one");
  const [customerId, setCustomerId] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");
  const [listError, setListError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState("");
  const customers = result.customers || [];
  const messages = result.messages || [];

  useEffect(() => {
    const onError = (event) => setListError(String(event.detail || "La liste n'a pas pu être actualisée."));
    window.addEventListener("admin:read-error", onError);
    return () => window.removeEventListener("admin:read-error", onError);
  }, []);

  async function openMessage(id) {
    setDetail(null);
    setDetailError("");
    try {
      const response = await fetch(`/admin/api/site-mail?id=${encodeURIComponent(id)}`, { credentials: "same-origin", cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        setDetailError(payload.error || "Message introuvable.");
        return;
      }
      setDetail(payload);
    } catch {
      setDetailError("Impossible de charger ce message.");
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFormError("");
    setDone("");
    try {
      const answer = await onAction({
        action: "site_mail_send",
        audience,
        customer_id: audience === "one" ? customerId : "",
        subject,
        message,
      });
      if (answer?.message) {
        setDone(answer.message);
        setSubject("");
        setMessage("");
        window.dispatchEvent(new CustomEvent("admin:data-synced"));
      }
    } catch (reason) {
      setFormError(reason?.message || "Le message n'a pas pu être envoyé.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="operations-page mail-page">
      <PageHeader
        title="Courrier"
        description="L'historique est en haut : chaque message déjà parti par Resend, et ceux envoyés depuis ici."
      />
      {listError ? <p className="form-error" role="alert">{listError}</p> : null}

      <section className="operations-panel" aria-labelledby="sent-mail-title" aria-busy={loading}>
        <header className="mail-panel-head">
          <h2 id="sent-mail-title">Déjà envoyés</h2>
          <span>{loading ? "Chargement…" : `${messages.length} message${messages.length > 1 ? "s" : ""}`}</span>
        </header>
        {loading && !messages.length ? <div className="operation-loading"><Mail size={18} />Chargement de l'historique…</div> : null}
        {!loading && !messages.length ? (
          <Empty icon={Mail} title="Aucun message envoyé pour le moment." text="Les emails déjà partis par Resend, puis les prochains envois du site, s'affichent dans cette liste." />
        ) : null}
        {messages.length ? (
          <div className="operation-list mail-list">
            {messages.map((item) => (
              <article key={item.id} className={detail?.id === item.id ? "operation-card is-open" : "operation-card"}>
                <header>
                  <span className="operation-icon"><Mail size={18} /></span>
                  <div>
                    <small>{item.kind_label || item.kind} · {when(item.created_at)}</small>
                    <strong>{item.subject || "Sans sujet"}</strong>
                  </div>
                  <span className="status">{STATUS[item.status] || item.status}</span>
                </header>
                <p>{item.to}</p>
                <footer>
                  <ActionButton type="button" secondary icon={Mail} onClick={() => void openMessage(item.id)}>Voir le message</ActionButton>
                </footer>
              </article>
            ))}
          </div>
        ) : null}
        {detailError ? <p className="form-error" role="alert">{detailError}</p> : null}
        {detail ? (
          <article className="mail-reading">
            <h3>{detail.subject}</h3>
            <p>{detail.kind_label || detail.kind} · {detail.to}{detail.name ? ` · ${detail.name}` : ""} · {STATUS[detail.status] || detail.status}</p>
            <pre>{detail.text || "Ce message n'a pas de texte."}</pre>
          </article>
        ) : null}
      </section>

      <section className="mail-compose" aria-labelledby="new-mail-title">
        <h2 id="new-mail-title">Nouveau message</h2>
        {result.from ? <p className="mail-from">De : <strong>{result.from}</strong></p> : null}
        <form className="operation-form" onSubmit={(event) => void submit(event)}>
          <div className="form-grid">
            <Field label="Destinataire">
              <select value={audience} onChange={(event) => setAudience(event.target.value)} aria-label="Destinataire">
                <option value="one">Un client</option>
                <option value="all">Tous les clients ({customers.length})</option>
              </select>
            </Field>
            {audience === "one" ? (
              <Field label="Client">
                <select value={customerId} onChange={(event) => setCustomerId(event.target.value)} required aria-label="Client">
                  <option value="">Choisir…</option>
                  {customers.map((person) => (
                    <option key={person.id} value={person.id}>{person.name} — {person.email}</option>
                  ))}
                </select>
              </Field>
            ) : <span />}
          </div>
          <Field label="Sujet" wide>
            <input value={subject} onChange={(event) => setSubject(event.target.value)} required minLength={3} maxLength={120} />
          </Field>
          <Field label="Message" wide>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} required minLength={8} maxLength={4000} rows={7} />
          </Field>
          {formError ? <p className="form-error" role="alert">{formError}</p> : null}
          {done ? <p className="form-success" role="status">{done}</p> : null}
          {!loading && !customers.length ? <p>Aucun client pour le moment.</p> : null}
          <div className="dialog-actions">
            <ActionButton icon={Send} type="submit" disabled={busy || !customers.length}>
              {busy ? "Envoi…" : "Envoyer"}
            </ActionButton>
          </div>
        </form>
      </section>
    </div>
  );
}
