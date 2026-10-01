import { Link, ROUTES } from "@/lib/router";

const COLUMNS = [
  {
    title: "Boutique",
    links: [
      ["Catalogue", ROUTES.shop],
      ["Catégories", ROUTES.categories],
      ["Offres", ROUTES.deals],
      ["Liste des prix", ROUTES.prices],
    ],
  },
  {
    title: "Aide",
    links: [
      ["Support", ROUTES.help],
      ["Messagerie", ROUTES.messenger],
      ["Contact", ROUTES.contact],
      ["Signaler", ROUTES.report],
      ["Communauté", ROUTES.community],
    ],
  },
  {
    title: "Infos",
    links: [
      ["Annonces", ROUTES.news],
      ["Conditions", ROUTES.terms],
      ["Confidentialité", ROUTES.privacy],
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-brand">
        <Link className="brand" to={ROUTES.home}>
          <img src="/logo.png" alt="" width="40" height="40" />
          <strong>BlackMarket</strong>
        </Link>
        <p>
          Services digitaux en dinar. Portefeuille rechargeable par D17, Flouci, IZI ou Wafa Cash. Accès
          livrés par email et conservés dans ton compte.
        </p>
      </div>
      {COLUMNS.map((column) => (
        <nav key={column.title} aria-label={column.title}>
          <h2>{column.title}</h2>
          <ul>
            {column.links.map(([label, to]) => (
              <li key={to}>
                <Link to={to}>{label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      ))}
    </footer>
  );
}
