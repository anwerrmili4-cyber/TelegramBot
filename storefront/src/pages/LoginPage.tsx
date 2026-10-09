import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { GoogleButton } from "@/components/GoogleButton";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, errorMessage } from "@/lib/api";
import { Link, navigate, nextPath, ROUTES, withNext } from "@/lib/router";
import { AuthLayout, EMAIL_PATTERN, PasswordField } from "@/pages/AuthLayout";
import { verifyEmailPath } from "@/pages/VerifyEmailPage";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Saisis une adresse email valide.");
      return;
    }
    if (!password) {
      setError("Saisis ton mot de passe.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate(nextPath(), { replace: true });
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "email_unverified") {
        navigate(verifyEmailPath(email.trim().toLowerCase(), nextPath()));
        return;
      }
      setError(errorMessage(reason, "Connexion impossible."));
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      kicker="Mon compte"
      title="Connexion"
      intro="Connecte-toi pour accéder au site, à tes commandes et à ton portefeuille."
      footer={
        <>
          Pas encore de compte ? <Link to={withNext(ROUTES.register, nextPath())}>Créer un compte</Link>
        </>
      }
    >
      <GoogleButton />
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

        <PasswordField
          label="Mot de passe"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />

        <Link className="auth-inline-link" to={ROUTES.forgotPassword}>
          Mot de passe oublié ?
        </Link>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Connexion…" : "Se connecter"}
          {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
        </button>
      </form>
    </AuthLayout>
  );
}
