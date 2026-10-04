import { useEffect, useState } from "react";
import { assetUrl, fetchReviews, errorMessage } from "@/lib/api";
import type { PublicReview } from "@/types";

const AVIS_DWELL_MS = 5200;

function StarRow({ value }: { value: number }) {
  return (
    <span className="review-stars" aria-label={`${value} sur 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <span key={star} className={star <= value ? "review-star is-on" : "review-star"} aria-hidden="true">
          ★
        </span>
      ))}
    </span>
  );
}

function ServiceMark({ review, className }: { review: PublicReview; className: string }) {
  const logo = review.service_logo_url ? assetUrl(review.service_logo_url) : "";
  const label = review.service_name || review.offer_name || "";
  return (
    <span className={className} aria-hidden="true">
      {logo ? <img src={logo} alt="" /> : label.slice(0, 1) || "✦"}
    </span>
  );
}

function ReviewCards({ reviews }: { reviews: PublicReview[] }) {
  if (!reviews.length) return <p className="review-empty">Aucun avis publié pour le moment.</p>;
  return (
    <ul className="review-list">
      {reviews.map((review) => (
        <li key={`${review.created_at}-${review.name}-${review.offer_name}`}>
          <span className="review-who">
            <strong>{review.name}</strong>
            {review.email ? <span className="review-mail">{review.email}</span> : null}
          </span>
          {review.offer_name ? (
            <span className="review-buy">
              <ServiceMark review={review} className="review-mark" />
              <small>{review.offer_name}</small>
            </span>
          ) : null}
          <StarRow value={review.score} />
          <p>{review.comment}</p>
        </li>
      ))}
    </ul>
  );
}

function usePublicReviews(offerId?: number, defer = false) {
  const [reviews, setReviews] = useState<PublicReview[] | null>(null);
  const [average, setAverage] = useState(0);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let idle = 0;
    let timer = 0;
    setReviews(null);
    setError("");

    const start = () => {
      if (controller.signal.aborted) return;
      fetchReviews(offerId, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setReviews(result.reviews);
          setAverage(result.average ?? 0);
          setCount(result.count ?? result.reviews.length);
        })
        .catch((reason: unknown) => {
          if (controller.signal.aborted) return;
          setError(errorMessage(reason, "Impossible de charger les avis."));
          setReviews([]);
        });
    };

    if (defer && typeof window.requestIdleCallback === "function") {
      idle = window.requestIdleCallback(start, { timeout: 1500 });
    } else if (defer) {
      timer = window.setTimeout(start, 600);
    } else {
      start();
    }

    return () => {
      controller.abort();
      if (idle) window.cancelIdleCallback(idle);
      if (timer) window.clearTimeout(timer);
    };
  }, [offerId, defer, attempt]);

  return { reviews, average, count, error, retry: () => setAttempt((value) => value + 1) };
}

export function OfferReviews({ offerId }: { offerId: number }) {
  const { reviews, average, count, error, retry } = usePublicReviews(offerId);
  return (
    <section className="offer-reviews" aria-labelledby="offer-reviews-title">
      <h2 id="offer-reviews-title">Avis</h2>
      {reviews === null ? <p className="review-wait">Chargement des avis…</p> : null}
      {error ? (
        <p className="form-error">
          {error}{" "}
          <button type="button" className="auth-inline-link" onClick={retry}>
            Réessayer
          </button>
        </p>
      ) : null}
      {reviews && !error ? (
        <>
          {count > 0 ? (
            <p className="review-summary">
              {average.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} / 5 · {count} avis
            </p>
          ) : null}
          <ReviewCards reviews={reviews} />
        </>
      ) : null}
    </section>
  );
}

/** One published review at a time, in the slot under the hero search. Hidden when none exist. */
export function HeroReviewReel() {
  const { reviews } = usePublicReviews();
  const [index, setIndex] = useState(0);
  const [reduced, setReduced] = useState(false);
  const [hidden, setHidden] = useState(false);
  const count = reviews?.length ?? 0;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    const onHide = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onHide);
    return () => document.removeEventListener("visibilitychange", onHide);
  }, []);

  useEffect(() => {
    if (count < 2 || reduced || hidden) return;
    const timer = window.setTimeout(() => setIndex((current) => (current + 1) % count), AVIS_DWELL_MS);
    return () => window.clearTimeout(timer);
  }, [count, index, reduced, hidden]);

  if (!reviews?.length) return null;
  const review = reviews[index % reviews.length];
  const filming = reviews.length > 1 && !reduced;

  return (
    <section className={filming ? "hero-avis is-filming" : "hero-avis"} aria-labelledby="hero-avis-title">
      <h2 id="hero-avis-title" className="hero-avis-title">Avis</h2>
      <div className="hero-avis-viewport">
        <article className="hero-avis-frame" key={`${review.created_at}-${review.name}-${index}`}>
          <div className="hero-avis-copy">
            <span className="hero-avis-who">
              <strong>{review.name}</strong>
              {review.email ? <span className="hero-avis-mail">{review.email}</span> : null}
            </span>
            {review.offer_name ? (
              <span className="hero-avis-buy">
                <ServiceMark review={review} className="hero-avis-mark" />
                <small>{review.offer_name}</small>
              </span>
            ) : null}
            <StarRow value={review.score} />
            <p>{review.comment}</p>
          </div>
        </article>
      </div>
      {filming ? (
        <span className="hero-avis-bar" aria-hidden="true">
          <i key={index} style={{ animationDuration: `${AVIS_DWELL_MS}ms` }} />
        </span>
      ) : null}
    </section>
  );
}

/** Home list. It waits until the browser is idle so it does not compete with the catalog. */
export function PublicReviewList() {
  const { reviews, error, retry } = usePublicReviews(undefined, true);
  return (
    <section className="offer-reviews home-reviews" aria-labelledby="site-reviews-title">
      <h2 id="site-reviews-title">Avis</h2>
      {reviews === null ? <p className="review-wait">Chargement des avis…</p> : null}
      {error ? (
        <p className="form-error">
          {error}{" "}
          <button type="button" className="auth-inline-link" onClick={retry}>
            Réessayer
          </button>
        </p>
      ) : null}
      {reviews && !error ? <ReviewCards reviews={reviews} /> : null}
    </section>
  );
}
