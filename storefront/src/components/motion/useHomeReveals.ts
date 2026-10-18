import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { prefersReducedMotion } from "@/lib/motion";

gsap.registerPlugin(ScrollTrigger, useGSAP);

/** Fade and rise homepage blocks once as they enter. Tiles keep their own entrance. */
export function useHomeReveals(signature: string) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const scope = root.current;
      if (!scope || prefersReducedMotion()) return;

      const sections = gsap.utils.toArray<HTMLElement>(".home-block, .steps", scope);
      const animated = new Map<HTMLElement, HTMLElement[]>();
      sections.forEach((section) => {
        const blocks = section.querySelectorAll<HTMLElement>(
          ":scope > h2, :scope > p, :scope > .section-head, :scope > .home-more, :scope > div:not(.tile-grid):not(.cat-grid)",
        );
        const cards = section.querySelectorAll<HTMLElement>(
          ":scope > .cat-grid > .cat-card, :scope > .steps-grid > li, :scope > details",
        );
        const nodes = [...blocks, ...cards];
        if (!nodes.length) return;
        animated.set(section, nodes);

        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: section,
            start: "top 88%",
            once: true,
          },
        });
        if (blocks.length) {
          timeline.fromTo(
            blocks,
            { y: 28, opacity: 0 },
            { y: 0, opacity: 1, duration: 0.9, ease: "power2.out", stagger: 0.05 },
          );
        }
        if (cards.length) {
          timeline.fromTo(
            cards,
            { y: 28, opacity: 0 },
            { y: 0, opacity: 1, duration: 0.9, ease: "power2.out", stagger: 0.06 },
            blocks.length ? "-=0.55" : 0,
          );
        }
      });

      const onFocus = (event: FocusEvent) => {
        const section = (event.target as HTMLElement | null)?.closest<HTMLElement>(".home-block, .steps");
        const nodes = section ? animated.get(section) : undefined;
        if (!section || !nodes?.length) return;
        // A paused ScrollTrigger keeps the hidden start state and would overwrite a competing tween.
        ScrollTrigger.getAll().forEach((trigger) => {
          if (trigger.trigger === section) trigger.kill();
        });
        gsap.killTweensOf(nodes);
        gsap.set(nodes, { y: 0, opacity: 1 });
      };
      scope.addEventListener("focusin", onFocus);

      let frame = 0;
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => ScrollTrigger.refresh());
      });
      observer.observe(scope);

      return () => {
        cancelAnimationFrame(frame);
        observer.disconnect();
        scope.removeEventListener("focusin", onFocus);
      };
    },
    { scope: root, dependencies: [signature], revertOnUpdate: true },
  );

  return root;
}
