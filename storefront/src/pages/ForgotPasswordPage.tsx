import { useState, type FormEvent } from "react";
import { ArrowRight, MailCheck } from "lucide-react";
import { errorMessage, requestPasswordReset } from "@/lib/api";
import { Link, ROUTES } from "@/lib/router";
import { AuthLayout, EMAIL_PATTERN } from "@/pages/AuthLayout";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [sentTo, setSentTo] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address)) {
      setError("Saisis une adresse email valide.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await requestPasswordReset(address);
      setSentTo(address);
    } catch (reason) {
      setError(errorMessage(reason, "Impossible d'envoyer le lien."));
    } finally {
      setSubmitting(false);
    }
  }

  const footer = (
    <>
      <Link to={ROUTES.login}>Retour à la connexion</Link>
    </>
  );

  if (sentTo) {
    return (
      <AuthLayout kicker="Mot de passe oublié" title="Vérifie ta boîte mail" footer={footer}>
        <div className="auth-success">
          <span className="success-mark">
            <MailCheck size={28} aria-hidden="true" />
          </span>
          <p>
            Si un compte existe pour <strong>{sentTo}</strong>, un lien de réinitialisation vient
            d'y être envoyé. Il reste valable une heure.
          </p>
          <p className="auth-muted">Pense à regarder dans les spams.</p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      kicker="Mot de passe oublié"
      title="Réinitialiser"
      intro="Saisis l'email de ton compte, on t'envoie un lien pour choisir un nouveau mot de passe."
      footer={footer}
    >
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <label>
          Adresse email
          <input
            required
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="toi@exemple.com"
          />
        </label>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Envoi…" : "Envoyer le lien"}
          {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
        </button>
      </form>
    </AuthLayout>
  );
}
