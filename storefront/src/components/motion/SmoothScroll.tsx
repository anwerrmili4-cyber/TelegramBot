import { useEffect, type ReactNode } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "@/lib/motion";
import "lenis/dist/lenis.css";

gsap.registerPlugin(ScrollTrigger);

const NAVIGATE_EVENT = "storefront:navigate";

let activeLenis: Lenis | null = null;

function jumpTo(node: HTMLElement | null) {
  if (activeLenis) {
    if (node) activeLenis.scrollTo(node, { immediate: true, force: true });
    else activeLenis.scrollTo(0, { immediate: true, force: true });
    return;
  }
  if (node) node.scrollIntoView();
  else window.scrollTo({ top: 0 });
}

/** Scroll to an element with Lenis so a native scrollIntoView is not overwritten mid-flight. */
export function scrollToElement(node: HTMLElement, { block = "start" }: { block?: "start" | "center" } = {}) {
  if (activeLenis) {
    const offset = block === "center" ? -(window.innerHeight - node.offsetHeight) / 2 : 0;
    activeLenis.scrollTo(node, { offset, force: true });
    return;
  }
  node.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block });
}

/** Jump with Lenis so a route change is not overwritten by an in-flight smooth scroll. */
export function scrollAfterNavigate(to: string) {
  const hash = to.split("#")[1] ?? "";
  jumpTo(null);
  if (!hash) return;
  // The next page is committed after this call, so the anchor exists on the following frame.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const node = document.getElementById(hash);
      if (node) jumpTo(node);
    });
  });
}

/**
 * One Lenis instance, driven by GSAP's ticker so ScrollTrigger stays in sync.
 * Reduced motion keeps the native scroll and does not start a second loop.
 */
export function SmoothScroll({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (prefersReducedMotion()) return;

    const lenis = new Lenis({
      autoRaf: false,
      lerp: 0.08,
      smoothWheel: true,
      stopInertiaOnNavigate: true,
      prevent: (node) => Boolean(node.closest(".overlay, .phone-menu, [data-lenis-prevent]")),
    });
    activeLenis = lenis;

    const onLenisScroll = () => {
      ScrollTrigger.update();
    };
    lenis.on("scroll", onLenisScroll);

    const tick = (time: number) => {
      lenis.raf(time * 1000);
    };
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    const onNavigate = () => {
      requestAnimationFrame(() => ScrollTrigger.refresh());
    };
    window.addEventListener(NAVIGATE_EVENT, onNavigate);

    const syncLock = () => {
      if (document.body.style.overflow === "hidden") lenis.stop();
      else lenis.start();
    };
    syncLock();
    const lockObserver = new MutationObserver(syncLock);
    lockObserver.observe(document.body, { attributes: true, attributeFilter: ["style"] });

    return () => {
      window.removeEventListener(NAVIGATE_EVENT, onNavigate);
      lockObserver.disconnect();
      lenis.off("scroll", onLenisScroll);
      if (activeLenis === lenis) activeLenis = null;
      gsap.ticker.remove(tick);
      gsap.ticker.lagSmoothing(500, 33);
      lenis.destroy();
    };
  }, []);

  return children;
}
