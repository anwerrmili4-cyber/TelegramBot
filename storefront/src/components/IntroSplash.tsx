import { useEffect, useState, type CSSProperties } from "react";

const SEEN_KEY = "bm-intro-seen";
const NAME = "BLACKMARKET";
const HOLD_MS = 2900;
const REDUCED_HOLD_MS = 700;
const EXIT_FALLBACK_MS = 900;

function shouldPlay(): boolean {
  try {
    return !sessionStorage.getItem(SEEN_KEY);
  } catch {
    return true;
  }
}

function markSeen() {
  try {
    sessionStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Private mode: the intro simply plays again next visit.
  }
}

export function IntroSplash() {
  const [phase, setPhase] = useState<"playing" | "leaving" | "done">(() => (shouldPlay() ? "playing" : "done"));

  useEffect(() => {
    if (phase !== "playing") return;
    markSeen();
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(() => setPhase("leaving"), reduced ? REDUCED_HOLD_MS : HOLD_MS);
    const skip = () => setPhase("leaving");
    window.addEventListener("keydown", skip);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", skip);
      document.body.style.overflow = previousOverflow;
    };
  }, [phase]);

  // animationend is the normal exit; the timer covers browsers that skip it.
  useEffect(() => {
    if (phase !== "leaving") return;
    const timer = window.setTimeout(() => setPhase("done"), EXIT_FALLBACK_MS);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (phase === "done") return null;

  return (
    <div
      className="intro"
      data-phase={phase}
      aria-hidden="true"
      onClick={() => setPhase("leaving")}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget && phase === "leaving") setPhase("done");
      }}
    >
      <div className="intro-glow" />
      <div className="intro-stage">
        <div className="intro-logo">
          <span className="intro-ring" />
          <span className="intro-ring intro-ring-late" />
          <img src="/logo.png" alt="" width="168" height="168" />
        </div>
        <div className="intro-name">
          <span className="intro-word">
            {NAME.split("").map((letter, index) => (
              <span key={index} style={{ "--i": index } as CSSProperties}>
                {letter}
              </span>
            ))}
          </span>
          <span className="intro-line" />
          <span className="intro-tag">Tunisie</span>
        </div>
      </div>
      <p className="intro-skip">Touchez pour passer</p>
    </div>
  );
}
