import { useEffect, useState } from "react";
import { fetchReviews, errorMessage } from "@/lib/api";
import type { PublicReview } from "@/types";

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

function ReviewCards({ reviews }: { reviews: PublicReview[] }) {
  if (!reviews.length) return <p className="review-empty">Aucun avis publié pour le moment.</p>;
  return (
    <ul className="review-list">
      {reviews.map((review) => (
        <li key={`${review.created_at}-${review.name}-${review.offer_name}`}>
          <strong>{review.name}</strong>
          <StarRow value={review.score} />
          <p>{review.comment}</p>
          {review.offer_name ? <small>{review.offer_name}</small> : null}
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

/** Home list. It waits until the browser is idle so it does not compete with the catalog. */
export function PublicReviewList() {
  const { reviews, error, retry } = usePublicReviews(undefined, true);
  return (
    <section className="offer-reviews home-reviews" aria-labelledby="site-reviews-title">
      <h2 id="site-reviews-title">Avis des clients</h2>
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
