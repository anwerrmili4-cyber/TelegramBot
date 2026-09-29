import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { prefersReducedMotion } from "@/lib/motion";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Safety net in case the exit animation never reports back. */
const EXIT_TIMEOUT = 500;

type OverlayState = "closed" | "open" | "closing";

type OverlayProps = {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  variant: "drawer" | "dialog";
  children: ReactNode;
};

/**
 * Modal surface shared by the cart drawer and the checkout dialog. It locks
 * background scrolling, closes on Escape or backdrop click, keeps Tab inside
 * the panel, and stays mounted through its exit animation so closing is
 * animated rather than abrupt.
 */
export function Overlay({ open, onClose, labelledBy, variant, children }: OverlayProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<OverlayState>(open ? "open" : "closed");

  useEffect(() => {
    setState((current) => (open ? "open" : current === "open" ? "closing" : "closed"));
  }, [open]);

  useEffect(() => {
    if (state !== "closing") return;
    const node = panel.current;
    if (!node || prefersReducedMotion()) {
      setState("closed");
      return;
    }
    const finish = () => setState("closed");
    node.addEventListener("animationend", finish);
    const timer = window.setTimeout(finish, EXIT_TIMEOUT);
    return () => {
      node.removeEventListener("animationend", finish);
      window.clearTimeout(timer);
    };
  }, [state]);

  useEffect(() => {
    if (state !== "open") return;

    const restoreFocusTo = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    panel.current?.focus({ preventScroll: true });

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const targets = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.offsetParent !== null,
      );
      if (!targets.length) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      restoreFocusTo?.focus({ preventScroll: true });
    };
  }, [state, onClose]);

  if (state === "closed") return null;

  return createPortal(
    <div className={`overlay overlay-${variant}`} data-state={state}>
      <div className="overlay-backdrop" onClick={onClose} />
      <div
        className="overlay-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        ref={panel}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
