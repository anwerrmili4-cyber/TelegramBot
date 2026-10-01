import { useEffect, useState } from "react";
import {
  Check,
  X,
} from "lucide-react";
import { money, date, ActionButton, Modal } from "../admin-kit.jsx";

export const shortTxid = (txid) => (txid ? `${txid.slice(0, 9)}…${txid.slice(-6)}` : "—");

export const topupCustomerName = (topup) => topup.username
  ? `@${topup.username}`
  : topup.full_name || topup.first_name || `Client ${topup.user_id}`;

export function TopupDecisionModal({ decision, busy, onCancel, onConfirm }) {
  const { topup, approved } = decision;
  const amount = money(topup.amount, topup.currency || "USDT");
  const customer = topupCustomerName(topup);
  return (
    <Modal title={approved ? "Accepter ce dépôt" : "Refuser ce dépôt"} onClose={onCancel}>
      <div className="delete-confirmation">
        <span>{approved ? <Check size={22} /> : <X size={22} />}</span>
        <div>
          <h4>{approved ? `Créditer ${amount} à ${customer} ?` : `Refuser le dépôt de ${amount} de ${customer} ?`}</h4>
          <p>{approved
            ? "Vérifiez que ce TXID correspond à un paiement réellement reçu : le portefeuille sera crédité immédiatement."
            : "Le dépôt sera marqué comme refusé et le portefeuille ne sera pas crédité."}</p>
          <p style={{ wordBreak: "break-all" }}>TXID : {topup.explorer_url && topup.txid
            ? <a className="txid-link" href={topup.explorer_url} target="_blank" rel="noreferrer">{topup.txid}</a>
            : topup.txid || "—"}</p>
        </div>
      </div>
      <div className="dialog-actions">
        <ActionButton secondary onClick={onCancel}>Annuler</ActionButton>
        <ActionButton danger={!approved} icon={approved ? Check : X} disabled={busy} onClick={onConfirm}>
          {approved ? "Accepter et créditer" : "Refuser le dépôt"}
        </ActionButton>
      </div>
    </Modal>
  );
}

export function PendingWalletTopups({ onAction }) {
  const [topups, setTopups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [decision, setDecision] = useState(null);
  const load = () => {
    setLoading(true);
    return fetch("/admin/api/wallet-topups?status=manual_review", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((payload) => setTopups(payload.items || []))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  const decide = async (topup, approved) => {
    setBusyId(topup.id);
    try {
      const result = await onAction({
        action: approved ? "approve_wallet_topup" : "reject_wallet_topup",
        topup_id: topup.id,
      });
      if (result) await load();
    } finally {
      setBusyId(null);
      setDecision(null);
    }
  };
  if (!loading && !topups.length) return null;
  return (
    <section className="data-panel pending-topups">
      <header>
        <div>
          <span className="eyebrow">Validation manuelle</span>
          <h3>Rechargements on-chain en attente</h3>
          <p>Vérifiez le TXID avant de créditer le portefeuille.</p>
        </div>
        <span className="pending-topup-count">{topups.length}</span>
      </header>
      <div className="responsive-table">
        <table>
          <thead><tr><th>Demande</th><th>Client</th><th>Réseau</th><th>Montant</th><th>TXID</th><th>Date</th><th>Décision</th></tr></thead>
          <tbody>
            {topups.map((topup) => (
              <tr key={topup.id}>
                <td><strong>#{topup.id}</strong></td>
                <td><strong>{topup.username ? `@${topup.username}` : topup.first_name || `Client ${topup.user_id}`}</strong><small>{topup.user_id}</small></td>
                <td><span className="status manual_review">{topup.network === "bsc" ? "BSC (BEP20)" : "Polygon"}</span></td>
                <td><strong>{money(topup.amount, topup.currency || "USDT")}</strong></td>
                <td>{topup.explorer_url && topup.txid ? <a className="txid-link" href={topup.explorer_url} target="_blank" rel="noreferrer" title={topup.txid}>{shortTxid(topup.txid)}</a> : <span className="txid-text" title={topup.txid || ""}>{shortTxid(topup.txid)}</span>}</td>
                <td>{date(topup.created_at)}</td>
                <td>
                  <div className="topup-actions">
                    <ActionButton icon={Check} disabled={busyId === topup.id} onClick={() => setDecision({ topup, approved: true })}>Accepter</ActionButton>
                    <ActionButton danger icon={X} disabled={busyId === topup.id} onClick={() => setDecision({ topup, approved: false })}>Refuser</ActionButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <div className="table-loading">Chargement des demandes…</div>}
      {decision && <TopupDecisionModal decision={decision} busy={busyId === decision.topup.id} onCancel={() => setDecision(null)} onConfirm={() => decide(decision.topup, decision.approved)} />}
    </section>
  );
}

export const DEPOSIT_PROVIDER_LABELS = {
  binance: "Binance Pay",
  bybit: "Bybit",
  bsc: "BSC (BEP20)",
  polygon: "Polygon",
  solana: "Solana",
  unknown: "Autre",
};
