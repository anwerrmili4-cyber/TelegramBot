import { useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { motionDuration } from "../components/motion/setup.js";

function focusable(node) {
  if (!node) return [];
  return [...node.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")]
    .filter((element) => !element.disabled && element.getAttribute("aria-hidden") !== "true");
}

export function Dialog({
  onClose,
  label,
  labelledBy,
  describedBy,
  role = "dialog",
  motion = "pop",
  className = "",
  backdropClassName = "",
  onKeyDown,
  children,
}) {
  const backdropRef = useRef(null);
  const panelRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useLayoutEffect(() => {
    const previous = document.activeElement;
    const panel = panelRef.current;
    const preferred = panel?.querySelector("[data-autofocus]") || focusable(panel)[0];
    preferred?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = focusable(panel);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  useGSAP(() => {
    const panel = panelRef.current;
    const backdrop = backdropRef.current;
    if (!panel || !backdrop) return undefined;
    const duration = motionDuration(0.24);
    gsap.fromTo(backdrop, { autoAlpha: 0 }, { autoAlpha: 1, duration, overwrite: "auto" });
    gsap.fromTo(panel, motion === "drawer" ? { x: 24, autoAlpha: 0 } : { y: 8, autoAlpha: 0 }, {
      x: 0,
      y: 0,
      autoAlpha: 1,
      duration,
      ease: "power2.out",
      overwrite: "auto",
      clearProps: "transform,opacity,visibility",
    });
    return undefined;
  }, { scope: backdropRef });

  return (
    <div
      ref={backdropRef}
      className={`shell-backdrop ${backdropClassName}`.trim()}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <section
        ref={panelRef}
        className={className}
        role={role}
        aria-modal="true"
        aria-label={labelledBy ? undefined : label}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        {children}
      </section>
    </div>
  );
}
