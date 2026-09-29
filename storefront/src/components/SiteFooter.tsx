import { UserRound } from "lucide-react";
import { Link } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="brand">
        <img src="/logo.png" alt="" width="40" height="40" />
        <div>
          <strong>BLACKMARKET</strong>
          <small>Tunisie</small>
        </div>
      </div>
      <p>
        Paiements D17, Flouci, IZI et Wafa Cash vérifiés par un administrateur. Tes accès sont livrés par
        email et restent disponibles dans ton espace.
      </p>
      <Link to={accountPath("commandes")}>
        <UserRound size={16} aria-hidden="true" /> Mon espace client
      </Link>
    </footer>
  );
}
