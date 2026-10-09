import { useEffect, useRef, type ComponentType } from "react";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import { ROUTES, usePathname } from "@/lib/router";

/** How long the homepage stays usable after the intro, before the window opens. */
export const SIGNUP_BROWSE_MS = 5000;

const LOCK_KEY = "bm-signup-lock";

/** True once the window has opened in this tab, so a refresh does not give another free look. */
export function signupLockPending(): boolean {
  try {
    return sessionStorage.getItem(LOCK_KEY) === "1";
  } catch {
    return false;
  }
}

export function rememberSignupLock(): void {
  try {
    sessionStorage.setItem(LOCK_KEY, "1");
  } catch {
    // The short look is offered again on the next visit.
  }
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Pages that belong to creating or recovering an account. Everything else stays locked. */
const ACCOUNT_FLOW: Record<string, ComponentType> = {
  [ROUTES.login]: LoginPage,
  [ROUTES.register]: RegisterPage,
  [ROUTES.verifyEmail]: VerifyEmailPage,
  [ROUTES.forgotPassword]: ForgotPasswordPage,
  [ROUTES.resetPassword]: ResetPasswordPage,
};

export function isAccountFlow(path: string): boolean {
  return Object.prototype.hasOwnProperty.call(ACCOUNT_FLOW, path);
}

/**
 * Registration window over the site. It cannot be dismissed: there is no close
 * control and Escape does nothing. Login, email verification and password
 * recovery stay inside the window, because that is how an account is opened.
 */
export function SignupGate() {
  const path = usePathname();
  const windowRef = useRef<HTMLDivElement>(null);
  const Page = ACCOUNT_FLOW[path] ?? RegisterPage;

  useEffect(() => {
    const root = windowRef.current;
    if (!root) return;
    const items = () =>
      [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((element) => element.offsetParent !== null);
    items().find((element) => element.tagName === "INPUT")?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.key !== "Tab") return;
      const targets = items();
      if (!targets.length) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [path]);

  return (
    <div className="signup-gate">
      <div
        ref={windowRef}
        className="signup-window"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
      >
        <div className="signup-brand">
          <img src="/logo.png" alt="" width="44" height="44" />
          <div>
            <strong>BlackMarket</strong>
            <span>Tunisie</span>
          </div>
        </div>
        <Page />
      </div>
    </div>
  );
}
