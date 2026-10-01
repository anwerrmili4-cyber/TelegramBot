import { useEffect, useRef, useState, type AnimationEvent, type CSSProperties, type PointerEvent } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, Layers } from "lucide-react";
import { assetUrl } from "@/lib/api";
import { money } from "@/lib/format";
import { warrantyView } from "@/lib/warranty";
import { Link, productPath } from "@/lib/router";
import type { Offer } from "@/types";

const DWELL_MS = 4100;

function isDeal(offer: Offer): boolean {
  const bulk = offer.bulk_unit_millimes ?? 0;
  return (offer.bulk_quantity ?? 0) > 1 && bulk > 0 && bulk < offer.price_millimes;
}

function discountPercent(offer: Offer): number {
  const bulk = offer.bulk_unit_millimes ?? 0;
  if (!isDeal(offer)) return 0;
  return Math.max(1, Math.round((1 - bulk / offer.price_millimes) * 100));
}

/** Bulk deals first, then the rest of what is actually in stock. */
export function filmOffers(offers: Offer[], limit = 6): Offer[] {
  const live = offers.filter((offer) => offer.available);
  const deals = live.filter(isDeal);
  const rest = live.filter((offer) => !isDeal(offer));
  const pool = [...deals, ...rest.filter((offer) => offer.featured), ...rest.filter((offer) => !offer.featured)];
  const seen = new Set<number>();
  const frames: Offer[] = [];
  for (const offer of pool) {
    if (seen.has(offer.id)) continue;
    seen.add(offer.id);
    frames.push(offer);
    if (frames.length === limit) break;
  }
  return frames;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);
  return reduced;
}

export function FilmReel({ offers }: { offers: Offer[] }) {
  const slides = filmOffers(offers);
  const count = slides.length;
  const [index, setIndex] = useState(0);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [dir, setDir] = useState(1);
  const [hovering, setHovering] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [inView, setInView] = useState(true);
  const reduced = useReducedMotion();
  const rootRef = useRef<HTMLElement>(null);
  const swiped = useRef(false);
  const originX = useRef(0);
  const current = count ? ((index % count) + count) % count : 0;
  const paused = hovering || focused || hidden || !inView || reduced;

  useEffect(() => {
    const onHide = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onHide);
    return () => document.removeEventListener("visibilitychange", onHide);
  }, []);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || count < 2) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.45 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [count]);

  useEffect(() => {
    if (leaving === null) return;
    const timer = window.setTimeout(() => setLeaving(null), 820);
    return () => window.clearTimeout(timer);
  }, [leaving]);

  if (count === 0) return null;

  function go(next: number, direction: number) {
    const target = ((next % count) + count) % count;
    if (target === current) return;
    setDir(direction);
    setLeaving(current);
    setIndex(target);
  }

  function advance(event: AnimationEvent<HTMLElement>) {
    if (paused || count < 2 || event.animationName !== "poster-bar") return;
    go(current + 1, 1);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    originX.current = event.clientX;
    swiped.current = false;
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    const delta = event.clientX - originX.current;
    if (Math.abs(delta) < 48) return;
    swiped.current = true;
    go(current + (delta < 0 ? 1 : -1), delta < 0 ? 1 : -1);
  }

  return (
    <section className="posters-sec" ref={rootRef} aria-label="Offres">
      <div
        className={paused ? "posters paused" : "posters"}
        style={{ "--dwell": `${DWELL_MS}ms`, "--dir": dir } as CSSProperties}
        aria-roledescription="carousel"
        onAnimationEnd={advance}
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        onFocus={() => setFocused(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setFocused(false);
        }}
        onKeyDown={(event) => {
          if (count < 2) return;
          if (event.key === "ArrowRight") {
            event.preventDefault();
            go(current + 1, 1);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            go(current - 1, -1);
          }
        }}
      >
        <div
          className="poster-track"
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onClickCapture={(event) => {
            if (!swiped.current) return;
            event.preventDefault();
            event.stopPropagation();
            swiped.current = false;
          }}
        >
          {slides.map((offer, slideIndex) => {
            const active = slideIndex === current;
            const picture = offer.image_url || offer.service_logo_url;
            const deal = isDeal(offer);
            const warranty = warrantyView(offer);
            const percent = discountPercent(offer);
            const unit = deal ? offer.bulk_unit_millimes ?? offer.price_millimes : offer.price_millimes;
            const classes = ["poster", picture ? "" : "no-img", deal ? "is-bulk" : "", active ? "on" : "", leaving === slideIndex ? "leaving" : ""]
              .filter(Boolean)
              .join(" ");
            return (
              <Link
                key={offer.id}
                className={classes}
                to={productPath(offer.id)}
                style={{ "--pi": slideIndex } as CSSProperties}
                aria-roledescription="slide"
                aria-label={`${slideIndex + 1} sur ${count} : ${offer.name}, ${warranty.label}`}
                aria-hidden={active ? undefined : true}
                tabIndex={active ? undefined : -1}
              >
                {picture ? <img className="poster-bg" src={assetUrl(picture)} alt="" aria-hidden="true" decoding="async" /> : null}
                <div className="poster-body">
                  <span className="poster-kicker">
                    <Layers size={14} aria-hidden="true" />
                    {deal ? `Offre groupe · dès ${offer.bulk_quantity}+` : offer.badge || "Sélection"}
                  </span>
                  {deal ? (
                    <div className="poster-off">
                      <span>−{percent}</span>
                      <small>
                        %<br />
                        l'unité
                      </small>
                    </div>
                  ) : null}
                  <h3>{offer.name}</h3>
                  <div className="poster-price">
                    <b>{money(unit)}</b>
                    {deal ? <em>l'unité dès {offer.bulk_quantity}+</em> : <em>{offer.service_name}</em>}
                    {deal ? <s>{money(offer.price_millimes)}</s> : null}
                  </div>
                  <span className="poster-cta">
                    {deal ? "Voir les prix groupe" : "Voir le produit"}
                    <ArrowRight size={16} aria-hidden="true" />
                  </span>
                </div>
                <div className={offer.image_url ? "poster-art" : "poster-art brandpic"}>
                  {picture ? (
                    <img src={assetUrl(picture)} alt="" decoding="async" width={400} height={400} />
                  ) : (
                    <span className="poster-emoji" aria-hidden="true">
                      {offer.service_emoji}
                    </span>
                  )}
                  <span className={warranty.covered ? "warranty-badge is-covered" : "warranty-badge is-open"}>{warranty.label}</span>
                </div>
              </Link>
            );
          })}
        </div>
        {count > 1 ? (
          <>
            <button className="poster-nav prev" type="button" aria-label="Précédent" onClick={() => go(current - 1, -1)}>
              <ChevronLeft size={18} aria-hidden="true" />
            </button>
            <button className="poster-nav next" type="button" aria-label="Suivant" onClick={() => go(current + 1, 1)}>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
            <div className="poster-dots">
              {slides.map((offer, slideIndex) => {
                const on = slideIndex === current;
                return (
                  <button
                    key={offer.id}
                    type="button"
                    className={on ? "on" : ""}
                    aria-label={`Offre ${slideIndex + 1}`}
                    aria-current={on ? "true" : undefined}
                    onClick={() => go(slideIndex, slideIndex > current ? 1 : -1)}
                  >
                    <i />
                  </button>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
