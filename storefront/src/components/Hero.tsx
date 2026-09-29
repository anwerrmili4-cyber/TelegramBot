import { ArrowRight, BadgeCheck, Coins, Sparkles, Zap } from "lucide-react";

export function Hero({ whatsappNumber }: { whatsappNumber: string }) {
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
        Remplis ton panier, règle le total avec D17 ou Flouci, puis envoie ton reçu sur WhatsApp.
        Un humain vérifie, puis on livre.
      </p>

      <div className="hero-actions">
        <a className="button button-primary button-lg" href="#catalogue">
          Voir le catalogue <ArrowRight size={18} aria-hidden="true" />
        </a>
        <a
          className="button button-ghost button-lg"
          href={`https://wa.me/${whatsappNumber}`}
          target="_blank"
          rel="noreferrer"
        >
          Parler au support
        </a>
      </div>

      <ul className="hero-trust">
        <li>
          <Coins size={16} aria-hidden="true" /> Prix affichés en DT
        </li>
        <li>
          <Zap size={16} aria-hidden="true" /> Stock mis à jour en direct
        </li>
        <li>
          <BadgeCheck size={16} aria-hidden="true" /> Vérification humaine
        </li>
      </ul>
    </section>
  );
}
