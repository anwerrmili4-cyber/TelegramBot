const STEPS = [
  {
    title: "Remplis ton panier",
    body: "Choisis autant de services que tu veux. Le prix, le stock et la durée affichés sont ceux du moment.",
  },
  {
    title: "Paie le total en dinar",
    body: "Un seul règlement D17 ou Flouci pour l'ensemble du panier, au montant exact indiqué.",
  },
  {
    title: "Envoie ton reçu",
    body: "WhatsApp s'ouvre avec ta référence. Joins le justificatif : on vérifie puis on livre.",
  },
];

export function HowItWorks() {
  return (
    <section className="steps" id="fonctionnement" aria-labelledby="steps-title">
      <div className="section-head">
        <div>
          <span className="kicker">Simple et transparent</span>
          <h2 id="steps-title">Trois étapes, aucune surprise.</h2>
        </div>
        <p>
          Aucun paiement n'est validé automatiquement : c'est un contrôle humain qui déclenche la
          livraison.
        </p>
      </div>
      <ol className="steps-grid">
        {STEPS.map((step, index) => (
          <li key={step.title}>
            <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
