import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BadgeCheck, Clock3, LogIn, PackageCheck, Wallet as WalletIcon, X } from "lucide-react";
import { Overlay } from "@/components/Overlay";
import { MethodPicker, PaymentInstructions, ReceiptField } from "@/components/PaymentFields";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, fetchWallet, submitCheckout } from "@/lib/api";
import { money, plural } from "@/lib/format";
import { stagger } from "@/lib/motion";
import { navigate, ROUTES, withNext } from "@/lib/router";
import { accountPath } from "@/lib/accountPath";
import type { Cart } from "@/hooks/useCart";
import type { CheckoutResult, PaymentMethod } from "@/types";

type CheckoutDialogProps = {
  open: boolean;
  cart: Cart;
  paymentMethods: PaymentMethod[];
  onClose: () => void;
  onConfirmed: () => void;
};

type PayWith = "wallet" | "transfer";

const BULLET = /^([•\u2022\-*]|\d+[.)])\s+(.+)$/;

/** Split an admin remark into the introduction and each detail the customer must send. */
function infoFields(remark: string, productName: string): { intro: string; items: string[] } {
  const text = remark.replace(/\r\n/g, "\n").trim();
  if (!text) return { intro: "", items: [`Informations pour ${productName}`] };
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const items = lines.flatMap((line) => {
    const parts = line.split(/\s*•\s*/).map((part) => part.trim()).filter(Boolean);
    if (parts.length >= 2) return parts[0].endsWith(":") ? parts.slice(1) : parts;
    const marked = line.match(BULLET);
    return marked ? [marked[2].trim()] : [];
  });
  if (items.length >= 2) {
    const intro = lines
      .map((line) => (line.includes("•") ? line.split(/\s*•\s*/)[0].trim() : line))
      .filter((line) => line && !BULLET.test(line) && line.endsWith(":"))
      .join("\n");
    return { intro, items };
  }
  return { intro: "", items: [text] };
}

function packedInfo(items: string[], answers: string[]): string {
  if (items.length <= 1) return (answers[0] || "").trim();
  return items.map((item, index) => `${item} : ${(answers[index] || "").trim()}`).join("\n");
}

export function CheckoutDialog({ open, cart, paymentMethods, onClose, onConfirmed }: CheckoutDialogProps) {
  const { customer, token, handleError } = useAuth();
  const [balance, setBalance] = useState<number | null>(null);
  const [payWith, setPayWith] = useState<PayWith>("wallet");
  const [method, setMethod] = useState(paymentMethods[0]?.id ?? "");
  const [receipt, setReceipt] = useState("");
  const [info, setInfo] = useState<Record<number, string[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CheckoutResult | null>(null);
  const checkoutKey = useRef("");

  const total = cart.totalMillimes;
  const walletEnough = balance !== null && balance >= total;
  const chosenMethod = paymentMethods.find((option) => option.id === method) ?? paymentMethods[0];

  useEffect(() => {
    if (!open) return;
    checkoutKey.current = globalThis.crypto?.randomUUID?.() ?? `pay-${Date.now()}`;
  }, [open]);

  useEffect(() => {
    if (!open || !token) return;
    const controller = new AbortController();
    fetchWallet(token, controller.signal)
      .then((wallet) => {
        setBalance(wallet.balance_millimes);
        if (wallet.balance_millimes < total) setPayWith("transfer");
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) handleError(reason);
      });
    return () => controller.abort();
  }, [open, token, total, handleError]);

  function setAnswer(offerId: number, index: number, value: string) {
    setInfo((current) => {
      const next = [...(current[offerId] || [])];
      next[index] = value;
      return { ...current, [offerId]: next };
    });
  }

  function close() {
    onClose();
    if (result) {
      // The cart is only discarded once the customer leaves a confirmed order,
      // so a failed submission never loses their selection.
      setResult(null);
      setReceipt("");
      setInfo({});
      onConfirmed();
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (payWith === "wallet" && !walletEnough) {
      setError("Solde insuffisant : recharge ton portefeuille ou paie par virement.");
      return;
    }
    if (payWith === "transfer" && !receipt) {
      setError(
        chosenMethod?.id === "virement_postal"
          ? "Ajoute une capture du virement."
          : "Ajoute une capture de ton reçu.",
      );
      return;
    }
    const missing = cart.lines.find((line) => {
      if (!line.offer.requires_info) return false;
      const answers = info[line.offer.id] || [];
      return infoFields(line.offer.remark || "", line.offer.name).items.some((_, index) => !(answers[index] || "").trim());
    });
    if (missing) {
      setError(`« ${missing.offer.name} » : envoie les informations demandées.`);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const created = await submitCheckout(token, {
        payment_method: payWith === "wallet" ? "wallet" : chosenMethod?.id ?? "",
        idempotency_key: checkoutKey.current,
        receipt: payWith === "transfer" ? receipt : undefined,
        items: cart.lines.map((line) => ({
          offer_id: line.offer.id,
          quantity: line.quantity,
          ...(line.offer.requires_info
            ? {
                info: packedInfo(
                  infoFields(line.offer.remark || "", line.offer.name).items,
                  info[line.offer.id] || [],
                ),
              }
            : {}),
        })),
      });
      setResult(created);
      setBalance(created.balance_millimes);
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Impossible de créer la commande."));
    } finally {
      setSubmitting(false);
    }
  }

  function goToAccount(tab: "commandes" | "portefeuille") {
    close();
    navigate(accountPath(tab));
  }

  return (
    <Overlay open={open} onClose={close} labelledBy="checkout-title" variant="dialog">
      <header className="dialog-head">
        <div>
          <span className="kicker">{result ? "Commande enregistrée" : "Finaliser"}</span>
          <h2 id="checkout-title">{result ? `Référence ${result.reference}` : "Paiement"}</h2>
        </div>
        <button type="button" className="icon-button" onClick={close} aria-label="Fermer">
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {!customer ? (
        <div className="checkout-success">
          <span className="success-mark">
            <LogIn size={28} aria-hidden="true" />
          </span>
          <p className="success-copy">
            Connecte-toi pour payer : tes accès seront livrés par email et resteront disponibles dans ton
            espace client. Ton panier est conservé.
          </p>
          <button
            type="button"
            className="button button-primary button-block"
            onClick={() => {
              onClose();
              navigate(withNext(ROUTES.login, "/"));
            }}
          >
            Se connecter <ArrowRight size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="button button-ghost button-block"
            onClick={() => {
              onClose();
              navigate(withNext(ROUTES.register, "/"));
            }}
          >
            Créer un compte
          </button>
        </div>
      ) : result ? (
        <CheckoutSuccess result={result} onOpenAccount={goToAccount} />
      ) : (
        <form className="checkout-form" onSubmit={onSubmit} noValidate>
          <div className="checkout-recap">
            <span>
              {cart.count} {plural(cart.count, "article", "articles")}
            </span>
            <strong>{money(total)}</strong>
          </div>

          <ul className="checkout-lines">
            {cart.lines.map((line) => {
              const prompt = line.offer.requires_info ? infoFields(line.offer.remark || "", line.offer.name) : null;
              const answers = info[line.offer.id] || [];
              return (
                <li key={line.offer.id}>
                  <div className="checkout-line">
                    <span>
                      <strong>{line.offer.name}</strong>
                      <small>
                        {line.quantity} {plural(line.quantity, "unité", "unités")}
                      </small>
                    </span>
                    <b>{money(line.offer.price_millimes * line.quantity)}</b>
                  </div>
                  {prompt ? (
                    <fieldset className="info-ask">
                      <legend>Pour ce produit</legend>
                      {prompt.intro ? <p>{prompt.intro}</p> : null}
                      {prompt.items.map((item, index) => {
                        const long = item.includes("\n") || item.length > 90;
                        return (
                          <label key={`${line.offer.id}-${index}`}>
                            <span className="field-label">{item}</span>
                            {long ? (
                              <textarea
                                name={`info-${line.offer.id}-${index}`}
                                rows={3}
                                maxLength={400}
                                required
                                autoComplete="off"
                                value={answers[index] || ""}
                                onChange={(event) => setAnswer(line.offer.id, index, event.target.value)}
                              />
                            ) : (
                              <input
                                name={`info-${line.offer.id}-${index}`}
                                maxLength={400}
                                required
                                autoComplete="off"
                                value={answers[index] || ""}
                                onChange={(event) => setAnswer(line.offer.id, index, event.target.value)}
                              />
                            )}
                          </label>
                        );
                      })}
                    </fieldset>
                  ) : line.offer.remark ? (
                    <p className="order-note">
                      <span className="remark-copy">
                        <b>Remarque</b>
                        {line.offer.remark}
                      </span>
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>

          <fieldset className="pay-with">
            <legend>Payer avec</legend>
            <label className={payWith === "wallet" ? "selected" : ""}>
              <input
                type="radio"
                name="pay_with"
                checked={payWith === "wallet"}
                onChange={() => setPayWith("wallet")}
              />
              <WalletIcon size={18} aria-hidden="true" />
              <span>
                <strong>Mon portefeuille</strong>
                <small>
                  {balance === null
                    ? "Chargement du solde…"
                    : walletEnough
                      ? `Solde : ${money(balance)} · livraison immédiate`
                      : `Solde : ${money(balance)} · insuffisant`}
                </small>
              </span>
            </label>
            <label className={payWith === "transfer" ? "selected" : ""}>
              <input
                type="radio"
                name="pay_with"
                checked={payWith === "transfer"}
                onChange={() => setPayWith("transfer")}
                disabled={!paymentMethods.length}
              />
              <Clock3 size={18} aria-hidden="true" />
              <span>
                <strong>Virement avec reçu</strong>
                <small>{paymentMethods.map((option) => option.label).join(", ") || "Indisponible"}</small>
              </span>
            </label>
          </fieldset>

          {payWith === "wallet" ? (
            balance !== null && !walletEnough ? (
              <p className="manual-warning">
                <WalletIcon size={18} aria-hidden="true" />
                <span>
                  <strong>Il te manque {money(total - balance)}</strong>
                  Recharge ton portefeuille depuis ton espace, ou paie cette commande par virement.
                  <button type="button" className="auth-inline-link" onClick={() => goToAccount("portefeuille")}>
                    Recharger mon portefeuille
                  </button>
                </span>
              </p>
            ) : null
          ) : (
            <>
              <MethodPicker
                methods={paymentMethods}
                value={chosenMethod?.id ?? ""}
                onChange={setMethod}
                name="payment_method"
              />
              <PaymentInstructions method={chosenMethod} amountMillimes={total} />
              <ReceiptField
                value={receipt}
                onChange={setReceipt}
                onError={setError}
                label={chosenMethod?.id === "virement_postal" ? "Capture du virement" : "Capture du reçu"}
              />
            </>
          )}

          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="button button-primary button-block"
            disabled={submitting || !cart.lines.length || (payWith === "wallet" && !walletEnough)}
          >
            {submitting
              ? "Paiement en cours…"
              : payWith === "wallet"
                ? `Payer ${money(total)}`
                : "Envoyer mon reçu"}
            {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
          </button>
        </form>
      )}
    </Overlay>
  );
}

function CheckoutSuccess({
  result,
  onOpenAccount,
}: {
  result: CheckoutResult;
  onOpenAccount: (tab: "commandes" | "portefeuille") => void;
}) {
  const delivered = result.status === "delivered";
  const waiting = result.status === "to_verify";
  return (
    <div className="checkout-success">
      <span className="success-mark">
        {delivered ? <PackageCheck size={30} aria-hidden="true" /> : <BadgeCheck size={30} aria-hidden="true" />}
      </span>
      <p className="success-copy">
        {delivered
          ? "Commande livrée ! Tes accès viennent d'arriver par email et sont disponibles dans ton espace."
          : waiting
            ? "Ton reçu a bien été envoyé. Un administrateur le vérifie, puis tes accès arrivent par email et dans ton espace."
            : "Paiement confirmé. Ta livraison est en préparation : tu recevras tes accès par email et dans ton espace."}
      </p>

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
        <span>{waiting ? "Total à vérifier" : "Total payé"}</span>
        <strong>{money(result.total_millimes)}</strong>
      </div>
      {result.payment_method === "wallet" ? (
        <p className="success-hint">Nouveau solde : {money(result.balance_millimes)}</p>
      ) : null}

      <button type="button" className="button button-primary button-block" onClick={() => onOpenAccount("commandes")}>
        {delivered ? "Voir mes accès" : "Suivre ma commande"} <ArrowRight size={17} aria-hidden="true" />
      </button>
    </div>
  );
}
