/** Place a shared pill on `active`, measured from `container`'s padding edge. */
export function placeSlidingPill(container: HTMLElement, active: HTMLElement | null) {
  if (!active || active.offsetWidth === 0) {
    delete container.dataset.pill;
    return;
  }

  let x = 0;
  let y = 0;
  let node: HTMLElement | null = active;
  while (node && node !== container) {
    x += node.offsetLeft;
    y += node.offsetTop;
    const parent: Element | null = node.offsetParent;
    node = parent instanceof HTMLElement ? parent : null;
  }

  container.style.setProperty("--pill-x", `${x}px`);
  container.style.setProperty("--pill-y", `${y}px`);
  container.style.setProperty("--pill-w", `${active.offsetWidth}px`);
  container.style.setProperty("--pill-h", `${active.offsetHeight}px`);
  container.dataset.pill = "ready";
}
