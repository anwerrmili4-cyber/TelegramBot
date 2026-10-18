import { useEffect } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import "lenis/dist/lenis.css";

gsap.registerPlugin(ScrollTrigger);

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export default function SmoothScroll({ children }) {
  useEffect(() => {
    if (window.matchMedia(REDUCED_MOTION_QUERY).matches) return undefined;

    const lenis = new Lenis({
      autoRaf: false,
      lerp: 0.08,
      smoothWheel: true,
      stopInertiaOnNavigate: true,
      prevent: (node) => Boolean(node.closest(
        ".nav-list, .search-results, .drawer-alerts, .form-dialog-body, .ai-chat-messages, [data-lenis-prevent]",
      )),
    });

    lenis.on("scroll", ScrollTrigger.update);

    const tick = (time) => {
      lenis.raf(time * 1000);
    };
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    const onNavigate = () => {
      lenis.scrollTo(0, { immediate: true, force: true });
      requestAnimationFrame(() => ScrollTrigger.refresh());
    };
    window.addEventListener("admin:navigate", onNavigate);

    return () => {
      window.removeEventListener("admin:navigate", onNavigate);
      lenis.off("scroll", ScrollTrigger.update);
      gsap.ticker.remove(tick);
      gsap.ticker.lagSmoothing(500, 33);
      lenis.destroy();
    };
  }, []);

  return children;
}
