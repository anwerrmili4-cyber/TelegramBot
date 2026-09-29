import { ArrowRight, Coins, Sparkles, Wallet, Zap } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Link, ROUTES } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

export function Hero() {
  const { customer } = useAuth();
  return (
    <section className="hero" aria-labelledby="hero-title">
      <span className="hero-eyebrow">
        <Sparkles size={14} aria-hidden="true" /> Catalogue connecté en direct
      </span>
      <h1 id="hero-title">
        Les meilleurs services digitaux,
        <em>payés en dinar.</em>
      </h1>
      <p className="hero-lead">
        Recharge ton portefeuille par D17, Flouci, IZI ou Wafa Cash, puis achète en un clic. Tes accès
        arrivent par email et restent dans ton espace client.
      </p>

      <div className="hero-actions">
        <a className="button button-primary button-lg" href="#catalogue">
          Voir le catalogue <ArrowRight size={18} aria-hidden="true" />
        </a>
        <Link
          className="button button-ghost button-lg"
          to={customer ? accountPath("portefeuille") : ROUTES.register}
        >
          {customer ? "Recharger mon portefeuille" : "Créer un compte"}
        </Link>
      </div>

      <ul className="hero-trust">
        <li>
          <Coins size={16} aria-hidden="true" /> Prix affichés en DT
        </li>
        <li>
          <Zap size={16} aria-hidden="true" /> Livraison immédiate si en stock
        </li>
        <li>
          <Wallet size={16} aria-hidden="true" /> Portefeuille et historique
        </li>
      </ul>
    </section>
  );
}
