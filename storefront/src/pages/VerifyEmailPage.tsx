import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, resendVerificationCode } from "@/lib/api";
import { Link, navigate, ROUTES } from "@/lib/router";
import { AuthLayout } from "@/pages/AuthLayout";

const RESEND_COOLDOWN_SECONDS = 60;

export function verifyEmailPath(email: string): string {
  return `${ROUTES.verifyEmail}?email=${encodeURIComponent(email)}`;
}

export function VerifyEmailPage() {
  const { verifyEmail } = useAuth();
  const [email] = useState(() => new URLSearchParams(window.location.search).get("email") ?? "");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (code.length !== 6) {
      setError("Saisis les 6 chiffres reçus par email.");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await verifyEmail(email, code);
      navigate(ROUTES.home, { replace: true });
    } catch (reason) {
      setError(errorMessage(reason, "Impossible de vérifier le code."));
      setSubmitting(false);
    }
  }

  async function onResend() {
    setError("");
    setNotice("");
    setCooldown(RESEND_COOLDOWN_SECONDS);
    try {
      await resendVerificationCode(email);
      setCode("");
      setNotice("Un nouveau code vient d'être envoyé.");
    } catch (reason) {
      setError(errorMessage(reason, "Impossible d'envoyer un nouveau code."));
    }
  }

  if (!email) {
    return (
      <AuthLayout
        kicker="Inscription"
        title="Lien incomplet"
        intro="Crée ton compte ou connecte-toi pour recevoir un code de vérification."
        footer={<Link to={ROUTES.register}>Créer un compte</Link>}
      />
    );
  }

  return (
    <AuthLayout
      kicker="Inscription"
      title="Confirme ton email"
      intro={
        <>
          Nous avons envoyé un code à 6 chiffres à <strong>{email}</strong>. Il expire dans 15 minutes.
        </>
      }
      footer={<Link to={ROUTES.login}>Retour à la connexion</Link>}
    >
      <form className="auth-form" onSubmit={onSubmit} noValidate>
        <label>
          Code de vérification
          <input
            required
            name="code"
            className="code-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="000000"
            autoFocus
          />
          <small>Pense à regarder dans les spams.</small>
        </label>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="auth-muted" role="status">
            {notice}
          </p>
        ) : null}

        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Vérification…" : "Confirmer"}
          {submitting ? null : <ArrowRight size={17} aria-hidden="true" />}
        </button>

        <button
          type="button"
          className="auth-inline-link"
          onClick={() => void onResend()}
          disabled={cooldown > 0}
        >
          {cooldown > 0 ? `Renvoyer le code (${cooldown} s)` : "Renvoyer le code"}
        </button>
      </form>
    </AuthLayout>
  );
}
