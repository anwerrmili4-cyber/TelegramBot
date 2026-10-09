import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { GoogleButton } from "@/components/GoogleButton";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage } from "@/lib/api";
import { Link, navigate, nextPath, ROUTES, withNext } from "@/lib/router";
import { AuthLayout, EMAIL_PATTERN, MIN_PASSWORD_LENGTH, PasswordField } from "@/pages/AuthLayout";
import { verifyEmailPath } from "@/pages/VerifyEmailPage";

export function RegisterPage() {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function validationError(): string {
    if (name.trim().length < 2) return "Saisis ton nom complet.";
    if (!EMAIL_PATTERN.test(email.trim())) return "Saisis une adresse email valide.";
    if (password.length < MIN_PASSWORD_LENGTH) {
      return `Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`;
    }
    if (password !== confirmation) return "Les deux mots de passe ne correspondent pas.";
    return "";
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const problem = validationError();
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await register(name.trim(), email.trim(), password);
      navigate(verifyEmailPath(email.trim().toLowerCase(), nextPath()), { replace: true });
    } catch (reason) {
      setError(errorMessage(reason, "Impossible de créer le compte."));
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      kicker="Inscription"
      title="Créer un compte"
      intro="Un compte est nécessaire pour accéder au site. Cela prend quelques secondes, puis tu retrouves tes achats et ton portefeuille."
      footer={
        <>
          Déjà inscrit ? <Link to={withNext(ROUTES.login, nextPath())}>Se connecter</Link>
        </>
      }
    >
      <GoogleButton context="signup" />
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <label>
          Nom complet
          <input
            required
            name="name"
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Ex. Amine Ben Salah"
          />
        </label>

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
          {submitting ? "Création…" : "Créer mon compte"}
          {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
        </button>
      </form>
    </AuthLayout>
  );
}
