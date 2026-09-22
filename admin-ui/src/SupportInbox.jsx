import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Archive, Headphones, MessageSquareText, Search, Send } from "lucide-react";
import "./support.css";

const labels = { open: "Ouvert", waiting_admin: "Attente admin", waiting_customer: "Attente client", closed: "Fermé", resolved: "Résolu" };
const categories = { payment: "Paiement", order: "Commande", delivery: "Livraison", other: "Général", catalog_request: "Catalogue" };
const customer = (ticket) => ticket.username ? `@${ticket.username}` : ticket.full_name || `Client ${ticket.user_id}`;
const stamp = (value) => {
  const parsed = new Date(typeof value === "number" ? value * 1000 : value);
  return value && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
};

function Conversation({ ticket, onAction, onBack, draft, setDraft, onStatus }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const thread = useRef(null);
  const nearBottom = useRef(true);
  const closed = ["closed", "resolved"].includes(ticket.status);

  useEffect(() => {
    let active = true;
    let controller;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch(`/admin/api/ticket-messages?ticket_id=${ticket.id}`, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Impossible de charger les messages. Réessayez.");
        const payload = await response.json();
        if (active) { setMessages(Array.isArray(payload) ? payload : payload.messages || []); setError(""); }
      } catch (err) { if (active && err.name !== "AbortError") setError(err.message); }
      finally { if (active) setLoading(false); }
    };
    const refresh = () => { if (document.visibilityState === "visible") load(); };
    load();
    const timer = window.setInterval(refresh, 10000);
    window.addEventListener("admin:data-synced", refresh);
    return () => { active = false; controller?.abort(); window.clearInterval(timer); window.removeEventListener("admin:data-synced", refresh); };
  }, [ticket.id, version]);

  useEffect(() => {
    if (nearBottom.current && thread.current) thread.current.scrollTop = thread.current.scrollHeight;
  }, [messages]);

  const send = async (event) => {
    event.preventDefault();
    if (busy || !draft.trim()) return;
    setBusy(true);
    try {
      if (await onAction({ action: "reply_ticket", ticket_id: ticket.id, message: draft.trim() })) {
        setDraft(""); nearBottom.current = true; setVersion((n) => n + 1); onStatus("waiting_customer");
      }
    } finally { setBusy(false); }
  };

  return <section className="support-conversation" aria-label={`Conversation avec ${customer(ticket)}`}>
    <header className="support-chat-header">
      <button className="support-back" onClick={onBack} aria-label="Retour aux conversations"><ArrowLeft size={20} /></button>
      <span className="support-avatar"><Headphones size={21} /></span>
      <div className="support-chat-identity"><strong>{customer(ticket)}</strong><small>Ticket #{ticket.id} · {categories[ticket.category] || ticket.category || "Général"}</small></div>
      <span className={`status ${ticket.status}`}>{labels[ticket.status] || ticket.status}</span>
      <button className="support-close" aria-label={closed ? "Ticket fermé" : "Fermer le ticket"} disabled={busy || closed} onClick={async () => {
        setBusy(true);
        try { if (await onAction({ action: "close_ticket", ticket_id: ticket.id })) onStatus("closed"); }
        finally { setBusy(false); }
      }}><Archive size={16} /><span>{closed ? "Ticket fermé" : "Fermer le ticket"}</span></button>
    </header>
    <div className="support-messages" ref={thread} role="log" aria-label="Messages de la conversation" onScroll={() => {
      const el = thread.current; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }}>
      <div className="support-thread-intro"><span className="support-avatar"><UserInitial ticket={ticket} /></span><strong>{customer(ticket)}</strong><p>Début de la conversation · Ticket #{ticket.id}</p></div>
      {loading && <p className="support-notice" role="status">Chargement des messages…</p>}
      {error && <div className="support-notice" role="alert">{error} <button onClick={() => setVersion((n) => n + 1)}>Réessayer</button></div>}
      {!loading && !error && !messages.length && <p className="support-notice">Aucun message dans cette conversation.</p>}
      {messages.map((message, index) => <article key={message.id || index} className={`support-bubble ${message.sender_type === "admin" ? "is-admin" : "is-customer"}`}>
        <small>{message.sender_type === "admin" ? "Vous" : "Client"}</small>
        <p>{message.message || message.content}</p>
        <time>{stamp(message.created_at)}</time>
      </article>)}
    </div>
    <form className="support-composer" onSubmit={send}>
      <div><textarea aria-label="Votre réponse" placeholder="Écrivez votre réponse…" value={draft} disabled={busy} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(event); }
      }} maxLength={2000} rows={2} /><button type="submit" disabled={busy || !draft.trim()} aria-label="Envoyer la réponse"><Send size={20} /></button></div>
      <small>{busy ? "Enregistrement en cours…" : "Entrée pour envoyer · Maj + Entrée pour une nouvelle ligne"}</small>
    </form>
  </section>;
}

function UserInitial({ ticket }) { return String(ticket.full_name || ticket.username || ticket.user_id || "C").slice(0, 2).toUpperCase(); }

export default function SupportInbox({ result, loading, search, setSearch, status, setStatus, searchField, setSearchField, targetTicketId, pagination, onAction }) {
  const [selected, setSelected] = useState(null);
  const [drafts, setDrafts] = useState({});
  useEffect(() => {
    setSelected((previous) => result.items.find((item) => item.id === previous?.id) || previous);
  }, [result.items]);
  useEffect(() => {
    if (!targetTicketId) return;
    const match = result.items.find((item) => String(item.id) === String(targetTicketId));
    if (match) setSelected(match);
  }, [result.items, targetTicketId]);
  const current = selected;
  return <div className="support-page">
    <div className="support-heading"><div><span className="eyebrow">Assistance</span><h2>Messagerie</h2></div><span><MessageSquareText size={16} /> Support clients</span></div>
    <div className={`support-inbox ${current ? "has-conversation" : ""}`}>
      <aside className="support-sidebar" aria-label="Conversations">
        <header><h3>Conversations</h3><span>{result.total}</span></header>
        <div className="support-filters">
          <label className="support-search"><Search size={17} /><input type="search" aria-label="Rechercher une conversation" placeholder="Rechercher une conversation…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <div><select aria-label="Champ de recherche" value={searchField} onChange={(event) => setSearchField(event.target.value)}>{[["all", "Tout rechercher"], ["ticket_id", "ID ticket"], ["user_id", "ID client"], ["category", "Catégorie"], ["message", "Message"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          <select aria-label="Filtrer les conversations par statut" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Tous les statuts</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        </div>
        <div className="support-list" aria-busy={loading}>
          {loading && <p className="support-notice" role="status">Actualisation…</p>}
          {!loading && !result.items.length && <div className="support-list-empty"><Search size={26} /><strong>Aucune conversation</strong><p>Essayez une autre recherche ou un autre statut.</p></div>}
          {result.items.map((ticket) => <button key={ticket.id} className={`support-contact ${current?.id === ticket.id ? "is-selected" : ""}`} aria-pressed={current?.id === ticket.id} onClick={() => setSelected(ticket)}>
            <span className="support-avatar"><UserInitial ticket={ticket} /></span>
            <span className="support-contact-copy"><span><strong>{customer(ticket)}</strong>{ticket.status === "waiting_admin" && <i aria-label="Réponse attendue" />}</span><small>{ticket.last_message || ticket.message || categories[ticket.category] || ticket.category || "Conversation support"}</small><span className="support-contact-meta"><span>#{ticket.id} · {labels[ticket.status] || ticket.status}</span><time>{stamp(ticket.updated_at || ticket.created_at)}</time></span></span>
          </button>)}
        </div>
        {pagination}
      </aside>
      {current ? <Conversation key={current.id} ticket={current} onAction={onAction} onBack={() => setSelected(null)} draft={drafts[current.id] || ""} setDraft={(value) => setDrafts((prev) => ({ ...prev, [current.id]: value }))} onStatus={(value) => setSelected({ ...current, status: value })} /> : <section className="support-welcome"><span><MessageSquareText size={35} /></span><h3>Vos conversations, au même endroit.</h3><p>Sélectionnez un client pour consulter ses messages et lui répondre directement.</p><small><Headphones size={14} /> Support BlackMarket</small></section>}
    </div>
  </div>;
}
