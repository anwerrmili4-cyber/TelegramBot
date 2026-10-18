import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const REVEAL_SELECTOR = ".page-heading, section, article, .panel, .data-panel";

function outermostBlocks(scope) {
  const candidates = [...scope.querySelectorAll(REVEAL_SELECTOR)];
  return candidates.filter((node) => {
    const parentBlock = node.parentElement?.closest(REVEAL_SELECTOR);
    return !parentBlock || !scope.contains(parentBlock);
  });
}

export function useAdminReveals(signature) {
  const root = useRef(null);

  useGSAP(
    () => {
      const scope = root.current;
      if (!scope || window.matchMedia(REDUCED_MOTION_QUERY).matches) return undefined;

      const animated = new Map();
      outermostBlocks(scope).forEach((node) => {
        const tween = gsap.fromTo(
          node,
          { y: 18, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            duration: 0.58,
            ease: "power2.out",
            clearProps: "transform,opacity",
            scrollTrigger: {
              trigger: node,
              start: "top 92%",
              once: true,
            },
          },
        );
        animated.set(node, tween);
      });

      const revealFocusedBlock = (event) => {
        const block = event.target.closest?.(REVEAL_SELECTOR);
        const tween = block ? animated.get(block) : null;
        if (!block || !tween) return;
        tween.scrollTrigger?.kill();
        tween.kill();
        gsap.set(block, { y: 0, opacity: 1, clearProps: "transform,opacity" });
      };
      scope.addEventListener("focusin", revealFocusedBlock);

      let refreshFrame = 0;
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(refreshFrame);
        refreshFrame = requestAnimationFrame(() => ScrollTrigger.refresh());
      });
      observer.observe(scope);

      return () => {
        cancelAnimationFrame(refreshFrame);
        observer.disconnect();
        scope.removeEventListener("focusin", revealFocusedBlock);
      };
    },
    { scope: root, dependencies: [signature], revertOnUpdate: true },
  );

  return root;
}
