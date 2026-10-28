import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { motionDuration } from "../components/motion/setup.js";

export function Skeleton({ label = "Chargement du centre de contrôle…" }) {
  const ref = useRef(null);

  useGSAP(() => {
    const duration = motionDuration(0.9);
    if (!duration) return undefined;
    gsap.fromTo(".shell-skeleton-bar", { opacity: 0.45 }, {
      opacity: 1,
      duration,
      yoyo: true,
      repeat: -1,
      stagger: 0.06,
      ease: "sine.inOut",
    });
    return undefined;
  }, { scope: ref });

  return (
    <div className="shell-skeleton" ref={ref} role="status" aria-live="polite" aria-busy="true">
      <span className="shell-sr-only">{label}</span>
      <div className="shell-skeleton-bar is-title" />
      <div className="shell-skeleton-bar" />
      <div className="shell-skeleton-grid">
        <div className="shell-skeleton-bar is-card" />
        <div className="shell-skeleton-bar is-card" />
        <div className="shell-skeleton-bar is-card" />
      </div>
    </div>
  );
}
