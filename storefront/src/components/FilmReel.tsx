import { useEffect, useRef, useState, type AnimationEvent, type CSSProperties, type PointerEvent } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, Layers, ShieldCheck, ShieldOff } from "lucide-react";
import { assetUrl } from "@/lib/api";
import { money } from "@/lib/format";
import { warrantyBadgeClass, warrantyView } from "@/lib/warranty";
import { FavoriteButton } from "@/components/FavoriteButton";
import { Link, productPath } from "@/lib/router";
import type { Offer } from "@/types";

const DWELL_MS = 6000;

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

/** Wordmarks are wider than the square frame. Cover would clip the name. */
function isWideMark(img: HTMLImageElement): boolean {
  if (!img.naturalWidth || !img.naturalHeight) return false;
  return img.naturalWidth / img.naturalHeight > 1.25;
}

function PosterArt({ src, brand }: { src: string; brand: boolean }) {
  const [logo, setLogo] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  function measure(img: HTMLImageElement) {
    const wide = isWideMark(img);
    setLogo((current) => (current === wide ? current : wide));
  }

  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete) measure(img);
  }, [src]);

  return (
    <div className={brand ? "poster-art brandpic" : "poster-art"}>
      <div className={logo ? "poster-shot is-logo" : "poster-shot"}>
        <span className="poster-still">
          <img
            ref={imgRef}
            src={src}
            alt=""
            decoding="async"
            width={400}
            height={400}
            onLoad={(event) => measure(event.currentTarget)}
          />
        </span>
      </div>
    </div>
  );
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
  const [inView, setInView] = useState(false);
  const [userHold, setUserHold] = useState(false);
  const reduced = useReducedMotion();
  const rootRef = useRef<HTMLElement>(null);
  const swiped = useRef(false);
  const originX = useRef(0);
  const originY = useRef(0);
  const current = count ? ((index % count) + count) % count : 0;
  const paused = hovering || focused || hidden || !inView || reduced || userHold;

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
    const timer = window.setTimeout(() => setLeaving(null), 900);
    return () => window.clearTimeout(timer);
  }, [leaving]);

  if (count === 0) return null;

  function go(next: number, direction: number, manual = false) {
    if (manual) setUserHold(true);
    const target = ((next % count) + count) % count;
    if (target === current) return;
    const from = current;
    setDir(direction);
    window.requestAnimationFrame(() => {
      setLeaving(from);
      setIndex(target);
    });
  }

  function advance(event: AnimationEvent<HTMLElement>) {
    if (paused || event.currentTarget.classList.contains("paused") || count < 2 || event.animationName !== "poster-bar") return;
    go(current + 1, 1);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    originX.current = event.clientX;
    originY.current = event.clientY;
    swiped.current = false;
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    const deltaX = event.clientX - originX.current;
    const deltaY = event.clientY - originY.current;
    if (Math.abs(deltaX) < 48 || Math.abs(deltaX) <= Math.abs(deltaY)) return;
    swiped.current = true;
    go(current + (deltaX < 0 ? 1 : -1), deltaX < 0 ? 1 : -1, true);
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
        onFocus={(event) => {
          const target = event.target as HTMLElement;
          setFocused(!target.closest(".poster-play"));
        }}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setFocused(false);
        }}
        onKeyDown={(event) => {
          if (count < 2) return;
          if (event.key === "ArrowRight") {
            event.preventDefault();
            go(current + 1, 1, true);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            go(current - 1, -1, true);
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
            const nearby =
              active ||
              leaving === slideIndex ||
              slideIndex === (current + 1) % count ||
              slideIndex === (current + count - 1) % count;
            const kicker = deal ? `Offre groupe · dès ${offer.bulk_quantity}+` : offer.badge || "Sélection";
            const promo = !deal && kicker.trim().toUpperCase() === "PROMO";
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
                <FavoriteButton compact offerId={offer.id} />
                {picture && nearby ? (
                  <img
                    className="poster-bg"
                    src={assetUrl(picture)}
                    alt=""
                    aria-hidden="true"
                    decoding="async"
                    loading={active ? "eager" : "lazy"}
                    fetchPriority={active ? "high" : "low"}
                  />
                ) : null}
                <div className="poster-body">
                  <div className="poster-meta">
                    <span className={promo ? "poster-kicker is-promo" : "poster-kicker"}>
                      <Layers size={14} aria-hidden="true" />
                      <span>{kicker}</span>
                    </span>
                    <span className={warrantyBadgeClass("poster-warranty", warranty.tone)}>
                      {warranty.tone === "none" ? <ShieldOff size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}
                      {warranty.label}
                    </span>
                  </div>
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
                {picture && nearby ? (
                  <PosterArt src={assetUrl(picture)} brand={!offer.image_url} />
                ) : picture ? (
                  <div className={offer.image_url ? "poster-art" : "poster-art brandpic"} />
                ) : (
                  <div className="poster-art brandpic">
                    <div className="poster-shot">
                      <span className="poster-still">
                        <span className="poster-emoji" aria-hidden="true">
                          {offer.service_emoji}
                        </span>
                      </span>
                    </div>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
        {count > 1 ? (
          <>
            <button className="poster-nav prev" type="button" aria-label="Précédent" onClick={() => go(current - 1, -1, true)}>
              <ChevronLeft size={18} aria-hidden="true" />
            </button>
            <button className="poster-nav next" type="button" aria-label="Suivant" onClick={() => go(current + 1, 1, true)}>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
            {!reduced ? (
              <button
                className="poster-play"
                type="button"
                aria-pressed={userHold}
                onClick={() => setUserHold((held) => !held)}
              >
                {userHold ? "Lecture" : "Pause"}
              </button>
            ) : null}
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
                    onClick={() => go(slideIndex, slideIndex > current ? 1 : -1, true)}
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
