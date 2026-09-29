const STEPS = [
  {
    title: "Recharge ton portefeuille",
    body: "Envoie le montant de ton choix par D17, Flouci, IZI ou Wafa Cash, puis joins la référence et une capture du reçu.",
  },
  {
    title: "Achète en un clic",
    body: "Dès que la recharge est validée, paie ton panier avec ton solde. Tu peux aussi payer une commande directement par virement.",
  },
  {
    title: "Reçois tes accès",
    body: "Livraison immédiate quand le produit est en stock, par email et dans ton espace client, avec tout ton historique.",
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
          Chaque recharge et chaque reçu est contrôlé par un administrateur avant d'être crédité ou
          livré.
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
