import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  BadgeCheck,
  ChevronDown,
  Copy,
  KeyRound,
  LogOut,
  Package,
  RotateCcw,
  UserRound,
  Wallet as WalletIcon,
} from "lucide-react";
import { MethodPicker, PaymentInstructions, ReceiptField } from "@/components/PaymentFields";
import { useAuth } from "@/hooks/useAuth";
import { createDeposit, errorMessage, fetchOrders, fetchWallet, resendVerificationCode } from "@/lib/api";
import { dateTime, displayPhone, isValidPhone, money, normalizePhoneInput, periodLabel, plural } from "@/lib/format";
import { Link, navigate, ROUTES, withNext } from "@/lib/router";
import { MIN_PASSWORD_LENGTH, PasswordField } from "@/pages/AuthLayout";
import { verifyEmailPath } from "@/pages/VerifyEmailPage";
import type { AccountOrder, AccountOrders, CartStatus, Deposit, Wallet } from "@/types";

const TABS = [
  { id: "commandes", label: "Mes achats", icon: Package },
  { id: "portefeuille", label: "Portefeuille", icon: WalletIcon },
  { id: "profil", label: "Profil & sécurité", icon: UserRound },
] as const;

type Tab = (typeof TABS)[number]["id"];

export function accountPath(tab: Tab = "commandes"): string {
  return `${ROUTES.account}?onglet=${tab}`;
}

function initialTab(): Tab {
  const requested = new URLSearchParams(window.location.search).get("onglet");
  return TABS.find((tab) => tab.id === requested)?.id ?? "commandes";
}

const CART_STATUS: Record<CartStatus, [string, string]> = {
  to_verify: ["Reçu en vérification", "pending"],
  confirmed: ["Paiement confirmé", "progress"],
  partial: ["Livraison partielle", "progress"],
  delivered: ["Livrée", "done"],
  cancelled: ["Annulée", "failed"],
  mixed: ["En cours", "progress"],
};

const LINE_STATUS: Record<string, [string, string]> = {
  to_verify: ["En vérification", "pending"],
  confirmed: ["En préparation", "progress"],
  delivered: ["Livré", "done"],
  cancelled: ["Annulé", "failed"],
};

const DEPOSIT_STATUS: Record<Deposit["status"], [string, string]> = {
  pending: ["En vérification", "pending"],
  approved: ["Créditée", "done"],
  rejected: ["Refusée", "failed"],
};

function StatusChip({ label, tone }: { label: string; tone: string }) {
  return <span className={`status-chip status-${tone}`}>{label}</span>;
}

export function AccountPage() {
  const { customer, loading, logout } = useAuth();
  const [tab, setTab] = useState<Tab>(initialTab);

  useEffect(() => {
    if (!loading && !customer) navigate(withNext(ROUTES.login, accountPath(tab)), { replace: true });
  }, [loading, customer, tab]);

  function select(next: Tab) {
    setTab(next);
    window.history.replaceState(null, "", accountPath(next));
  }

  if (!customer) {
    return (
      <section className="account-page">
        <p className="account-loading">Chargement de ton espace…</p>
      </section>
    );
  }

  return (
    <section className="account-page" aria-labelledby="account-title">
      <header className="account-head">
        <div>
          <span className="kicker">Mon espace</span>
          <h1 id="account-title">Bonjour {customer.name.split(" ")[0]}</h1>
          <p>{customer.email}</p>
        </div>
        <button type="button" className="button button-ghost" onClick={() => void logout().then(() => navigate(ROUTES.home))}>
          <LogOut size={16} aria-hidden="true" /> Se déconnecter
        </button>
      </header>

      <div className="account-tabs" role="tablist" aria-label="Sections du compte">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => select(id)}
          >
            <Icon size={16} aria-hidden="true" /> {label}
          </button>
        ))}
      </div>

      {tab === "commandes" ? <OrdersTab /> : tab === "portefeuille" ? <WalletTab /> : <ProfileTab />}
    </section>
  );
}

/* ---------- Purchases ---------- */

function OrdersTab() {
  const { customer, token, handleError } = useAuth();
  const [data, setData] = useState<AccountOrders | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetchOrders(token, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        handleError(reason);
        setError(errorMessage(reason, "Impossible de charger tes achats."));
      });
    return () => controller.abort();
  }, [token, attempt, handleError]);

  async function confirmEmail() {
    if (!customer) return;
    await resendVerificationCode(customer.email).catch(() => undefined);
    navigate(verifyEmailPath(customer.email, accountPath("commandes")));
  }

  if (error) {
    return (
      <div className="account-empty">
        <p>{error}</p>
        <button type="button" className="button button-primary" onClick={() => setAttempt((value) => value + 1)}>
          <RotateCcw size={16} aria-hidden="true" /> Réessayer
        </button>
      </div>
    );
  }
  if (!data) return <p className="account-loading">Chargement de tes achats…</p>;

  return (
    <div className="account-section">
      {!data.email_confirmed ? (
        <p className="manual-warning">
          <BadgeCheck size={18} aria-hidden="true" />
          <span>
            <strong>Confirme ton adresse email</strong>
            Tes commandes passées sans compte avec {customer?.email} apparaîtront ici une fois l'adresse confirmée.
            <button type="button" className="auth-inline-link" onClick={() => void confirmEmail()}>
              Recevoir un code
            </button>
          </span>
        </p>
      ) : null}

      {data.orders.length ? (
        <ul className="order-list">
          {data.orders.map((order, index) => (
            <OrderCard key={order.reference} order={order} defaultOpen={index === 0} />
          ))}
        </ul>
      ) : (
        <div className="account-empty">
          <Package size={32} aria-hidden="true" />
          <h3>Aucun achat pour l'instant</h3>
          <p>Tes commandes, leur statut et tes accès livrés apparaîtront ici.</p>
          <Link className="button button-primary" to="/#catalogue">
            Parcourir le catalogue <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      )}
    </div>
  );
}

function OrderCard({ order, defaultOpen }: { order: AccountOrder; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [label, tone] = CART_STATUS[order.status] ?? CART_STATUS.mixed;
  const count = order.items.reduce((sum, item) => sum + item.quantity, 0);
  return (
    <li className={`order-card${open ? " open" : ""}`}>
      <button type="button" className="order-summary" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="order-main">
          <strong>{order.reference}</strong>
          <small>
            {dateTime(order.created_at)} · {count} {plural(count, "article", "articles")} · {order.payment_label}
          </small>
        </span>
        <StatusChip label={label} tone={tone} />
        <b>{money(order.total_millimes)}</b>
        <ChevronDown size={18} aria-hidden="true" className="order-chevron" />
      </button>

      {open ? (
        <div className="order-details">
          <ul className="order-items">
            {order.items.map((item) => {
              const [itemLabel, itemTone] = LINE_STATUS[item.status] ?? LINE_STATUS.to_verify;
              const period = periodLabel(item.period_days);
              return (
                <li key={item.id}>
                  <div className="order-item-head">
                    <span>
                      <strong>
                        {item.quantity} × {item.offer_name}
                      </strong>
                      <small>
                        {item.service_name}
                        {period ? ` · ${period}` : ""} · {money(item.total_millimes)}
                      </small>
                    </span>
                    <StatusChip label={itemLabel} tone={itemTone} />
                  </div>
                  {item.delivery ? <DeliveryBox content={item.delivery} deliveredAt={item.delivered_at} /> : null}
                </li>
              );
            })}
          </ul>
          <dl className="order-meta">
            <div>
              <dt>Paiement</dt>
              <dd>
                {order.payment_label}
                {order.transaction_reference ? ` · réf. ${order.transaction_reference}` : ""}
              </dd>
            </div>
            {order.paid_at ? (
              <div>
                <dt>Payé le</dt>
                <dd>{dateTime(order.paid_at)}</dd>
              </div>
            ) : null}
            {order.cancel_reason ? (
              <div>
                <dt>Motif d'annulation</dt>
                <dd>{order.cancel_reason}</dd>
              </div>
            ) : null}
            {order.refunded_millimes ? (
              <div>
                <dt>Remboursé</dt>
                <dd>{money(order.refunded_millimes)} sur ton portefeuille</dd>
              </div>
            ) : null}
          </dl>
        </div>
      ) : null}
    </li>
  );
}

function DeliveryBox({ content, deliveredAt }: { content: string; deliveredAt: number | null }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="delivery-box">
      <div className="delivery-head">
        <span>Tes accès · livrés le {dateTime(deliveredAt)}</span>
        <button
          type="button"
          className="icon-button"
          aria-label="Copier les accès"
          onClick={() => {
            void navigator.clipboard?.writeText(content).then(() => setCopied(true));
          }}
        >
          <Copy size={15} aria-hidden="true" />
        </button>
      </div>
      <pre>{content}</pre>
      {copied ? <small aria-live="polite">Copié.</small> : null}
    </div>
  );
}

/* ---------- Wallet ---------- */

function WalletTab() {
  const { token, handleError } = useAuth();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchWallet(token, signal)
        .then(setWallet)
        .catch((reason: unknown) => {
          if (signal?.aborted) return;
          handleError(reason);
          setError(errorMessage(reason, "Impossible de charger ton portefeuille."));
        }),
    [token, handleError],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (error && !wallet) return <p className="form-error">{error}</p>;
  if (!wallet) return <p className="account-loading">Chargement du portefeuille…</p>;

  const pending = wallet.deposits.filter((deposit) => deposit.status === "pending");
  return (
    <div className="account-section wallet-layout">
      <div className="wallet-balance">
        <span>Solde disponible</span>
        <strong>{money(wallet.balance_millimes)}</strong>
        <small>
          {pending.length
            ? `${pending.length} recharge${pending.length > 1 ? "s" : ""} en vérification`
            : "Paie tes commandes en un clic, livraison immédiate quand le produit est en stock."}
        </small>
      </div>

      <DepositForm wallet={wallet} onCreated={() => void load()} />

      <section className="account-card">
        <h2>Mes recharges</h2>
        {wallet.deposits.length ? (
          <ul className="ledger">
            {wallet.deposits.map((deposit) => {
              const [label, tone] = DEPOSIT_STATUS[deposit.status];
              return (
                <li key={deposit.id}>
                  <span>
                    <strong>
                      {money(deposit.status === "approved" ? deposit.credited_millimes : deposit.amount_millimes)} ·{" "}
                      {deposit.method_label}
                    </strong>
                    <small>
                      Réf. {deposit.transaction_reference} · {dateTime(deposit.created_at)}
                      {deposit.reason ? ` · ${deposit.reason}` : ""}
                    </small>
                  </span>
                  <StatusChip label={label} tone={tone} />
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="account-muted">Aucune recharge pour l'instant.</p>
        )}
      </section>

      <section className="account-card">
        <h2>Historique du solde</h2>
        {wallet.transactions.length ? (
          <ul className="ledger">
            {wallet.transactions.map((row) => (
              <li key={row.id}>
                <span>
                  <strong>
                    {row.label}
                    {row.reference ? ` · ${row.reference}` : ""}
                  </strong>
                  <small>
                    {dateTime(row.created_at)}
                    {row.note ? ` · ${row.note}` : ""}
                  </small>
                </span>
                <b className={row.amount_millimes < 0 ? "amount-out" : "amount-in"}>
                  {row.amount_millimes > 0 ? "+" : "−"}
                  {money(Math.abs(row.amount_millimes))}
                </b>
              </li>
            ))}
          </ul>
        ) : (
          <p className="account-muted">Les recharges, achats et remboursements apparaîtront ici.</p>
        )}
      </section>
    </div>
  );
}

function DepositForm({ wallet, onCreated }: { wallet: Wallet; onCreated: () => void }) {
  const { token, handleError } = useAuth();
  const methods = wallet.payment_methods;
  const [method, setMethod] = useState(methods[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [receipt, setReceipt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const chosen = methods.find((option) => option.id === method) ?? methods[0];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const value = Number(amount.replace(",", "."));
    if (!value || value * 1000 < wallet.min_deposit_millimes || value * 1000 > wallet.max_deposit_millimes) {
      setError(
        `Le montant doit être compris entre ${money(wallet.min_deposit_millimes)} et ${money(wallet.max_deposit_millimes)}.`,
      );
      return;
    }
    if (reference.trim().length < 3) {
      setError("Saisis la référence de la transaction indiquée sur ton reçu.");
      return;
    }
    if (!receipt) {
      setError("Ajoute une capture de ton reçu.");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await createDeposit(token, {
        method: chosen?.id ?? "",
        amount: amount.trim(),
        transaction_reference: reference.trim(),
        receipt,
      });
      setAmount("");
      setReference("");
      setReceipt("");
      setNotice("Demande envoyée. Ton solde sera crédité dès que l'administrateur aura vérifié le reçu.");
      onCreated();
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Impossible d'envoyer la recharge."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!methods.length) {
    return (
      <section className="account-card">
        <h2>Recharger</h2>
        <p className="account-muted">Les recharges sont momentanément indisponibles.</p>
      </section>
    );
  }

  return (
    <section className="account-card">
      <h2>Recharger mon portefeuille</h2>
      <form className="checkout-form account-form" onSubmit={onSubmit} noValidate>
        <MethodPicker methods={methods} value={chosen?.id ?? ""} onChange={setMethod} name="deposit_method" />
        <PaymentInstructions method={chosen} />
        <label>
          Montant envoyé (DT)
          <input
            required
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
            placeholder="Ex. 50"
          />
        </label>
        <label>
          Référence de la transaction
          <input
            required
            value={reference}
            maxLength={64}
            onChange={(event) => setReference(event.target.value)}
            placeholder="Ex. 123456789"
          />
        </label>
        <ReceiptField value={receipt} onChange={setReceipt} onError={setError} />
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="form-success" role="status">
            {notice}
          </p>
        ) : null}
        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Envoi…" : "Envoyer la demande de recharge"}
        </button>
      </form>
    </section>
  );
}

/* ---------- Profile ---------- */

function ProfileTab() {
  const { customer, updateProfile, changePassword } = useAuth();
  const [name, setName] = useState(customer?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<[string, boolean] | null>(null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<[string, boolean] | null>(null);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (name.trim().length < 2) {
      setProfileMessage(["Saisis ton nom complet.", false]);
      return;
    }
    if (phone && !isValidPhone(phone)) {
      setProfileMessage(["Saisis un numéro tunisien valide à 8 chiffres.", false]);
      return;
    }
    setSavingProfile(true);
    try {
      await updateProfile(name.trim(), normalizePhoneInput(phone));
      setProfileMessage(["Profil enregistré.", true]);
    } catch (reason) {
      setProfileMessage([errorMessage(reason, "Impossible d'enregistrer le profil."), false]);
    } finally {
      setSavingProfile(false);
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (next.length < MIN_PASSWORD_LENGTH) {
      setPasswordMessage([`Le nouveau mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`, false]);
      return;
    }
    setSavingPassword(true);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setPasswordMessage(["Mot de passe modifié. Tes autres appareils ont été déconnectés.", true]);
    } catch (reason) {
      setPasswordMessage([errorMessage(reason, "Impossible de modifier le mot de passe."), false]);
    } finally {
      setSavingPassword(false);
    }
  }

  if (!customer) return null;
  return (
    <div className="account-section profile-layout">
      <section className="account-card">
        <h2>
          <UserRound size={18} aria-hidden="true" /> Mes informations
        </h2>
        <form className="auth-form" onSubmit={saveProfile} noValidate>
          <label>
            Nom complet
            <input value={name} autoComplete="name" onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Adresse email
            <input value={customer.email} disabled />
            <small>
              {customer.email_confirmed ? "Adresse confirmée." : "Adresse pas encore confirmée."} C'est là que tes
              accès sont envoyés.
            </small>
          </label>
          <label>
            Numéro de téléphone <small>(optionnel)</small>
            <span className="phone-field">
              <i>+216</i>
              <input
                inputMode="numeric"
                autoComplete="tel-national"
                value={displayPhone(phone)}
                onChange={(event) => setPhone(normalizePhoneInput(event.target.value))}
                placeholder="21 994 132"
              />
            </span>
          </label>
          {profileMessage ? (
            <p className={profileMessage[1] ? "form-success" : "form-error"} role="status">
              {profileMessage[0]}
            </p>
          ) : null}
          <button type="submit" className="button button-primary" disabled={savingProfile}>
            {savingProfile ? "Enregistrement…" : "Enregistrer"}
          </button>
        </form>
      </section>

      <section className="account-card">
        <h2>
          <KeyRound size={18} aria-hidden="true" /> {customer.has_password ? "Mot de passe" : "Créer un mot de passe"}
        </h2>
        <form className="auth-form" onSubmit={savePassword} noValidate>
          {customer.has_password ? (
            <PasswordField
              label="Mot de passe actuel"
              name="current_password"
              value={current}
              onChange={setCurrent}
              autoComplete="current-password"
            />
          ) : (
            <p className="account-hint">
              Tu te connectes avec Google. Ajoute un mot de passe si tu veux aussi te connecter avec ton email.
            </p>
          )}
          <PasswordField
            label="Nouveau mot de passe"
            name="new_password"
            value={next}
            onChange={setNext}
            autoComplete="new-password"
            hint={`${MIN_PASSWORD_LENGTH} caractères minimum.`}
          />
          {passwordMessage ? (
            <p className={passwordMessage[1] ? "form-success" : "form-error"} role="status">
              {passwordMessage[0]}
            </p>
          ) : null}
          <button type="submit" className="button button-primary" disabled={savingPassword || (customer.has_password && !current) || !next}>
            {savingPassword ? "Enregistrement…" : customer.has_password ? "Changer le mot de passe" : "Créer le mot de passe"}
          </button>
          {customer.has_password ? (
            <Link className="auth-inline-link" to={ROUTES.forgotPassword}>
              Mot de passe oublié ?
            </Link>
          ) : null}
        </form>
      </section>
    </div>
  );
}
