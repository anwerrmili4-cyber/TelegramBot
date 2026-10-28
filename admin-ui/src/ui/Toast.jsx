import { useEffect, useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { AlertTriangle, CheckCheck, X } from "lucide-react";
import "../components/motion/setup.js";

export function Toast({ toast, onClose }) {
  const rootRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const timerRef = useRef(0);
  onCloseRef.current = onClose;

  const dismiss = () => {
    window.clearTimeout(timerRef.current);
    const node = rootRef.current?.querySelector(".shell-toast");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!node || reduce) {
      onCloseRef.current();
      return;
    }
    gsap.to(node, {
      y: -8,
      autoAlpha: 0,
      duration: 0.18,
      ease: "power1.in",
      overwrite: "auto",
      onComplete: () => onCloseRef.current(),
    });
  };

  useGSAP(() => {
    if (!toast) return undefined;
    const node = rootRef.current?.querySelector(".shell-toast");
    const bar = rootRef.current?.querySelector(".shell-toast-progress");
    if (!node) return undefined;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    gsap.fromTo(node, { y: reduce ? 0 : 8, autoAlpha: reduce ? 1 : 0 }, {
      y: 0,
      autoAlpha: 1,
      duration: reduce ? 0 : 0.22,
      ease: "power2.out",
      overwrite: "auto",
    });
    if (bar && !reduce) {
      gsap.fromTo(bar, { scaleX: 1 }, {
        scaleX: 0,
        duration: 4.2,
        ease: "none",
        transformOrigin: "left center",
        overwrite: "auto",
      });
    }
    return undefined;
  }, { dependencies: [toast], scope: rootRef, revertOnUpdate: true });

  useEffect(() => {
    if (!toast) return undefined;
    timerRef.current = window.setTimeout(dismiss, 4200);
    return () => window.clearTimeout(timerRef.current);
  }, [toast]);

  if (!toast) return null;
  const type = toast.type === "error" || toast.type === "warning" ? toast.type : "success";
  const Icon = type === "success" ? CheckCheck : AlertTriangle;

  return (
    <div className="shell-toast-stage" ref={rootRef}>
      <div className={`shell-toast is-${type}`} role={type === "error" ? "alert" : "status"} aria-live={type === "error" ? "assertive" : "polite"} aria-atomic="true">
        <span className="shell-toast-icon" aria-hidden="true"><Icon size={18} strokeWidth={2.25} /></span>
        <div className="shell-toast-copy">
          <strong>{toast.title}</strong>
          {toast.message ? <small>{toast.message}</small> : null}
        </div>
        <button type="button" onClick={dismiss} aria-label="Ignorer la notification">
          <X size={16} />
        </button>
        <i className="shell-toast-progress" aria-hidden="true" />
      </div>
    </div>
  );
}
