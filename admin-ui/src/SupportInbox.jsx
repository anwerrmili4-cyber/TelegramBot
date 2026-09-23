import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Archive, ArchiveRestore, CheckCheck, ExternalLink, Headphones, Image as ImageIcon, MessageSquareText, Paperclip, Play, Search, Send, Sparkles, X } from "lucide-react";
import "./support.css";

const labels = { open: "Ouvert", waiting_admin: "Attente admin", waiting_customer: "Attente client", closed: "Fermé", resolved: "Résolu" };
const categories = { payment: "Paiement", order: "Commande", delivery: "Livraison", other: "Général", catalog_request: "Catalogue" };
const ticketStatus = (ticket) => ticket.archived_at ? "Archivé" : labels[ticket.status] || ticket.status;
const customer = (ticket) => ticket.full_name || [ticket.first_name, ticket.last_name].filter(Boolean).join(" ") || (ticket.username ? `@${ticket.username}` : `Client ${ticket.user_id}`);
const customerReference = (ticket) => ticket.username ? `@${ticket.username}` : `ID ${ticket.user_id}`;
const stamp = (value) => {
  const parsed = new Date(typeof value === "number" ? value * 1000 : value);
  return value && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
};

const emojiToken = /\[\[TGEMOJI:([^:\]]+):([0-9a-fA-F]*)\]\]/g;
const decodeEmoji = (hex) => {
  try {
    const bytes = new Uint8Array((hex.match(/.{1,2}/g) || []).map((value) => Number.parseInt(value, 16)));
    return new TextDecoder().decode(bytes) || "⭐";
  } catch { return "⭐"; }
};
const plainRichText = (value) => String(value || "").replace(emojiToken, (_, __, hex) => decodeEmoji(hex));

function TelegramEmoji({ id, fallback }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="telegram-emoji-fallback">{fallback}</span>;
  return <img className="telegram-emoji" src={`/admin/api/telegram-custom-emoji?id=${encodeURIComponent(id)}`} alt={fallback} loading="lazy" onError={() => setFailed(true)} />;
}

function RichText({ children }) {
  const value = String(children || "");
  const nodes = [];
  let cursor = 0;
  for (const match of value.matchAll(emojiToken)) {
    if (match.index > cursor) nodes.push(value.slice(cursor, match.index));
    const fallback = decodeEmoji(match[2]);
    nodes.push(<TelegramEmoji key={`${match[1]}-${match.index}`} id={match[1]} fallback={fallback} />);
    cursor = match.index + match[0].length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function MessageMedia({ media }) {
  if (!media?.file_id) return null;
  const src = `/admin/api/telegram-media?file_id=${encodeURIComponent(media.file_id)}`;
  const kind = media.type === "image" || String(media.mime_type || "").startsWith("image/") ? "image"
    : media.type === "video" || String(media.mime_type || "").startsWith("video/") ? "video" : media.type;
  if (kind === "image" || kind === "sticker") return <a className={`support-media is-${kind}`} href={src} target="_blank" rel="noreferrer" aria-label="Ouvrir l’image en plein écran"><img src={src} alt={media.file_name || "Image envoyée"} loading="lazy" /></a>;
  if (kind === "video") return <div className="support-media is-video"><video src={src} controls playsInline preload="metadata">Votre navigateur ne peut pas lire cette vidéo.</video><span><Play size={13} /> Vidéo</span></div>;
  return <a className="support-media-file" href={src} target="_blank" rel="noreferrer"><Paperclip size={16} />{media.file_name || "Pièce jointe Telegram"}</a>;
}

function uploadTicketMedia({ ticketId, message, file, token, onProgress }) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const body = new FormData();
    body.append("ticket_id", String(ticketId));
    body.append("message", message);
    body.append("file", file, file.name);
    request.open("POST", "/admin/api/ticket-media");
    request.withCredentials = true;
    request.setRequestHeader("X-Dashboard-Write-Token", token || "");
    request.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100)); };
    request.onerror = () => reject(new Error("Connexion interrompue pendant l’envoi."));
    request.onload = () => {
      let payload = {};
      try { payload = JSON.parse(request.responseText || "{}"); } catch { /* handled below */ }
      if (request.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
      if (request.status < 200 || request.status >= 300 || payload.ok === false) reject(new Error(payload.error || payload.message || "Impossible d’envoyer cette pièce jointe."));
      else resolve(payload);
    };
    request.send(body);
  });
}

function Conversation({ ticket, onAction, onArchive, onBack, onNavigate, draft, setDraft, onStatus, writeToken }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [attachment, setAttachment] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [composerError, setComposerError] = useState("");
  const thread = useRef(null);
  const fileInput = useRef(null);
  const nearBottom = useRef(true);
  const closed = ["closed", "resolved"].includes(ticket.status);
  const archived = Boolean(ticket.archived_at);

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
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener("admin:data-synced", refresh);
    return () => { active = false; controller?.abort(); window.clearInterval(timer); window.removeEventListener("admin:data-synced", refresh); };
  }, [ticket.id, version]);

  useEffect(() => {
    if (nearBottom.current && thread.current) thread.current.scrollTop = thread.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!attachment) { setPreviewUrl(""); return undefined; }
    const url = URL.createObjectURL(attachment);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [attachment]);

  const send = async (event) => {
    event.preventDefault();
    if (busy || closed || (!draft.trim() && !attachment)) return;
    const message = draft.trim();
    const optimisticId = attachment ? "" : `pending-${ticket.id}-${Date.now()}`;
    if (optimisticId) {
      setMessages((current) => [...current, {
        id: optimisticId,
        sender_type: "admin",
        content: message,
        created_at: new Date().toISOString(),
      }]);
      setDraft("");
      nearBottom.current = true;
    }
    setBusy(true);
    setComposerError("");
    try {
      const completed = attachment
        ? await uploadTicketMedia({ ticketId: ticket.id, message, file: attachment, token: writeToken, onProgress: setUploadProgress })
        : await onAction({ action: "reply_ticket", ticket_id: ticket.id, message });
      if (!completed) throw new Error("Le message n’a pas pu être envoyé.");
      if (completed) {
        if (optimisticId && completed.message_record) {
          setMessages((current) => current.map((item) => item.id === optimisticId ? completed.message_record : item));
        } else {
          setVersion((n) => n + 1);
        }
        setDraft(""); setAttachment(null); setUploadProgress(0); nearBottom.current = true; onStatus("waiting_customer");
      }
    } catch (sendError) {
      if (optimisticId) {
        setMessages((current) => current.filter((item) => item.id !== optimisticId));
        setDraft(message);
      }
      setComposerError(sendError.message);
    }
    finally { setBusy(false); }
  };

  const chooseAttachment = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const image = file.type.startsWith("image/");
    const video = file.type.startsWith("video/");
    const limit = image ? 10_000_000 : 50_000_000;
    if ((!image && !video) || file.size > limit) {
      setComposerError(!image && !video ? "Choisissez une image ou une vidéo." : `Ce fichier dépasse la limite de ${image ? "10" : "50"} Mo.`);
      return;
    }
    setComposerError(""); setAttachment(file); setUploadProgress(0);
  };

  return <section className="support-conversation" aria-label={`Conversation avec ${customer(ticket)}`}>
    <header className="support-chat-header">
      <button className="support-back" onClick={onBack} aria-label="Retour aux conversations"><ArrowLeft size={20} /></button>
      <span className="support-avatar"><Headphones size={21} /></span>
      <button type="button" className="support-chat-identity support-customer-link" onClick={() => onNavigate("customers", ticket.user_id)} title="Ouvrir le profil client"><strong>{customer(ticket)} <ExternalLink size={13} /></strong><small>{customerReference(ticket)} · Ticket #{ticket.id} · {categories[ticket.category] || ticket.category || "Général"}</small></button>
      <span className={`status ${archived ? "archived" : ticket.status}`}>{ticketStatus(ticket)}</span>
      <button className="support-close" aria-label={archived ? "Restaurer le ticket" : closed ? "Archiver le ticket" : "Fermer le ticket"} disabled={busy} onClick={async () => {
        setBusy(true);
        try {
          if (archived) {
            if (await onAction({ action: "ticket_unarchive", ticket_id: ticket.id })) onArchive(false);
          } else if (closed) {
            if (await onAction({ action: "ticket_archive", ticket_id: ticket.id })) onArchive(true);
          } else if (await onAction({ action: "close_ticket", ticket_id: ticket.id })) onStatus("closed");
        }
        finally { setBusy(false); }
      }}>{archived ? <ArchiveRestore size={16} /> : closed ? <Archive size={16} /> : <CheckCheck size={16} />}<span>{archived ? "Restaurer" : closed ? "Archiver" : "Fermer le ticket"}</span></button>
    </header>
    <div className="support-messages" ref={thread} role="log" aria-label="Messages de la conversation" onScroll={() => {
      const el = thread.current; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }}>
      <div className="support-thread-intro"><span className="support-avatar"><UserInitial ticket={ticket} /></span><strong>{customer(ticket)}</strong><p>Début de la conversation · Ticket #{ticket.id}</p></div>
      {loading && <p className="support-notice" role="status">Chargement des messages…</p>}
      {error && <div className="support-notice" role="alert">{error} <button onClick={() => setVersion((n) => n + 1)}>Réessayer</button></div>}
      {!loading && !error && !messages.length && <p className="support-notice">Aucun message dans cette conversation.</p>}
      {messages.map((message, index) => <article key={message.id || index} className={`support-bubble ${message.sender_type === "admin" ? "is-admin" : "is-customer"} ${message.media ? "has-media" : ""}`}>
        <small>{message.sender_type === "admin" ? "Vous" : customer(ticket)}</small>
        <MessageMedia media={message.media} />
        {(message.message || message.content) && <p><RichText>{message.message || message.content}</RichText></p>}
        <time>{stamp(message.created_at)}</time>
      </article>)}
    </div>
    <form className="support-composer" onSubmit={send}>
      {attachment && <div className="support-attachment-preview">
        <div>{attachment.type.startsWith("image/") ? <img src={previewUrl} alt="Aperçu de la pièce jointe" /> : <video src={previewUrl} muted />}</div>
        <span>{attachment.type.startsWith("image/") ? <ImageIcon size={15} /> : <Play size={15} />}<strong>{attachment.name}</strong><small>{(attachment.size / 1_000_000).toFixed(1)} Mo</small></span>
        <button type="button" onClick={() => setAttachment(null)} aria-label="Retirer la pièce jointe" disabled={busy}><X size={17} /></button>
      </div>}
      {composerError && <p className="support-composer-error" role="alert">{composerError}</p>}
      <div className="support-composer-row"><input ref={fileInput} className="support-file-input" type="file" accept="image/*,video/*" onChange={chooseAttachment} />
      <button className="support-attach" type="button" disabled={busy || closed} onClick={() => fileInput.current?.click()} aria-label="Ajouter une image ou une vidéo"><Paperclip size={20} /></button>
      <textarea aria-label="Votre réponse" placeholder={closed ? "Cette conversation est fermée" : attachment ? "Ajouter une légende…" : "Écrivez votre réponse…"} value={draft} disabled={busy || closed} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(event); }
      }} maxLength={attachment ? 850 : 2000} rows={2} /><button className="support-send" type="submit" disabled={busy || closed || (!draft.trim() && !attachment)} aria-label="Envoyer la réponse"><Send size={20} /></button></div>
      {busy && attachment && <div className="support-upload-progress" role="progressbar" aria-valuenow={uploadProgress} aria-valuemin="0" aria-valuemax="100"><span style={{ width: `${uploadProgress}%` }} /></div>}
      <small>{busy ? attachment ? `Envoi du média… ${uploadProgress}%` : "Enregistrement en cours…" : <><Sparkles size={11} /> Emoji Premium Telegram · images jusqu’à 10 Mo · vidéos jusqu’à 50 Mo</>}</small>
    </form>
  </section>;
}

function UserInitial({ ticket }) { return String(ticket.full_name || ticket.username || ticket.user_id || "C").slice(0, 2).toUpperCase(); }

export default function SupportInbox({ result, loading, search, setSearch, status, setStatus, searchField, setSearchField, targetTicketId, pagination, onAction, onNavigate, writeToken, variant = "support", showBulkActions = true }) {
  const [selected, setSelected] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [bulkBusy, setBulkBusy] = useState(false);
  const isProductRequests = variant === "product-requests";
  useEffect(() => {
    setSelected((previous) => result.items.find((item) => item.id === previous?.id) || previous);
  }, [result.items]);
  useEffect(() => {
    if (!targetTicketId) return;
    const match = result.items.find((item) => String(item.id) === String(targetTicketId));
    if (match) setSelected(match);
  }, [result.items, targetTicketId]);
  const current = selected;
  const runBulkAction = async (action) => {
    if (bulkBusy) return;
    setBulkBusy(true);
    try {
      if (await onAction({ action })) {
        setSelected(null);
        window.dispatchEvent(new CustomEvent("admin:data-synced"));
      }
    } finally { setBulkBusy(false); }
  };
  return <div className="support-page">
    <div className={`support-inbox ${current ? "has-conversation" : ""}`}>
      <aside className="support-sidebar" aria-label="Conversations">
        <header><h3>{isProductRequests ? "Demandes produits" : "Conversations"}</h3><span>{result.total}</span></header>
        {showBulkActions && status !== "archived" && <div className="support-bulk-actions"><button disabled={bulkBusy} onClick={() => runBulkAction("close_all_tickets")}><CheckCheck size={14} />Fermer ouverts</button><button disabled={bulkBusy} onClick={() => runBulkAction("tickets_archive_closed")}><Archive size={14} />Archiver fermés</button></div>}
        <div className="support-filters">
          <label className="support-search"><Search size={17} /><input type="search" aria-label={isProductRequests ? "Rechercher une demande produit" : "Rechercher une conversation"} placeholder={isProductRequests ? "Rechercher une demande…" : "Rechercher une conversation…"} value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <div><select aria-label="Champ de recherche" value={searchField} onChange={(event) => setSearchField(event.target.value)}>{[["all", "Tout rechercher"], ["ticket_id", "ID ticket"], ["user_id", "ID client"], ["category", "Catégorie"], ["message", "Message"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          <select aria-label="Filtrer les conversations par statut" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Tous les statuts</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}<option value="archived">Archivés</option></select></div>
        </div>
        <div className="support-list" aria-busy={loading}>
          {loading && !result.items.length && <p className="support-notice" role="status">Actualisation…</p>}
          {!loading && !result.items.length && <div className="support-list-empty"><Search size={26} /><strong>{isProductRequests ? "Aucune demande produit" : "Aucune conversation"}</strong><p>{isProductRequests ? "Les demandes envoyées depuis le catalogue du bot apparaîtront ici." : "Essayez une autre recherche ou un autre statut."}</p></div>}
          {result.items.map((ticket) => <button key={ticket.id} className={`support-contact ${current?.id === ticket.id ? "is-selected" : ""}`} aria-pressed={current?.id === ticket.id} onClick={() => setSelected(ticket)}>
            <span className="support-avatar"><UserInitial ticket={ticket} /></span>
            <span className="support-contact-copy"><span><strong>{customer(ticket)}</strong>{ticket.status === "waiting_admin" && <i aria-label="Réponse attendue" />}</span><small>{plainRichText(ticket.last_message || ticket.message || categories[ticket.category] || ticket.category || "Conversation support")}</small><span className="support-contact-meta"><span>#{ticket.id} · {ticketStatus(ticket)}</span><time>{stamp(ticket.updated_at || ticket.created_at)}</time></span></span>
          </button>)}
        </div>
        {pagination}
      </aside>
      {current ? <Conversation key={current.id} ticket={current} onAction={onAction} onArchive={() => { setSelected(null); window.dispatchEvent(new CustomEvent("admin:data-synced")); }} onBack={() => setSelected(null)} onNavigate={onNavigate} draft={drafts[current.id] || ""} setDraft={(value) => setDrafts((prev) => ({ ...prev, [current.id]: value }))} onStatus={(value) => setSelected({ ...current, status: value })} writeToken={writeToken} /> : <section className="support-welcome"><span>{isProductRequests ? <Sparkles size={35} /> : <MessageSquareText size={35} />}</span><h3>{isProductRequests ? "Transformez les demandes en nouvelles offres." : "Vos conversations, au même endroit."}</h3><p>{isProductRequests ? "Sélectionnez une demande pour comprendre le besoin et répondre directement au client dans Telegram." : "Sélectionnez un client pour consulter ses messages et lui répondre directement."}</p><small>{isProductRequests ? <><Sparkles size={14} /> Veille catalogue</> : <><Headphones size={14} /> Support BlackMarket</>}</small></section>}
    </div>
  </div>;
}
