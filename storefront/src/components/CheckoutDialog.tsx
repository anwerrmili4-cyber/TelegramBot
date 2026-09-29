import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, BadgeCheck, Copy, ShieldAlert, X } from "lucide-react";
import { Overlay } from "@/components/Overlay";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, submitCheckout } from "@/lib/api";
import { EMAIL_PATTERN } from "@/pages/AuthLayout";
import { displayPhone, isValidPhone, money, normalizePhoneInput, plural } from "@/lib/format";
import { stagger } from "@/lib/motion";
import type { Cart } from "@/hooks/useCart";
import type { CheckoutResult, PaymentMethod } from "@/types";

type CheckoutDialogProps = {
  open: boolean;
  cart: Cart;
  paymentMethods: PaymentMethod[];
  onClose: () => void;
  onConfirmed: () => void;
};

export function CheckoutDialog({
  open,
  cart,
  paymentMethods,
  onClose,
  onConfirmed,
}: CheckoutDialogProps) {
  const { customer } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [method, setMethod] = useState(paymentMethods[0]?.id ?? "d17");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CheckoutResult | null>(null);
  const [copied, setCopied] = useState(false);
  const methodLabel = paymentMethods.find((option) => option.id === method)?.label ?? method;

  // Pre-fill from the account without overwriting anything already typed.
  useEffect(() => {
    if (!open || !customer) return;
    setName((current) => current || customer.name);
    setEmail((current) => current || customer.email);
  }, [open, customer]);

  function close() {
    onClose();
    if (result) {
      // The cart is only discarded once the customer leaves a confirmed order,
      // so a failed submission never loses their selection.
      setResult(null);
      setName("");
      setEmail("");
      setPhone("");
      setNote("");
      setCopied(false);
      onConfirmed();
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Saisis une adresse email valide pour recevoir ta commande.");
      return;
    }
    if (!isValidPhone(phone)) {
      setError("Saisis un numéro tunisien valide à 8 chiffres.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      setResult(
        await submitCheckout({
          name: name.trim(),
          email: email.trim(),
          phone: normalizePhoneInput(phone),
          payment_method: method,
          note: note.trim(),
          items: cart.lines.map((line) => ({
            offer_id: line.offer.id,
            quantity: line.quantity,
          })),
        }),
      );
    } catch (reason) {
      setError(errorMessage(reason, "Impossible de créer la commande."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Overlay open={open} onClose={close} labelledBy="checkout-title" variant="dialog">
      <header className="dialog-head">
        <div>
          <span className="kicker">{result ? "Commande enregistrée" : "Finaliser"}</span>
          <h2 id="checkout-title">
            {result ? `Référence ${result.reference}` : "Tes coordonnées"}
          </h2>
        </div>
        <button type="button" className="icon-button" onClick={close} aria-label="Fermer">
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {result ? (
        <div className="checkout-success">
          <span className="success-mark">
            <BadgeCheck size={30} aria-hidden="true" />
          </span>
          <p className="success-copy">
            Il reste une étape : envoie ton reçu {methodLabel} sur WhatsApp. Aucun paiement n'est
            confirmé automatiquement.
          </p>

          <button
            type="button"
            className="reference-copy"
            onClick={() => {
              void navigator.clipboard?.writeText(result.reference).then(() => setCopied(true));
            }}
          >
            <span>
              <small>Ta référence</small>
              <strong>{result.reference}</strong>
            </span>
            <Copy size={16} aria-hidden="true" />
            <em aria-live="polite">{copied ? "Copiée" : ""}</em>
          </button>

          <ul className="success-lines">
            {result.items.map((item, index) => (
              <li key={item.offer_id} style={stagger(index)}>
                <span>
                  {item.quantity} × {item.offer_name}
                </span>
                <b>{money(item.total_millimes)}</b>
              </li>
            ))}
          </ul>
          <div className="cart-total">
            <span>Total à vérifier</span>
            <strong>{money(result.total_millimes)}</strong>
          </div>

          <a
            className="button button-primary button-block"
            href={result.whatsapp_url}
            target="_blank"
            rel="noreferrer"
          >
            Ouvrir WhatsApp <ArrowRight size={17} aria-hidden="true" />
          </a>
          <p className="success-hint">
            Un récapitulatif vient d'être envoyé à <strong>{email.trim()}</strong>. Garde la référence{" "}
            <strong>{result.reference}</strong> jusqu'à la livraison de tes {result.order_ids.length}{" "}
            {plural(result.order_ids.length, "produit", "produits")}.
          </p>
        </div>
      ) : (
        <form className="checkout-form" onSubmit={onSubmit} noValidate>
          <div className="checkout-recap">
            <span>
              {cart.count} {plural(cart.count, "article", "articles")}
            </span>
            <strong>{money(cart.totalMillimes)}</strong>
          </div>

          <label>
            Nom complet
            <input
              required
              name="name"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ex. Amine Ben Salah"
            />
          </label>

          <label>
            Adresse email
            <input
              required
              name="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="toi@exemple.com"
              aria-describedby="email-hint"
            />
            <small id="email-hint">Ta confirmation et tes accès arriveront à cette adresse.</small>
          </label>

          <label>
            Numéro WhatsApp
            <span className="phone-field">
              <i>+216</i>
              <input
                required
                name="phone"
                inputMode="numeric"
                autoComplete="tel-national"
                value={displayPhone(phone)}
                onChange={(event) => setPhone(normalizePhoneInput(event.target.value))}
                placeholder="21 994 132"
                aria-describedby="phone-hint"
              />
            </span>
            <small id="phone-hint">8 chiffres, c'est là que la vérification se fera.</small>
          </label>

          <fieldset className="method-choice">
            <legend>Moyen de paiement</legend>
            {paymentMethods.map((option) => (
              <label key={option.id} className={method === option.id ? "selected" : ""}>
                <input
                  type="radio"
                  name="payment_method"
                  value={option.id}
                  checked={method === option.id}
                  onChange={() => setMethod(option.id)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>

          <label>
            <span className="field-label">
              Remarque <i>(optionnel)</i>
            </span>
            <textarea
              name="note"
              rows={2}
              maxLength={400}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Une préférence, une précision…"
            />
          </label>

          <p className="manual-warning">
            <ShieldAlert size={18} aria-hidden="true" />
            <span>
              <strong>Vérification humaine</strong>
              Après validation, WhatsApp s'ouvre avec ta référence. Un administrateur contrôle ton
              reçu avant la livraison.
            </span>
          </p>

          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="button button-primary button-block"
            disabled={submitting || !cart.lines.length}
          >
            {submitting ? "Création en cours…" : "Valider et payer"}
            {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
          </button>
        </form>
      )}
    </Overlay>
  );
}
