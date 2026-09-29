import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { errorMessage, fetchAuthConfig } from "@/lib/api";
import { navigate, nextPath } from "@/lib/router";

type GoogleCredential = { credential: string };

type GoogleIdentity = {
  accounts: {
    id: {
      initialize: (options: {
        client_id: string;
        callback: (response: GoogleCredential) => void;
        ux_mode?: "popup";
        context?: "signin" | "signup";
      }) => void;
      renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

const SCRIPT_URL = "https://accounts.google.com/gsi/client";
let clientIdPromise: Promise<string> | null = null;
let scriptPromise: Promise<GoogleIdentity> | null = null;

function googleClientId(): Promise<string> {
  clientIdPromise ??= fetchAuthConfig()
    .then((config) => config.google_client_id || "")
    .catch(() => {
      clientIdPromise = null;
      return "";
    });
  return clientIdPromise;
}

function loadGoogle(): Promise<GoogleIdentity> {
  scriptPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts) {
      resolve(window.google);
      return;
    }
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => (window.google ? resolve(window.google) : reject(new Error("google")));
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error("google"));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

/** "Continuer avec Google", shown only when the server has a Google client id. */
export function GoogleButton({ context = "signin" }: { context?: "signin" | "signup" }) {
  const { loginWithGoogle } = useAuth();
  const target = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const clientId = await googleClientId();
      if (!clientId || cancelled) return;
      const google = await loadGoogle().catch(() => null);
      if (!google || cancelled || !target.current) return;
      google.accounts.id.initialize({
        client_id: clientId,
        ux_mode: "popup",
        context,
        callback: async ({ credential }) => {
          setBusy(true);
          setError("");
          try {
            await loginWithGoogle(credential);
            navigate(nextPath(), { replace: true });
          } catch (reason) {
            setError(errorMessage(reason, "Connexion Google impossible."));
            setBusy(false);
          }
        },
      });
      google.accounts.id.renderButton(target.current, {
        type: "standard",
        theme: "filled_black",
        size: "large",
        shape: "pill",
        text: context === "signup" ? "signup_with" : "continue_with",
        locale: "fr",
        width: Math.max(200, Math.min(400, window.innerWidth - 72)),
      });
      setAvailable(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [context, loginWithGoogle]);

  return (
    <div className="google-auth" hidden={!available} aria-busy={busy}>
      <div ref={target} className="google-button" />
      {busy ? <p className="google-status">Connexion avec Google…</p> : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="auth-divider">
        <span>ou avec ton email</span>
      </div>
    </div>
  );
}
