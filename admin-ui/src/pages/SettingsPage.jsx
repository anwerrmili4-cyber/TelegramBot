import { useState } from "react";
import {
  Check,
  Cloud,
  MessageSquareText,
  RefreshCw,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { PageHeader, ActionButton, Field } from "../admin-kit.jsx";

export default function SettingsPage({ data, onAction, onHealthCheck }) {
  const [form, setForm] = useState({
    shop_name: data.shop_name || "BlackMarket",
    currency: data.currency || "USDT",
    low_stock_threshold: data.low_stock_threshold || 5,
    order_expiry_seconds: data.order_expiry_seconds || 1800,
    payment_recipient: data.payment_recipient || "",
    affiliate_enabled: data.affiliate_enabled !== false,
    affiliate_target: data.affiliate_target || 10,
    affiliate_reward_cents: data.affiliate_reward_cents || 100,
    maintenance_enabled: data.maintenance_enabled === true,
    maintenance_message: data.maintenance_message || "",
    welcome_message: data.welcome_message || "",
    help_message: data.help_message || "",
    terms_message: data.terms_message || "",
    privacy_message: data.privacy_message || "",
    active_languages: data.active_languages || "en,ar",
    announcement_new_stock: data.announcement_new_stock || "",
    announcement_flash_sale: data.announcement_flash_sale || "",
    announcement_restock: data.announcement_restock || "",
  });
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  return (
    <>
      <PageHeader
        title="Paramètres"
        description="Personnalisez la boutique, le paiement, l’affiliation et les messages."
        actions={
          <>
            <ActionButton
              secondary
              icon={ShieldCheck}
              onClick={() => onHealthCheck("telegram")}
            >
              Telegram
            </ActionButton>
            <ActionButton secondary icon={RefreshCw} onClick={() => onHealthCheck("telegram-repair")}>Réparer le webhook</ActionButton>
            <ActionButton
              secondary
              icon={Cloud}
              onClick={() => onHealthCheck("binance")}
            >
              Binance
            </ActionButton>
          </>
        }
      />
      <form
        className="settings-layout"
        onSubmit={(event) => {
          event.preventDefault();
          onAction({
            action: "save_settings",
            ...form,
            affiliate_enabled: form.affiliate_enabled ? "on" : "",
            maintenance_enabled: form.maintenance_enabled ? "on" : "",
          });
        }}
      >
        <section className="settings-card">
          <header>
            <Settings size={18} />
            <div>
              <h3>Boutique</h3>
              <p>Identité et règles commerciales.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Nom">
              <input
                value={form.shop_name}
                onChange={(event) => set("shop_name", event.target.value)}
              />
            </Field>
            <Field label="Devise">
              <input
                value={form.currency}
                onChange={(event) => set("currency", event.target.value)}
              />
            </Field>
            <Field label="Seuil stock faible">
              <input
                type="number"
                value={form.low_stock_threshold}
                onChange={(event) =>
                  set("low_stock_threshold", event.target.value)
                }
              />
            </Field>
            <Field label="Expiration commande (secondes)">
              <input
                type="number"
                value={form.order_expiry_seconds}
                onChange={(event) =>
                  set("order_expiry_seconds", event.target.value)
                }
              />
            </Field>
            <Field label="Identifiant de paiement" wide>
              <input
                value={form.payment_recipient}
                onChange={(event) =>
                  set("payment_recipient", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <section className="settings-card">
          <header>
            <Users size={18} />
            <div>
              <h3>Affiliation et maintenance</h3>
              <p>Contrôlez les récompenses et la disponibilité.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Affiliation">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={form.affiliate_enabled}
                  onChange={(event) =>
                    set("affiliate_enabled", event.target.checked)
                  }
                />
                <span />
                Activée
              </label>
            </Field>
            <Field label="Objectif">
              <input
                type="number"
                value={form.affiliate_target}
                onChange={(event) =>
                  set("affiliate_target", event.target.value)
                }
              />
            </Field>
            <Field label="Récompense (centimes)">
              <input
                type="number"
                value={form.affiliate_reward_cents}
                onChange={(event) =>
                  set("affiliate_reward_cents", event.target.value)
                }
              />
            </Field>
            <Field label="Maintenance">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={form.maintenance_enabled}
                  onChange={(event) =>
                    set("maintenance_enabled", event.target.checked)
                  }
                />
                <span />
                Activée
              </label>
            </Field>
            <Field label="Message maintenance" wide>
              <textarea
                value={form.maintenance_message}
                onChange={(event) =>
                  set("maintenance_message", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <section className="settings-card full">
          <header>
            <MessageSquareText size={18} />
            <div>
              <h3>Contenu du bot</h3>
              <p>Messages personnalisés affichés aux clients.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Accueil">
              <textarea
                value={form.welcome_message}
                onChange={(event) => set("welcome_message", event.target.value)}
              />
            </Field>
            <Field label="Aide">
              <textarea
                value={form.help_message}
                onChange={(event) => set("help_message", event.target.value)}
              />
            </Field>
            <Field label="Conditions">
              <textarea
                value={form.terms_message}
                onChange={(event) => set("terms_message", event.target.value)}
              />
            </Field>
            <Field label="Confidentialité">
              <textarea
                value={form.privacy_message}
                onChange={(event) => set("privacy_message", event.target.value)}
              />
            </Field>
            <Field label="Langues actives" wide>
              <input
                value={form.active_languages}
                onChange={(event) => {
                  const languages = event.target.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter((value) => ["en", "ar"].includes(value));
                  set("active_languages", [...new Set(languages)].join(",") || "en");
                }}
                placeholder="en,ar"
              />
            </Field>
            <Field label="Annonce Nouveau Stock" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock}, {added}" wide>
              <textarea
                rows={5}
                value={form.announcement_new_stock}
                onChange={(event) =>
                  set("announcement_new_stock", event.target.value)
                }
              />
            </Field>
            <Field label="Annonce Vente Flash" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {old_price}, {price}, {cur}, {discount}, {remaining}" wide>
              <textarea
                rows={5}
                value={form.announcement_flash_sale}
                onChange={(event) =>
                  set("announcement_flash_sale", event.target.value)
                }
              />
            </Field>
            <Field label="Annonce Restock / Produit disponible" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock}" wide>
              <textarea
                rows={5}
                value={form.announcement_restock}
                onChange={(event) =>
                  set("announcement_restock", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <div className="settings-submit">
          <ActionButton icon={Check} type="submit">
            Enregistrer les paramètres
          </ActionButton>
        </div>
      </form>
    </>
  );
}
