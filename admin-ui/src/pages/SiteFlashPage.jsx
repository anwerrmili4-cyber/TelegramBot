import { useMemo, useState } from "react";
import { Clock, Send, Square, Zap } from "lucide-react";
import { ActionButton, Empty, Field, PageHeader, useRemoteList } from "../admin-kit.jsx";
import { dinars } from "../site-format.jsx";

const PRESETS = [
  [60, "1 heure"],
  [180, "3 heures"],
  [360, "6 heures"],
  [720, "12 heures"],
  [1440, "24 heures"],
  [2880, "48 heures"],
  [10080, "7 jours"],
];

function when(value) {
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function millimesOf(value) {
  const amount = Number(String(value || "").replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(amount) || amount <= 0) return 0;
  return Math.round(amount * 1000);
}

function durationLabel(minutes) {
  if (!minutes) return "";
  if (minutes % 1440 === 0) {
    const days = minutes / 1440;
    return days === 1 ? "1 jour" : `${days} jours`;
  }
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return hours === 1 ? "1 heure" : `${hours} heures`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours <= 0) return `${rest} minutes`;
  return `${hours} h ${String(rest).padStart(2, "0")}`;
}

export default function SiteFlashPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-flash", {}, { refreshInterval: 15000 });
  const [offerId, setOfferId] = useState("");
  const [flashPrice, setFlashPrice] = useState("");
  const [preset, setPreset] = useState("1440");
  const [hours, setHours] = useState("2");
  const [minutes, setMinutes] = useState("0");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [label, setLabel] = useState("Vente flash");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const products = result.products || [];
  const active = result.active || [];
  const selected = products.find((product) => String(product.id) === offerId) || null;
  const regular = selected?.regular_millimes || 0;
  const sale = millimesOf(flashPrice);
  const percent = regular > 0 && sale > 0 && sale < regular ? Math.max(1, Math.round(((regular - sale) * 100) / regular)) : 0;
  const durationMinutes = useMemo(() => {
    if (preset !== "custom") return Number(preset) || 0;
    const total = (Number(hours) || 0) * 60 + (Number(minutes) || 0);
    return total;
  }, [preset, hours, minutes]);
  const endsAt = durationMinutes >= 15 && durationMinutes <= 10080
    ? new Date(Date.now() + durationMinutes * 60000)
    : null;

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setDone("");
    if (!selected) {
      setError("Choisis un produit du site.");
      return;
    }
    if (selected.flash_active) {
      setError("Une vente flash est déjà en cours sur ce produit.");
      return;
    }
    if (durationMinutes < 15 || durationMinutes > 10080) {
      setError("La durée doit être comprise entre 15 minutes et 7 jours.");
      return;
    }
    setBusy(true);
    try {
      const answer = await onAction({
        action: "site_flash_start",
        offer_id: selected.id,
        flash_price: flashPrice,
        duration_minutes: durationMinutes,
        title,
        body,
        label,
      });
      if (answer?.message) {
        setDone(answer.message);
        setFlashPrice("");
        setTitle("");
        setBody("");
        setOfferId("");
        window.dispatchEvent(new CustomEvent("admin:data-synced"));
      }
    } catch (reason) {
      setError(reason?.message || "La vente flash n'a pas pu démarrer.");
    } finally {
      setBusy(false);
    }
  }

  async function stop(product) {
    setError("");
    setDone("");
    const answer = await onAction({ action: "site_flash_stop", offer_id: product.id });
    if (answer?.message) {
      setDone(answer.message);
      window.dispatchEvent(new CustomEvent("admin:data-synced"));
    }
  }

  return (
    <div className="operations-page">
      <PageHeader
        title="Vente flash"
        description="Le prix en dinars baisse le temps choisi, puis revient. L'annonce part aux clients vérifiés, dans le même email que les autres notifications."
      />
      <section className="mail-compose" aria-labelledby="flash-form-title">
        <h2 id="flash-form-title">Lancer une vente</h2>
        <form className="operation-form" onSubmit={(event) => void submit(event)}>
          <div className="form-grid">
            <Field label="Produit" wide>
              <select value={offerId} onChange={(event) => setOfferId(event.target.value)} required aria-label="Produit">
                <option value="">Choisir un produit du site…</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.service_name} — {product.name} — {dinars(product.regular_millimes)}
                    {product.flash_active ? " · en cours" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Prix actuel">
              <input value={selected ? dinars(regular) : ""} readOnly aria-label="Prix actuel" placeholder="Choisis un produit" />
            </Field>
            <Field label="Prix flash">
              <input
                value={flashPrice}
                onChange={(event) => setFlashPrice(event.target.value)}
                required
                inputMode="decimal"
                placeholder="19,500"
                aria-label="Prix flash"
              />
            </Field>
            <Field label="Durée">
              <select value={preset} onChange={(event) => setPreset(event.target.value)} aria-label="Durée">
                {PRESETS.map(([value, name]) => (
                  <option key={value} value={value}>{name}</option>
                ))}
                <option value="custom">Durée personnalisée</option>
              </select>
            </Field>
            {preset === "custom" ? (
              <Field label="Heures et minutes">
                <span className="flash-custom-duration">
                  <input
                    value={hours}
                    onChange={(event) => setHours(event.target.value)}
                    inputMode="numeric"
                    min="0"
                    max="168"
                    aria-label="Heures"
                  />
                  <input
                    value={minutes}
                    onChange={(event) => setMinutes(event.target.value)}
                    inputMode="numeric"
                    min="0"
                    max="59"
                    aria-label="Minutes"
                  />
                </span>
              </Field>
            ) : <span />}
          </div>
          {selected ? (
            <div className="flash-preview" aria-live="polite">
              <div>
                <span>Prix actuel</span>
                <strong>{dinars(regular)}</strong>
              </div>
              <div>
                <span>Prix flash</span>
                <strong>{sale > 0 ? dinars(sale) : "—"}</strong>
              </div>
              <div>
                <span>Remise</span>
                <strong>{percent ? `-${percent} %` : "—"}</strong>
              </div>
              <div>
                <span>Fin</span>
                <strong>{endsAt ? when(Math.floor(endsAt.getTime() / 1000)) : "—"}</strong>
              </div>
            </div>
          ) : null}
          <p>Le prix USDT du bot reste en place. Seul le prix du site change.</p>
          <details className="flash-options">
            <summary>Autres options</summary>
            <div className="form-grid">
              <Field label="Libellé sur le produit">
                <input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={24} aria-label="Libellé sur le produit" />
              </Field>
              <span />
              <Field label="Titre de l'annonce" wide>
                <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder="Laissé vide, le titre est généré" aria-label="Titre de l'annonce" />
              </Field>
              <Field label="Message" wide>
                <textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={2000} rows={4} placeholder="Laissé vide, le message indique l'ancien prix, le nouveau et la durée." aria-label="Message" />
              </Field>
            </div>
          </details>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {done ? <p className="form-success" role="status">{done}</p> : null}
          <div className="dialog-actions">
            <ActionButton icon={Send} type="submit" disabled={busy || !products.length}>
              {busy ? "Lancement…" : "Lancer la vente flash"}
            </ActionButton>
          </div>
        </form>
      </section>
      <section className="operations-panel" aria-labelledby="flash-active-title">
        <header className="notify-head">
          <h2 id="flash-active-title">En cours</h2>
          <span>{loading ? "Chargement…" : `${active.length} vente${active.length > 1 ? "s" : ""}`}</span>
        </header>
        {!loading && !products.length ? (
          <Empty icon={Zap} title="Aucun produit en vente sur le site." text="Fixe un prix en dinars dans Mon catalogue, puis reviens ici." />
        ) : null}
        {!loading && products.length && !active.length ? (
          <Empty icon={Clock} title="Aucune vente flash en cours." text="Choisis un produit, un prix plus bas et une durée." />
        ) : null}
        {active.length ? (
          <div className="operation-list">
            {active.map((product) => {
              const off = product.regular_millimes > product.price_millimes
                ? Math.max(1, Math.round(((product.regular_millimes - product.price_millimes) * 100) / product.regular_millimes))
                : 0;
              return (
                <article key={product.id} className="operation-card">
                  <header>
                    <span className="operation-icon"><Zap size={18} /></span>
                    <div>
                      <small>{product.service_name} · jusqu'au {when(product.flash_ends_at)}</small>
                      <strong>{product.name}</strong>
                    </div>
                  </header>
                  <div className="flash-preview">
                    <div>
                      <span>Prix actuel</span>
                      <strong><s>{dinars(product.regular_millimes)}</s></strong>
                    </div>
                    <div>
                      <span>Prix flash</span>
                      <strong>{dinars(product.price_millimes)}</strong>
                    </div>
                    <div>
                      <span>Remise</span>
                      <strong>{off ? `-${off} %` : "—"}</strong>
                    </div>
                    <div>
                      <span>Libellé</span>
                      <strong>{product.flash_label || "Vente flash"}</strong>
                    </div>
                  </div>
                  <footer>
                    <ActionButton danger icon={Square} onClick={() => void stop(product)}>Arrêter</ActionButton>
                  </footer>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </div>
  );
}
