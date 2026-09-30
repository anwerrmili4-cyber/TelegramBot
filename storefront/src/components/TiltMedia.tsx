import { useRef, type CSSProperties, type PointerEvent, type ReactNode } from "react";

type TiltMediaProps = {
  className?: string;
  children: ReactNode;
  /** Resting angles, in degrees, so the picture already reads as a 3D object. */
  restX?: number;
  restY?: number;
};

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Product picture that floats and leans toward the pointer. */
export function TiltMedia({ className, children, restX = 14, restY = -18 }: TiltMediaProps) {
  const ref = useRef<HTMLSpanElement>(null);

  function setTilt(x: number, y: number) {
    const node = ref.current;
    if (!node) return;
    node.style.setProperty("--tilt-x", `${x}deg`);
    node.style.setProperty("--tilt-y", `${y}deg`);
  }

  function onPointerMove(event: PointerEvent<HTMLSpanElement>) {
    if (reducedMotion()) return;
    const node = ref.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    setTilt(restX - py * 18, restY + px * 22);
  }

  return (
    <span
      ref={ref}
      className={className ? `tilt-media ${className}` : "tilt-media"}
      style={{ "--tilt-x": `${restX}deg`, "--tilt-y": `${restY}deg` } as CSSProperties}
      onPointerMove={onPointerMove}
      onPointerLeave={() => setTilt(restX, restY)}
    >
      {children}
    </span>
  );
}
