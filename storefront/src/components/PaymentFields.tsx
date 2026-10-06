import { useId, useState } from "react";
import { Copy, ImagePlus, Trash2 } from "lucide-react";
import { receiptDataUrl } from "@/lib/image";
import { money } from "@/lib/format";
import type { PaymentMethod } from "@/types";

const METHOD_LOGOS: Record<string, string> = {
  d17: "/payments/d17.png",
  flouci: "/payments/flouci.png",
  izi: "/payments/izi.webp",
  wafacash: "/payments/wafacash.webp",
};

function methodLogo(id: string) {
  return METHOD_LOGOS[id.toLowerCase()] ?? "";
}

/** Card numbers are shown in groups of four and copied as plain digits. */
function destinationText(details: string): { display: string; copy: string; grouped: boolean } {
  const compact = details.replace(/\s+/g, "");
  if (/^\d{12,19}$/.test(compact)) {
    return { display: compact.replace(/(.{4})/g, "$1 ").trim(), copy: compact, grouped: true };
  }
  return { display: details, copy: details, grouped: false };
}

type MethodPickerProps = {
  methods: PaymentMethod[];
  value: string;
  onChange: (id: string) => void;
  name: string;
};

export function MethodPicker({ methods, value, onChange, name }: MethodPickerProps) {
  return (
    <fieldset className="method-choice">
      <legend>Moyen de paiement</legend>
      {methods.map((option) => {
        const logo = methodLogo(option.id);
        return (
          <label key={option.id} className={value === option.id ? "selected" : ""}>
            {logo ? <img className={`method-logo method-logo-${option.id.toLowerCase()}`} src={logo} alt="" /> : null}
            <span className="method-line">
              <input
                type="radio"
                name={name}
                value={option.id}
                checked={value === option.id}
                onChange={() => onChange(option.id)}
              />
              <span>{option.label}</span>
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

/** Where to send the money, with the exact amount to transfer. */
export function PaymentInstructions({ method, amountMillimes }: { method?: PaymentMethod; amountMillimes?: number }) {
  const [copied, setCopied] = useState(false);
  if (!method) return null;
  const logo = methodLogo(method.id);
  const postal = method.id === "virement_postal";
  const destination = method.details ? destinationText(method.details) : null;
  return (
    <div className="payment-instructions">
      <p>
        {logo ? <img className={`method-logo method-logo-${method.id.toLowerCase()}`} src={logo} alt="" /> : null}
        {amountMillimes ? (
          <>
            Envoie <strong>{money(amountMillimes)}</strong> par {method.label} :
          </>
        ) : (
          <>Envoie le montant choisi par {method.label} :</>
        )}
      </p>
      <div className="payment-target">
        <span>
          {method.account_label ? <span className="payment-account">{method.account_label}</span> : null}
          {destination ? (
            <span className={destination.grouped ? "payment-account-number" : undefined}>{destination.display}</span>
          ) : (
            "Coordonnées bientôt disponibles."
          )}
        </span>
        {destination ? (
          <button
            type="button"
            className="icon-button"
            aria-label="Copier les coordonnées"
            onClick={() => {
              void navigator.clipboard?.writeText(destination.copy).then(() => setCopied(true));
            }}
          >
            <Copy size={15} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      <small aria-live="polite">
        {copied ? "Copié." : postal ? "Ajoute ensuite une capture du virement." : "Ajoute ensuite une capture du reçu."}
      </small>
    </div>
  );
}

type ReceiptFieldProps = {
  value: string;
  onChange: (dataUrl: string) => void;
  onError: (message: string) => void;
  label?: string;
};

export function ReceiptField({ value, onChange, onError, label = "Capture du reçu" }: ReceiptFieldProps) {
  const inputId = useId();
  const [busy, setBusy] = useState(false);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    try {
      onChange(await receiptDataUrl(file));
      onError("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Image illisible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="receipt-field">
      <span className="field-label">{label}</span>
      {value ? (
        <div className="receipt-preview">
          <img src={value} alt="Aperçu du reçu" />
          <button type="button" className="button button-quiet" onClick={() => onChange("")}>
            <Trash2 size={15} aria-hidden="true" /> Changer
          </button>
        </div>
      ) : (
        <label htmlFor={inputId} className="receipt-drop">
          <ImagePlus size={22} aria-hidden="true" />
          <span>{busy ? "Préparation de l'image…" : "Ajouter une capture (PNG, JPEG, WebP)"}</span>
          <input
            id={inputId}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => {
              void onFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      )}
    </div>
  );
}
