import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import "./setup.js";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function useNavIndicator(navRef, signature) {
  useGSAP(() => {
    const nav = navRef.current;
    const indicator = nav?.querySelector(".nav-indicator");
    if (!nav || !indicator) return undefined;

    const place = () => {
      const active = nav.querySelector(".nav-item.active");
      if (!active) {
        gsap.set(indicator, { autoAlpha: 0 });
        return;
      }
      const y = active.getBoundingClientRect().top - nav.getBoundingClientRect().top + nav.scrollTop + (active.offsetHeight - 20) / 2;
      const reduce = window.matchMedia(REDUCED_MOTION_QUERY).matches;
      gsap.to(indicator, {
        y,
        autoAlpha: 1,
        duration: reduce ? 0 : 0.28,
        ease: "power2.out",
        overwrite: "auto",
      });
    };

    place();
    const observer = new ResizeObserver(() => place());
    observer.observe(nav);
    return () => observer.disconnect();
  }, { dependencies: [signature], scope: navRef });
}
