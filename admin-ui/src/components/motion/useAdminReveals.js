import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import "./setup.js";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const ROW_SELECTOR = "tbody tr, .alert-card, .workspace-task, .launcher-card";

export function useAdminReveals(signature) {
  const root = useRef(null);

  useGSAP(() => {
    const scope = root.current;
    if (!scope || window.matchMedia(REDUCED_MOTION_QUERY).matches) return undefined;

    const rows = gsap.utils.toArray(ROW_SELECTOR, scope).slice(0, 12);
    const timeline = gsap.timeline({ defaults: { ease: "power2.out", overwrite: "auto" } });
    timeline.fromTo(scope, { y: 8, autoAlpha: 0 }, {
      y: 0,
      autoAlpha: 1,
      duration: 0.28,
      clearProps: "transform,opacity,visibility",
    });
    if (rows.length) {
      timeline.fromTo(rows, { y: 6, autoAlpha: 0 }, {
        y: 0,
        autoAlpha: 1,
        duration: 0.22,
        stagger: 0.03,
        clearProps: "transform,opacity,visibility",
      }, 0.04);
    }
    return undefined;
  }, { scope: root, dependencies: [signature], revertOnUpdate: true });

  return root;
}
