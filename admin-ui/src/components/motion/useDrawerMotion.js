import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import "./setup.js";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function useDrawerMotion(asideRef, backdropRef, open) {
  useGSAP(() => {
    const aside = asideRef.current;
    const backdrop = backdropRef.current;
    if (!aside || !backdrop) return undefined;

    const reduce = window.matchMedia(REDUCED_MOTION_QUERY).matches;
    const mm = gsap.matchMedia();

    mm.add("(min-width: 901px)", () => {
      gsap.set(aside, { clearProps: "transform,visibility,opacity" });
      gsap.set(backdrop, { autoAlpha: 0 });
    });

    mm.add("(max-width: 900px)", () => {
      const duration = reduce ? 0 : (open ? 0.28 : 0.2);
      if (open) {
        gsap.set(aside, { visibility: "visible" });
        gsap.fromTo(aside, { xPercent: -100 }, {
          xPercent: 0,
          duration,
          ease: "power2.out",
          overwrite: "auto",
        });
        gsap.to(backdrop, { autoAlpha: 1, duration, overwrite: "auto" });
        return undefined;
      }
      gsap.set(aside, { visibility: "visible" });
      gsap.to(aside, {
        xPercent: -100,
        duration,
        ease: "power2.in",
        overwrite: "auto",
        onComplete: () => gsap.set(aside, { visibility: "hidden" }),
      });
      gsap.to(backdrop, { autoAlpha: 0, duration, overwrite: "auto" });
      return undefined;
    });

    return () => mm.revert();
  }, { dependencies: [open] });
}
