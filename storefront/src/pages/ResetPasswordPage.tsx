import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, BadgeCheck } from "lucide-react";
import { errorMessage, resetPassword } from "@/lib/api";
import { Link, ROUTES } from "@/lib/router";
import { AuthLayout, MIN_PASSWORD_LENGTH, PasswordField } from "@/pages/AuthLayout";

export function ResetPasswordPage() {
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  // Keep the one-time token out of the history and any link shared afterwards.
  useEffect(() => {
    if (window.location.search) {
      window.history.replaceState(null, "", ROUTES.resetPassword);
    }
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`);
      return;
    }
    if (password !== confirmation) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (reason) {
      setError(errorMessage(reason, "Impossible de changer le mot de passe."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout
        kicker="Mot de passe oublié"
        title="Lien incomplet"
        intro="Ce lien de réinitialisation est incomplet. Ouvre le lien reçu par email ou demandes-en un nouveau."
        footer={<Link to={ROUTES.forgotPassword}>Demander un nouveau lien</Link>}
      />
    );
  }

  if (done) {
    return (
      <AuthLayout kicker="Mot de passe oublié" title="Mot de passe modifié">
        <div className="auth-success">
          <span className="success-mark">
            <BadgeCheck size={28} aria-hidden="true" />
          </span>
          <p>Ton nouveau mot de passe est enregistré. Tes autres sessions ont été déconnectées.</p>
          <Link className="button button-primary button-block" to={ROUTES.login}>
            Se connecter <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      kicker="Mot de passe oublié"
      title="Nouveau mot de passe"
      intro="Choisis un mot de passe que tu n'utilises pas ailleurs."
      footer={<Link to={ROUTES.login}>Retour à la connexion</Link>}
    >
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <PasswordField
          label="Nouveau mot de passe"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint={`Au moins ${MIN_PASSWORD_LENGTH} caractères.`}
        />
        <PasswordField
          label="Confirmer le mot de passe"
          name="password_confirmation"
          value={confirmation}
          onChange={setConfirmation}
          autoComplete="new-password"
        />

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Enregistrement…" : "Enregistrer"}
          {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
        </button>
      </form>
    </AuthLayout>
  );
}
