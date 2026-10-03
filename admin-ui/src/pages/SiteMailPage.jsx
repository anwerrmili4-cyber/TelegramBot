import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { ActionButton, Field, PageHeader, useRemoteList } from "../admin-kit.jsx";

function when(value) {
  if (!value) return "—";
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export default function SiteMailPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-mail", {}, { refreshInterval: 15000 });
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
      const response = await fetch(`/admin/api/site-mail?id=${id}`, { credentials: "same-origin", cache: "no-store" });
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
    <div className="operations-page">
      <PageHeader
        title="Courrier"
        description="Les messages automatiques et ceux que tu envoies. L'adresse d'expédition est celle du domaine."
      />
      {loading && !result.from ? <p>Chargement…</p> : null}
      {listError ? <p role="alert">{listError}</p> : null}

      <section aria-labelledby="sent-mail-title">
        <h2 id="sent-mail-title">Déjà envoyés</h2>
        {!loading && !messages.length ? <p>Aucun message envoyé pour le moment.</p> : null}
        <ul>
          {messages.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => void openMessage(item.id)}>
                <strong>{item.subject}</strong>
                <small>{item.kind_label || item.kind} · {item.to} · {when(item.created_at)} · {item.status === "queued" ? "En file" : item.status}</small>
              </button>
            </li>
          ))}
        </ul>
        {detailError ? <p role="alert">{detailError}</p> : null}
        {detail ? (
          <article>
            <h3>{detail.subject}</h3>
            <p>{detail.kind_label || detail.kind} · {detail.to}{detail.name ? ` · ${detail.name}` : ""}</p>
            <pre>{detail.text}</pre>
          </article>
        ) : null}
      </section>

      <section aria-labelledby="new-mail-title">
        <h2 id="new-mail-title">Nouveau message</h2>
        {result.from ? <p>De : <strong>{result.from}</strong></p> : null}
        <form onSubmit={(event) => void submit(event)}>
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
          ) : null}
          <Field label="Sujet">
            <input value={subject} onChange={(event) => setSubject(event.target.value)} required minLength={3} maxLength={120} />
          </Field>
          <Field label="Message">
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} required minLength={8} maxLength={4000} rows={8} />
          </Field>
          {formError ? <p role="alert">{formError}</p> : null}
          {done ? <p role="status">{done}</p> : null}
          {!loading && !customers.length ? <p>Aucun client pour le moment.</p> : null}
          <ActionButton icon={Send} type="submit" disabled={busy || !customers.length}>
            {busy ? "Envoi…" : "Envoyer"}
          </ActionButton>
        </form>
      </section>
    </div>
  );
}
