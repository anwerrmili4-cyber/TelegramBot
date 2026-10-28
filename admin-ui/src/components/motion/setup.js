import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function motionDuration(seconds) {
  if (typeof window === "undefined") return 0;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches ? 0 : seconds;
}
