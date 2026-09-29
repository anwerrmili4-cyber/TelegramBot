import type { CSSProperties } from "react";

/** Feeds `--index` to the CSS cascade so lists animate in sequence. */
export function stagger(index: number): CSSProperties {
  return { "--index": index } as CSSProperties;
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

type DocumentWithViewTransition = Document & {
  startViewTransition?: (callback: () => void) => { finished: Promise<void> };
};

/**
 * Run a state update inside a View Transition so the catalog morphs between
 * filters instead of snapping. Browsers without the API just apply the update.
 */
export function withViewTransition(update: () => void): void {
  const { startViewTransition } = document as DocumentWithViewTransition;
  if (!startViewTransition || prefersReducedMotion()) {
    update();
    return;
  }
  startViewTransition.call(document, update);
}
