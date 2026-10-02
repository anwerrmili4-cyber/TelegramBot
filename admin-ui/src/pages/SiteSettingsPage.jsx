import { useEffect, useState } from "react";
import {
  RefreshCw,
  Save,
} from "lucide-react";
import { PageHeader, ActionButton, Field, useRemoteList } from "../admin-kit.jsx";
import { dinars } from "../site-format.jsx";

export default function SiteSettingsPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-settings", {});
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (form || !result.available_payment_methods) return;
    setForm({
      tnd_per_usdt: String(result.tnd_per_usdt).replace(".", ","),
      methods: new Set(result.payment_methods || []),
      details: { ...(result.payment_details || {}) },
    });
  }, [form, result]);
  const methods = result.available_payment_methods || [];
  const toggleMethod = (id) => setForm((current) => {
    const next = new Set(current.methods);
    if (next.has(id)) next.delete(id); else next.add(id);
    return { ...current, methods: next };
  });
  const setDetails = (id, value) => setForm((current) => ({ ...current, details: { ...current.details, [id]: value } }));
  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    const payload = { action: "site_settings_save", tnd_per_usdt: form.tnd_per_usdt };
    methods.forEach(({ id }) => {
      payload[`payment_${id}`] = form.methods.has(id) ? "1" : "0";
      payload[`details_${id}`] = form.details[id] || "";
    });
    setSaving(true);
    try {
      await onAction(payload);
    } finally {
      setSaving(false);
    }
  };
  return <div className="operations-page site-page">
    <PageHeader title="Paramètres du site" description="Appliqués sur ourblackmarket.com en moins d’une minute, sans redéploiement." />
    <section className="site-panel">
      {loading && !form ? <div className="operation-loading"><RefreshCw className="spin" />Chargement…</div> : form && <form className="operation-form" onSubmit={submit}>
        <div className="form-grid">
          <Field label="Taux TND pour 1 USDT">
            <input value={form.tnd_per_usdt} onChange={(event) => setForm({ ...form, tnd_per_usdt: event.target.value })} inputMode="decimal" required />
            <small className="site-field-help">Sert uniquement à suggérer un prix en dinars dans le catalogue.</small>
          </Field>
        </div>
        <h3 className="site-section-title">Moyens de paiement</h3>
        <p className="site-field-help">Les coordonnées sont affichées au client au moment de payer une commande ou de recharger son portefeuille. Il joint ensuite la référence et la capture du reçu.</p>
        <div className="site-method-grid">{methods.map(({ id, label }) => <div key={id} className={`site-method-card${form.methods.has(id) ? " active" : ""}`}>
          <label className="switch"><input type="checkbox" checked={form.methods.has(id)} onChange={() => toggleMethod(id)} /><span />{label}</label>
          <textarea value={form.details[id] || ""} onChange={(event) => setDetails(id, event.target.value)} maxLength={300} rows={3} required={form.methods.has(id)} placeholder={`Où envoyer l’argent par ${label} (numéro, nom du bénéficiaire…)`} aria-label={`Coordonnées ${label}`} />
        </div>)}</div>
        <div className="dialog-actions"><ActionButton type="submit" icon={Save} disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer"}</ActionButton></div>
      </form>}
    </section>
  </div>;
}
