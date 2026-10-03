import { useEffect, useMemo, useRef, useState } from "react";
import { Mail, Palette, PenLine, Search, Send } from "lucide-react";
import { ActionButton, Empty, Field, PageHeader, useRemoteList } from "../admin-kit.jsx";

const STATUS = {
  queued: "En file",
  sent: "Envoyé",
  delivered: "Livré",
  bounced: "Rejeté",
  complained: "Signalé",
};

function stamp(value) {
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? null : date;
}

function when(value) {
  const date = stamp(value);
  if (!date) return "";
  const sameDay = date.toDateString() === new Date().toDateString();
  return new Intl.DateTimeFormat("fr-FR", sameDay ? { timeStyle: "short" } : { day: "numeric", month: "short" }).format(date);
}

function fullWhen(value) {
  const date = stamp(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "full", timeStyle: "short" }).format(date);
}

function initial(item) {
  const source = String(item.name || item.to || "?").trim();
  return source.charAt(0).toUpperCase() || "?";
}

function MailFrame({ html }) {
  const frame = useRef(null);

  function fit() {
    const doc = frame.current?.contentDocument;
    const height = doc?.documentElement?.scrollHeight;
    if (frame.current && height) frame.current.style.height = `${height}px`;
  }

  return (
    <iframe
      ref={frame}
      className="mail-frame"
      title="Contenu de l'email"
      sandbox="allow-same-origin"
      srcDoc={html}
      onLoad={fit}
    />
  );
}

export default function SiteMailPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-mail", {}, { refreshInterval: 20000 });
  const [folder, setFolder] = useState("sent");
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState("one");
  const [customerId, setCustomerId] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");
  const [listError, setListError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reading, setReading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [styles, setStyles] = useState([]);
  const [stylesLoaded, setStylesLoaded] = useState(false);
  const [stylesLoading, setStylesLoading] = useState(false);
  const [stylesError, setStylesError] = useState("");
  const [styleId, setStyleId] = useState("");
  const customers = result.customers || [];
  const messages = result.messages || [];

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return messages;
    return messages.filter((item) =>
      [item.subject, item.to, item.name, item.kind_label, item.preview].join(" ").toLowerCase().includes(needle)
    );
  }, [messages, query]);

  const styleGroups = useMemo(() => {
    const order = ["Compte", "Commandes", "Portefeuille", "Suivi"];
    return order
      .map((name) => ({ name, items: styles.filter((item) => item.group === name) }))
      .filter((group) => group.items.length);
  }, [styles]);
  const selectedStyle = styles.find((item) => item.id === styleId) || null;

  useEffect(() => {
    const onError = (event) => setListError(String(event.detail || "La liste n'a pas pu être actualisée."));
    window.addEventListener("admin:read-error", onError);
    return () => window.removeEventListener("admin:read-error", onError);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    const controller = new AbortController();
    setReading(true);
    setDetailError("");
    fetch(`/admin/api/site-mail?id=${encodeURIComponent(selectedId)}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
          setDetail(null);
          setDetailError(payload.error || "Message introuvable.");
          return;
        }
        setDetail(payload);
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        setDetail(null);
        setDetailError("Impossible de charger ce message.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setReading(false);
      });
    return () => controller.abort();
  }, [selectedId]);

  useEffect(() => {
    if (folder !== "styles" || stylesLoaded) return undefined;
    const controller = new AbortController();
    setStylesLoading(true);
    setStylesError("");
    fetch("/admin/api/site-mail?styles=1", { credentials: "same-origin", cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok || payload.ok === false) {
          setStylesError(payload.error || "Les modèles n'ont pas pu être chargés.");
          return;
        }
        setStyles(payload.styles || []);
        setStylesLoaded(true);
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        setStylesError("Impossible de charger les modèles.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setStylesLoading(false);
      });
    return () => controller.abort();
  }, [folder, stylesLoaded]);

  function openMessage(id) {
    setFolder("sent");
    setSelectedId(id);
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
        setFolder("sent");
        window.dispatchEvent(new CustomEvent("admin:data-synced"));
      }
    } catch (reason) {
      setFormError(reason?.message || "Le message n'a pas pu être envoyé.");
    } finally {
      setBusy(false);
    }
  }

  const recipient = detail?.name ? `${detail.name} <${detail.to}>` : detail?.to;
  const paneOpen = (folder === "sent" && selectedId) || (folder === "styles" && styleId);
  const layout = ["mail-app", paneOpen ? "is-reading" : "", folder === "compose" ? "is-composing" : ""].filter(Boolean).join(" ");

  return (
    <div className="operations-page mail-page">
      <PageHeader
        title="Courrier"
        description="Les emails déjà partis aux clients, ouverts comme dans une boîte mail."
      />
      {listError ? <p className="form-error" role="alert">{listError}</p> : null}

      <div className={layout}>
        <nav className="mail-folders" aria-label="Dossiers">
          <button type="button" className={folder === "sent" ? "is-active" : ""} onClick={() => setFolder("sent")}>
            <Mail size={16} />
            <span>Envoyés</span>
            <small>{messages.length}</small>
          </button>
          <button type="button" className={folder === "compose" ? "is-active" : ""} onClick={() => setFolder("compose")}>
            <PenLine size={16} />
            <span>Nouveau</span>
          </button>
          <button type="button" className={folder === "styles" ? "is-active" : ""} onClick={() => setFolder("styles")}>
            <Palette size={16} />
            <span>Modèles</span>
          </button>
        </nav>

        <section className="mail-list-pane" aria-labelledby="sent-mail-title">
          <header className="mail-list-head">
            <h2 id="sent-mail-title">{folder === "styles" ? "Modèles" : "Envoyés"}</h2>
            {folder === "styles" ? null : (
            <label className="mail-search">
              <Search size={14} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Rechercher"
                aria-label="Rechercher un message"
              />
            </label>
            )}
          </header>
          {folder === "styles" ? (
            <>
              <p className="mail-legend" aria-label="Couleurs des modèles">
                <span className="mail-kind mail-tone-success">Validé</span>
                <span className="mail-kind mail-tone-pending">En attente</span>
                <span className="mail-kind mail-tone-danger">Refus</span>
                <span className="mail-kind mail-tone-brand">Information</span>
              </p>
              {stylesError ? <p className="form-error" role="alert">{stylesError}</p> : null}
              {stylesLoading && !styles.length ? <p className="mail-empty-list">Chargement des modèles…</p> : null}
              {styleGroups.map((group) => (
                <div key={group.name}>
                  <h3 className="mail-style-group">{group.name}</h3>
                  <div className="mail-rows" role="listbox" aria-label={group.name}>
                    {group.items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        role="option"
                        aria-selected={styleId === item.id}
                        className={styleId === item.id ? `mail-row is-selected mail-tone-${item.tone}` : `mail-row mail-tone-${item.tone}`}
                        onClick={() => setStyleId(item.id)}
                      >
                        <span className={`mail-avatar mail-tone-${item.tone}`} aria-hidden="true">{item.label.charAt(0)}</span>
                        <span className="mail-row-copy">
                          <span className="mail-row-top">
                            <strong>{item.label}</strong>
                          </span>
                          <span className="mail-row-subject">{item.subject}</span>
                          <span className="mail-row-preview">{item.when}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </>
          ) : null}
          {folder !== "styles" && loading && !messages.length ? <p className="mail-empty-list">Chargement…</p> : null}
          {folder !== "styles" && !loading && !visible.length ? (
            <Empty
              icon={Mail}
              title={query ? "Aucun message ne correspond." : "Aucun message envoyé pour le moment."}
              text={query ? "Essaie un autre nom, une adresse ou un sujet." : "Les emails déjà partis aux clients s'affichent ici."}
            />
          ) : null}
          {folder !== "styles" ? (
          <div className="mail-rows" role="listbox" aria-label="Messages envoyés">
            {visible.map((item) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={selectedId === item.id}
                className={selectedId === item.id && folder === "sent" ? `mail-row is-selected mail-tone-${item.tone || "brand"}` : `mail-row mail-tone-${item.tone || "brand"}`}
                onClick={() => openMessage(item.id)}
              >
                <span className={`mail-avatar mail-tone-${item.tone || "brand"}`} aria-hidden="true">{initial(item)}</span>
                <span className="mail-row-copy">
                  <span className="mail-row-top">
                    <strong>{item.name || item.to}</strong>
                    <time dateTime={stamp(item.created_at)?.toISOString()}>{when(item.created_at)}</time>
                  </span>
                  <span className="mail-row-subject">{item.subject || "Sans sujet"}</span>
                  <span className={`mail-kind mail-tone-${item.tone || "brand"}`}>{item.kind_label}</span>
                  {item.preview ? <span className="mail-row-preview">{item.preview}</span> : null}
                </span>
              </button>
            ))}
          </div>
          ) : null}
        </section>

        <section className="mail-read-pane" aria-live="polite">
          {folder === "compose" ? (
            <form className="mail-compose" onSubmit={(event) => void submit(event)}>
              <header className="mail-compose-head">
                <h2>Nouveau message</h2>
                <p>De : <strong>{result.from || "BLACKMARKET"}</strong></p>
              </header>
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
                <textarea value={message} onChange={(event) => setMessage(event.target.value)} required minLength={8} maxLength={4000} rows={12} />
              </Field>
              {formError ? <p className="form-error" role="alert">{formError}</p> : null}
              {done ? <p className="form-success" role="status">{done}</p> : null}
              {!loading && !customers.length ? <p className="mail-empty-list">Aucun client pour le moment.</p> : null}
              <div className="dialog-actions">
                <ActionButton icon={Send} type="submit" disabled={busy || !customers.length}>
                  {busy ? "Envoi…" : "Envoyer"}
                </ActionButton>
              </div>
            </form>
          ) : null}

          {folder === "styles" && !selectedStyle ? (
            <div className="mail-placeholder">
              <Palette size={28} />
              <p>Choisis un modèle pour voir le style de l'email automatique.</p>
            </div>
          ) : null}

          {folder === "styles" && selectedStyle ? (
            <article className="mail-letter">
              <button type="button" className="mail-back" onClick={() => setStyleId("")}>Retour aux modèles</button>
              <header className="mail-letter-head">
                <h2>{selectedStyle.subject}</h2>
                <span className={`mail-kind mail-tone-${selectedStyle.tone}`}>{selectedStyle.label}</span>
                <dl>
                  <div><dt>Quand</dt><dd>{selectedStyle.when}</dd></div>
                  <div><dt>De</dt><dd>{result.from || "BLACKMARKET"}</dd></div>
                  <div><dt>Aperçu</dt><dd>Exemple seulement. Aucun email n'est envoyé.</dd></div>
                </dl>
              </header>
              <MailFrame key={selectedStyle.id} html={selectedStyle.html} />
            </article>
          ) : null}

          {folder === "sent" && !selectedId ? (
            <div className="mail-placeholder">
              <Mail size={28} />
              <p>Choisis un message pour lire exactement ce que le client a reçu.</p>
            </div>
          ) : null}

          {folder === "sent" && selectedId ? (
            <article className="mail-letter">
              <button type="button" className="mail-back" onClick={() => setSelectedId(null)}>Retour aux messages</button>
              {detailError ? <p className="form-error" role="alert">{detailError}</p> : null}
              {reading && !detail ? <p className="mail-empty-list">Ouverture du message…</p> : null}
              {detail ? (
                <>
                  <header className="mail-letter-head">
                    <h2>{detail.subject || "Sans sujet"}</h2>
                    <span className={`status ${detail.status || ""}`}>{STATUS[detail.status] || detail.status}</span>
                    <dl>
                      <div><dt>De</dt><dd>{result.from || "BLACKMARKET"}</dd></div>
                      <div><dt>À</dt><dd>{recipient}</dd></div>
                      <div><dt>Date</dt><dd>{fullWhen(detail.created_at)}</dd></div>
                      <div><dt>Type</dt><dd>{detail.kind_label || detail.kind}</dd></div>
                    </dl>
                  </header>
                  {detail.html ? <MailFrame html={detail.html} /> : <pre className="mail-plain">{detail.text || "Ce message n'a pas de contenu."}</pre>}
                </>
              ) : null}
            </article>
          ) : null}
        </section>
      </div>
    </div>
  );
}
