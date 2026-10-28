import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { motionDuration } from "./setup.js";

export function NavCount({ value }) {
  const ref = useRef(null);
  const current = useRef(0);

  useGSAP(() => {
    const node = ref.current;
    if (!node) return undefined;
    const proxy = { n: current.current };
    gsap.to(proxy, {
      n: value,
      duration: motionDuration(0.4),
      ease: "power1.out",
      overwrite: "auto",
      onUpdate: () => {
        node.textContent = String(Math.round(proxy.n));
      },
    });
    current.current = value;
    return undefined;
  }, { dependencies: [value] });

  if (!value) return null;
  return <small ref={ref}>{value}</small>;
}
