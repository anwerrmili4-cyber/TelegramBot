import { MessageCircle } from "lucide-react";

/** `21621994132` renders as `+216 21 994 132`. */
function prettyNumber(digits: string): string {
  const local = digits.replace(/^216/, "");
  return `+216 ${local.replace(/(\d{2})(\d{3})(\d{3})/, "$1 $2 $3")}`;
}

export function SiteFooter({ whatsappNumber }: { whatsappNumber: string }) {
  return (
    <footer className="site-footer">
      <div className="brand">
        <span aria-hidden="true">BM</span>
        <div>
          <strong>BLACKMARKET</strong>
          <small>Tunisie</small>
        </div>
      </div>
      <p>
        Paiements D17 et Flouci vérifiés manuellement. Aucun paiement n'est confirmé
        automatiquement.
      </p>
      <a href={`https://wa.me/${whatsappNumber}`} target="_blank" rel="noreferrer">
        <MessageCircle size={16} aria-hidden="true" /> {prettyNumber(whatsappNumber)}
      </a>
    </footer>
  );
}
