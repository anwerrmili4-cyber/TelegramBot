import { useState } from "react";
import { CheckCircle2, PackagePlus } from "lucide-react";
import { ActionButton, Field, Modal } from "./admin-kit.jsx";

const CLOSED_ORDER_STATUSES = new Set(["delivered", "cancelled", "refunded", "expired", "rejected"]);

export function canDeliverOrder(status) {
  return !CLOSED_ORDER_STATUSES.has(String(status || ""));
}

export function notificationSituation(notification) {
  if (!notification?.actionable) return null;
  const page = notification.target?.page;
  const entity = notification.target?.entity_id;
  if (entity == null || entity === "") return null;
  if (page === "orders" && notification.category === "order" && /^\d+$/.test(String(entity))) return "bot-deliver";
  if (page === "site-orders" && notification.category === "order") {
    const status = notification.target?.query?.status;
    if (status === "to_verify") return "site-confirm";
    if (status === "confirmed" || status === "partial") return "site-deliver";
  }
  return null;
}

function stopLineClick(event) {
  event.stopPropagation();
}

function DeliveryDialog({ title, help, content, sending, onChange, onClose, onSubmit }) {
  return (
    <Modal title={title} onClose={() => !sending && onClose()}>
      <form className="operation-form" onSubmit={onSubmit}>
        <p>{help}</p>
        <Field label="Contenu de livraison" wide>
          <textarea value={content} onChange={(event) => onChange(event.target.value)} placeholder="Identifiants, code ou lien à envoyer au client…" rows={4} maxLength={4000} required autoFocus />
        </Field>
        <div className="dialog-actions">
          <ActionButton type="button" secondary disabled={sending} onClick={onClose}>Retour</ActionButton>
          <ActionButton type="submit" icon={PackagePlus} disabled={sending || !content.trim()}>Envoyer et marquer livré</ActionButton>
        </div>
      </form>
    </Modal>
  );
}

export function DeliverOrderButton({ orderId, onAction }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    const text = content.trim();
    if (!text || sending) return;
    setSending(true);
    setOpen(false);
    try {
      const result = await onAction({ action: "manual_deliver_order", order_id: orderId, delivery_text: text });
      if (result) setContent("");
      else setOpen(true);
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="line-actions" onClick={stopLineClick} onMouseDown={stopLineClick}>
      <ActionButton type="button" icon={PackagePlus} onClick={() => setOpen(true)} aria-label={`Livrer la commande #${orderId}`}>Livrer</ActionButton>
      {open && <DeliveryDialog title={`Livrer la commande #${orderId}`} help="Ce contenu est envoyé au client. La commande est marquée livrée, même si elle n’était pas encore ouverte." content={content} sending={sending} onChange={setContent} onClose={() => setOpen(false)} onSubmit={submit} />}
    </div>
  );
}

function SiteDeliverButton({ reference, onAction }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    const text = content.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      const result = await onAction({ action: "site_cart_deliver", reference, note: text });
      if (result) {
        setOpen(false);
        setContent("");
      }
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="line-actions" onClick={stopLineClick} onMouseDown={stopLineClick}>
      <ActionButton type="button" icon={PackagePlus} onClick={() => setOpen(true)} aria-label={`Livrer le panier ${reference}`}>Livrer</ActionButton>
      {open && <DeliveryDialog title={`Livrer le panier ${reference}`} help="Ces accès sont envoyés au client par email, puis le panier est marqué livré." content={content} sending={sending} onChange={setContent} onClose={() => !sending && setOpen(false)} onSubmit={submit} />}
    </div>
  );
}

export function NotificationLineAction({ notification, onAction }) {
  const kind = notificationSituation(notification);
  const entity = notification.target?.entity_id;
  if (kind === "bot-deliver") return <DeliverOrderButton orderId={Number(entity)} onAction={onAction} />;
  if (kind === "site-confirm") {
    return (
      <div className="line-actions" onClick={stopLineClick} onMouseDown={stopLineClick}>
        <ActionButton type="button" icon={CheckCircle2} onClick={() => onAction({ action: "site_cart_confirm", reference: entity })} aria-label={`Confirmer le paiement du panier ${entity}`}>Confirmer</ActionButton>
      </div>
    );
  }
  if (kind === "site-deliver") return <SiteDeliverButton reference={String(entity)} onAction={onAction} />;
  return null;
}
