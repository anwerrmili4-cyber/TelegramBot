import { useEffect, useRef, type ComponentType } from "react";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import { ROUTES, navigate, usePathname, withNext } from "@/lib/router";
import { trackVisit } from "@/lib/track";

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
 * Full-screen registration window. It cannot be dismissed: there is no close
 * control, Escape does nothing, and any other address is replaced by the
 * inscription page. Login, email verification and password recovery stay
 * reachable because they are how an account is opened.
 */
export function SignupGate() {
  const path = usePathname();
  const windowRef = useRef<HTMLDivElement>(null);
  const Page = ACCOUNT_FLOW[path] ?? RegisterPage;

  useEffect(() => {
    try {
      sessionStorage.setItem("bm-intro-seen", "1");
    } catch {
      // The intro simply stays skipped for this visit.
    }
  }, []);

  useEffect(() => {
    trackVisit(isAccountFlow(path) ? path : ROUTES.register);
  }, [path]);

  useEffect(() => {
    // Read the address bar, not the render path: this effect can run twice
    // before the redirected path is rendered, and must not wrap `next` again.
    const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
    if (isAccountFlow(pathname)) return;
    const here = `${pathname}${window.location.search}`;
    const safe = here.startsWith("/") && !here.startsWith("//") ? here : ROUTES.home;
    navigate(withNext(ROUTES.register, safe), { replace: true });
  }, [path]);

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
