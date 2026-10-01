import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Package, Receipt, RefreshCw, Send, Users } from "lucide-react";
import { errorMessage, fetchTickets, openTicket, replyToTicket } from "@/lib/api";
import { money } from "@/lib/format";
import { Link, ROUTES, withNext } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";
import { useAuth } from "@/hooks/useAuth";
import type { AccountTicket, Category, Offer } from "@/types";

const SUPPORT = "https://t.me/b9hdc2";
const CHANNEL = "https://t.me/blackmarketBotChannel";
const GROUP = "https://t.me/Blackmarketgrp";

export function PageIntro({ kicker, title, children }: { kicker: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-intro">
      <span className="kicker">{kicker}</span>
      <h1>{title}</h1>
      {children ? <p>{children}</p> : null}
    </header>
  );
}

export function CategoriesPage({ categories, offers }: { categories: Category[]; offers: Offer[] }) {
  return (
    <section className="doc-page">
      <PageIntro kicker="Boutique" title="Catégories">
        Chaque rayon ouvre le catalogue filtré, avec le stock et les prix en dinar.
      </PageIntro>
      <ul className="category-grid">
        {categories.map((category) => {
          const count = offers.filter((offer) => offer.category === category.id).length;
          return (
            <li key={category.id}>
              <Link to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
                <strong>{category.label}</strong>
                <span>{count} produit{count > 1 ? "s" : ""}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function DealsPage({ offers, onOpenOffer }: { offers: Offer[]; onOpenOffer: (offer: Offer) => void }) {
  const picked = offers.filter((offer) => offer.featured || offer.badge);
  const shown = (picked.length ? picked : offers.filter((offer) => offer.available)).slice(0, 12);
  return (
    <section className="doc-page">
      <PageIntro kicker="Boutique" title="Offres">
        {picked.length
          ? "Les produits mis en avant dans le catalogue."
          : "Sélection des produits disponibles en ce moment."}
      </PageIntro>
      <ul className="price-list">
        {shown.map((offer) => (
          <li key={offer.id}>
            <button type="button" onClick={() => onOpenOffer(offer)}>
              <span>
                <strong>{offer.name}</strong>
                <small>{offer.category_label}</small>
              </span>
              <b>{money(offer.price_millimes)}</b>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PricesPage({ offers, onOpenOffer }: { offers: Offer[]; onOpenOffer: (offer: Offer) => void }) {
  return (
    <section className="doc-page">
      <PageIntro kicker="Boutique" title="Liste des prix">
        Prix du catalogue en dinar. Le stock affiché vient de la même source que la boutique.
      </PageIntro>
      <div className="price-table-wrap">
        <table className="price-table">
          <thead>
            <tr>
              <th>Produit</th>
              <th>Catégorie</th>
              <th>Prix</th>
              <th>Stock</th>
            </tr>
          </thead>
          <tbody>
            {offers.map((offer) => (
              <tr key={offer.id}>
                <td>
                  <button type="button" onClick={() => onOpenOffer(offer)}>
                    {offer.name}
                  </button>
                </td>
                <td>{offer.category_label}</td>
                <td>{money(offer.price_millimes)}</td>
                <td>{offer.available ? (offer.stock < 0 ? "En stock" : offer.stock) : "Épuisé"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const NEWS = [
  {
    title: "Recharges vérifiées à la main",
    body: "Un dépôt D17, Flouci, IZI ou Wafa Cash est crédité après contrôle du reçu et de la référence.",
  },
  {
    title: "Livraison dans le compte",
    body: "Quand le produit est en stock, l'accès part par email et reste visible dans Mes achats.",
  },
  {
    title: "Support sur le site",
    body: "Les réponses du support arrivent dans la messagerie du compte. Un ticket fermé ne reçoit plus de réponse.",
  },
];

export function NewsPage() {
  return (
    <section className="doc-page">
      <PageIntro kicker="Infos" title="Annonces">
        Ce qui change concrètement pour une commande sur le site.
      </PageIntro>
      <ul className="news-list">
        {NEWS.map((item) => (
          <li key={item.title}>
            <h2>{item.title}</h2>
            <p>{item.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

const SUPPORT_CARDS = [
  {
    icon: Package,
    title: "Où est mon produit ?",
    body: "La livraison part par email dès que le produit est en stock, et reste dans Mes achats.",
    to: accountPath("commandes"),
  },
  {
    icon: RefreshCw,
    title: "Demander un remplacement",
    body: "Ouvre la commande, dis ce qui ne va pas. La demande reste dans Garanties.",
    to: accountPath("garanties"),
  },
  {
    icon: Receipt,
    title: "Question de paiement",
    body: "D17, Flouci, IZI ou Wafa Cash : le solde bouge après vérification du reçu.",
    to: accountPath("portefeuille"),
  },
];

const SUPPORT_FOLDS = [
  {
    title: "Ma commande demande des précisions",
    body: "Certains accès ont besoin d'un email ou d'un identifiant. Ouvre la commande dans Mes achats et envoie le détail demandé. Le support te répond dans la messagerie.",
  },
  {
    title: "J'ai payé mais mon solde n'a pas bougé",
    body: "Un dépôt n'est crédité qu'après contrôle de la référence et de la capture. Vérifie Portefeuille, puis écris dans la messagerie avec le reçu si rien n'apparaît.",
  },
];

export function HelpPage() {
  return (
    <section className="doc-page support-page">
      <p className="crumb">
        <Link to={ROUTES.home}>Accueil</Link>
        <span aria-hidden="true">/</span>
        Support
      </p>
      <span className="kicker">On est là</span>
      <h1>Comment on peut t'aider ?</h1>
      <p className="support-lead">La plupart des réponses sont à un clic, et une personne réelle est à un message.</p>
      <div className="support-grid">
        {SUPPORT_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <Link className="support-card" key={card.title} to={card.to}>
              <span className="support-icon" aria-hidden="true">
                <Icon size={18} />
              </span>
              <strong>{card.title}</strong>
              <span>{card.body}</span>
            </Link>
          );
        })}
        <div className="support-folds">
          {SUPPORT_FOLDS.map((item) => (
            <details key={item.title}>
              <summary>{item.title}</summary>
              <p>{item.body}</p>
            </details>
          ))}
        </div>
        <aside className="support-contact">
          <span className="support-icon" aria-hidden="true">
            <Send size={18} />
          </span>
          <strong>Nous écrire</strong>
          <Link className="button button-primary button-block" to={ROUTES.messenger}>
            <Send size={16} aria-hidden="true" /> Ouvrir la messagerie
          </Link>
          <Link className="support-community" to={ROUTES.community}>
            <Users size={16} aria-hidden="true" /> Groupe communauté
          </Link>
        </aside>
      </div>
    </section>
  );
}

export function TermsPage() {
  return (
    <section className="doc-page doc-prose">
      <PageIntro kicker="Infos" title="Conditions">
        Règles d'usage du site BlackMarket Tunisie. Les achats passés par le bot Telegram suivent aussi les conditions du bot.
      </PageIntro>
      <h2>Le service</h2>
      <p>
        Le site vend des produits numériques et des abonnements, avec un portefeuille en dinar. La disponibilité, la durée et le prix affichés au moment de l'achat font foi. BlackMarket est un revendeur indépendant.
      </p>
      <h2>Paiement</h2>
      <p>
        Le montant et le moyen (D17, Flouci, IZI ou Wafa Cash) sont ceux indiqués au paiement. Un dépôt n'est crédité qu'après vérification du reçu. N'envoie jamais d'argent sur la base d'un message d'un compte inconnu.
      </p>
      <h2>Livraison et garantie</h2>
      <p>
        La commande est livrée quand l'accès est disponible par email ou dans le compte. Une garantie ne couvre que ce qui est écrit sur la fiche, et doit être ouverte pendant sa durée.
      </p>
      <h2>Support</h2>
      <p>
        Le support du site répond dans la messagerie. Le support Telegram officiel est disponible de 21h à minuit, heure de l'Inde.
      </p>
    </section>
  );
}

export function PrivacyPage() {
  return (
    <section className="doc-page doc-prose">
      <PageIntro kicker="Infos" title="Confidentialité">
        Le site ne garde que ce qui sert à commander, payer, livrer et répondre au support.
      </PageIntro>
      <p>
        Cela comprend le compte (nom, email, téléphone), les commandes, les recharges, les reçus de paiement et les messages de la messagerie. Les accès livrés restent dans le compte pour que tu puisses les retrouver.
      </p>
      <p>
        Ces données ne sont pas vendues. Elles sont utilisées pour créditer le portefeuille, livrer la commande, traiter une garantie et répondre à un ticket.
      </p>
    </section>
  );
}

export function ContactPage() {
  return (
    <section className="doc-page">
      <PageIntro kicker="Aide" title="Contact">
        Pour une commande ou un paiement, écris dans la messagerie du site. Le support Telegram reste le canal du bot.
      </PageIntro>
      <div className="link-row">
        <Link className="button button-primary" to={ROUTES.messenger}>
          Ouvrir la messagerie
        </Link>
        <a className="button button-ghost" href={SUPPORT} target="_blank" rel="noreferrer">
          Support Telegram
        </a>
      </div>
    </section>
  );
}

export function CommunityPage() {
  return (
    <section className="doc-page">
      <PageIntro kicker="Aide" title="Communauté">
        Les annonces publiques passent par la chaîne. Les échanges passent par le groupe.
      </PageIntro>
      <div className="link-row">
        <a className="button button-primary" href={CHANNEL} target="_blank" rel="noreferrer">
          Chaîne Telegram
        </a>
        <a className="button button-ghost" href={GROUP} target="_blank" rel="noreferrer">
          Groupe
        </a>
      </div>
    </section>
  );
}

export function ReportPage() {
  const { customer, token, handleError } = useAuth();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      await openTicket(token, { message, category: "other" });
      setMessage("");
      setDone(true);
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Le signalement n'a pas pu être envoyé."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="doc-page">
      <PageIntro kicker="Aide" title="Signaler">
        Un problème de paiement, de livraison ou de compte. Le message ouvre un ticket dans ta messagerie.
      </PageIntro>
      {customer ? (
        <form className="doc-form" onSubmit={(event) => void submit(event)}>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            minLength={8}
            maxLength={2000}
            rows={5}
            required
            placeholder="Décris ce qui s'est passé."
          />
          {error ? <small className="form-error">{error}</small> : null}
          {done ? <p className="account-muted">Signalement envoyé. La suite est dans la messagerie.</p> : null}
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "Envoi…" : "Envoyer"}
          </button>
        </form>
      ) : (
        <Link className="button button-primary" to={withNext(ROUTES.login, ROUTES.report)}>
          Se connecter pour signaler
        </Link>
      )}
    </section>
  );
}

const TICKET_STATUS: Record<string, string> = {
  open: "Ouvert",
  pending: "En cours",
  answered: "Répondu",
  closed: "Fermé",
  resolved: "Résolu",
};

function closed(status: string) {
  return status === "closed" || status === "resolved";
}

export function MessengerPage() {
  const { customer, token, handleError } = useAuth();
  const [view, setView] = useState<"client" | "admin">("client");
  const [tickets, setTickets] = useState<AccountTicket[] | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    fetchTickets(token, controller.signal)
      .then((result) => {
        setTickets(result.tickets);
        setActiveId((current) => current ?? result.tickets[0]?.id ?? null);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        handleError(reason);
        setError(errorMessage(reason, "Impossible de charger la messagerie."));
      });
    return () => controller.abort();
  }, [token, attempt, handleError]);

  const active = tickets?.find((ticket) => ticket.id === activeId) ?? null;

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!token || !draft.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (active && !closed(active.status)) {
        await replyToTicket(token, { ticket_id: active.id, message: draft.trim() });
      } else {
        const created = await openTicket(token, { message: draft.trim(), category: "order" });
        setActiveId(created.ticket.id);
      }
      setDraft("");
      setAttempt((value) => value + 1);
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Le message n'a pas pu être envoyé."));
    } finally {
      setBusy(false);
    }
  }

  if (!customer) {
    return (
      <section className="doc-page">
        <PageIntro kicker="Messages" title="Messagerie">
          Connecte-toi pour écrire au support et lire les réponses.
        </PageIntro>
        <Link className="button button-primary" to={withNext(ROUTES.login, ROUTES.messenger)}>
          Connexion
        </Link>
      </section>
    );
  }

  return (
    <section className="doc-page">
      <PageIntro kicker="Messages" title="Messagerie">
        {view === "client"
          ? "Tes échanges avec le support. Une réponse apparaît dans le fil."
          : "Les réponses officielles partent de la console admin. Ici tu vois tes fils tels que le support les reçoit."}
      </PageIntro>
      <div className="messenger-switch" role="group" aria-label="Vue de la messagerie">
        <button type="button" className={view === "client" ? "active" : ""} onClick={() => setView("client")}>
          Vue client
        </button>
        <button type="button" className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}>
          Vue admin
        </button>
        <a href="/admin">Ouvrir la console</a>
      </div>
      <div className={`messenger${view === "admin" ? " messenger-admin" : ""}`}>
        <ul className="messenger-list">
          {(tickets ?? []).map((ticket) => (
            <li key={ticket.id}>
              <button type="button" className={ticket.id === activeId ? "active" : ""} onClick={() => setActiveId(ticket.id)}>
                <strong>Ticket #{ticket.id}</strong>
                <span>{TICKET_STATUS[ticket.status] || ticket.status}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="messenger-thread">
          {!tickets ? <p>Chargement…</p> : active ? (
            <ul>
              {active.messages.map((entry) => (
                <li key={entry.id} className={entry.sender === "admin" ? "from-support" : "from-client"}>
                  <small>{entry.sender === "admin" ? "Support" : view === "admin" ? customer.name : "Toi"}</small>
                  <p>{entry.content}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p>Aucun ticket. Écris le premier message.</p>
          )}
          {view === "client" ? (
            <form onSubmit={(event) => void send(event)}>
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={active && !closed(active.status) ? "Répondre…" : "Nouveau message…"}
                maxLength={2000}
              />
              <button type="submit" className="button button-primary" disabled={busy || !draft.trim()}>
                Envoyer
              </button>
            </form>
          ) : (
            <a className="button button-primary" href="/admin">
              Répondre dans la console
            </a>
          )}
          {error ? <small className="form-error">{error}</small> : null}
        </div>
      </div>
    </section>
  );
}
