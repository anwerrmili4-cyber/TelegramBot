import { useId, useState, type ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";

type AuthLayoutProps = {
  kicker: string;
  title: string;
  intro?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
};

export function AuthLayout({ kicker, title, intro, children, footer }: AuthLayoutProps) {
  return (
    <section className="auth-page">
      <div className="auth-card">
        <header className="auth-head">
          <span className="kicker">{kicker}</span>
          <h1>{title}</h1>
          {intro ? <p>{intro}</p> : null}
        </header>
        {children}
        {footer ? <footer className="auth-foot">{footer}</footer> : null}
      </div>
    </section>
  );
}

type PasswordFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  hint?: string;
  name?: string;
};

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  hint,
  name = "password",
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const hintId = useId();
  return (
    <label>
      {label}
      <span className="password-field">
        <input
          required
          name={name}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? hintId : undefined}
        />
        <button
          type="button"
          onClick={() => setVisible((shown) => !shown)}
          aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
          aria-pressed={visible}
        >
          {visible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
        </button>
      </span>
      {hint ? <small id={hintId}>{hint}</small> : null}
    </label>
  );
}

export const MIN_PASSWORD_LENGTH = 8;
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
