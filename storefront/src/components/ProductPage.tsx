import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Check, Clock, Heart, List, Lock, Package, Share2, ShieldCheck, ShieldOff, ShoppingBag, TriangleAlert, Zap } from "lucide-react";
import { ProductTile } from "@/components/Hero";
import { QuantityStepper } from "@/components/QuantityStepper";
import { fetchFavorites, fetchReviews, requestStockAlert, setFavorite, assetUrl, errorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { maxOrderable, money, periodLabel } from "@/lib/format";
import { warrantyBadgeClass, warrantyView } from "@/lib/warranty";
import { Link, navigate, productPath, ROUTES, withNext } from "@/lib/router";
import type { Offer, PublicReview } from "@/types";

type ProductPageProps = {
  offer: Offer | null;
  loading: boolean;
  related: Offer[];
  inCart: number;
  cartIsFull: boolean;
  onOpenOffer: (offer: Offer) => void;
  onAdd: (offer: Offer, quantity: number) => void;
  onBuyNow: (offer: Offer, quantity: number) => void;
};

const PAY_STEPS = [
  ["Paie ta commande", "Portefeuille, ou D17, Flouci, IZI et Wafa Cash."],
  ["Reçois-le aussitôt", "L'accès arrive sur ta commande dès que le paiement est confirmé."],
  ["Un souci ?", "Le support est à un message."],
];

const URL_PATTERN = /https?:\/\/[^\s<]+/g;

function FavoriteButton({ offerId }: { offerId: number }) {
  const { customer, token } = useAuth();
  const [saved, setSaved] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      setSaved(false);
      return undefined;
    }
    const controller = new AbortController();
    fetchFavorites(token, controller.signal)
      .then((result) => setSaved(result.favorites.some((item) => item.offer_id === offerId)))
      .catch(() => undefined);
    return () => controller.abort();
  }, [token, offerId]);

  async function toggle() {
    if (!token || !customer) {
      navigate(withNext(ROUTES.login, productPath(offerId)));
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const result = await setFavorite(token, offerId, !saved);
      setSaved(result.saved);
      setNote(result.emailed ? "La fiche complète est partie sur ton email." : result.saved ? "Déjà dans tes favoris." : "Retiré de tes favoris.");
    } catch (reason) {
      setError(errorMessage(reason, "Le favori n'a pas pu être enregistré."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="favorite-row">
      <button
        type="button"
        className={saved ? "button button-ghost favorite-button is-saved" : "button button-ghost favorite-button"}
        aria-pressed={saved}
        disabled={busy}
        onClick={() => void toggle()}
      >
        <Heart size={16} aria-hidden="true" fill={saved ? "currentColor" : "none"} />
        {busy ? "Enregistrement…" : saved ? "Dans tes favoris" : "Ajouter aux favoris"}
      </button>
      {note ? <p className="favorite-note" role="status">{note}</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}

function StockAlert({ offerId }: { offerId: number }) {
  const { customer, token } = useAuth();
  const [email, setEmail] = useState(customer?.email ?? "");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await requestStockAlert(offerId, email.trim(), token || undefined);
      setDone(result.already_available ? "Ce produit est déjà en stock." : "C'est noté. On t'écrit dès qu'il est disponible.");
    } catch (reason) {
      setError(errorMessage(reason, "L'alerte n'a pas pu être enregistrée."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stock-alert" onSubmit={(event) => void submit(event)}>
      <p>
        {customer?.email
          ? `Indisponible pour le moment. On t'écrit à ${customer.email} dès que c'est de nouveau en stock.`
          : "Indisponible pour le moment. Laisse ton email et on t'écrit dès que c'est de nouveau en stock."}
      </p>
      {done ? (
        <p className="stock-alert-done" role="status">
          {done}
        </p>
      ) : (
        <>
          {customer ? null : (
            <label>
              Email
              <input
                required
                type="email"
                autoComplete="email"
                inputMode="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="toi@exemple.com"
              />
            </label>
          )}
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "Enregistrement…" : "Me prévenir quand c'est disponible"}
          </button>
          {error ? <small className="form-error">{error}</small> : null}
        </>
      )}
    </form>
  );
}

function receiveLines(description: string) {
  const lines = description
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.length ? lines : ["Service digital disponible directement depuis notre catalogue."];
}

function linkify(text: string) {
  const parts = text.split(URL_PATTERN);
  return parts.map((part, index) => {
    if (!/^https?:\/\//.test(part)) return part;
    const url = part.replace(/[),.;:!?]+$/, "");
    return (
      <span key={index}>
        <a href={url} target="_blank" rel="noopener noreferrer">
          {url}
        </a>
        {part.slice(url.length)}
      </span>
    );
  });
}

function DescriptionBody({ text }: { text: string }) {
  const lines = receiveLines(text);
  const long = text.length > 280 || lines.length > 6;
  if (!long) {
    return (
      <div className="rich">
        {lines.map((line, index) => (
          <p key={index}>
            <Check size={16} aria-hidden="true" />
            <span>{linkify(line)}</span>
          </p>
        ))}
      </div>
    );
  }
  const blocks = text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
  return (
    <div className="rich is-long">
      {(blocks.length ? blocks : lines).map((block, index) => (
        <p key={index}>{linkify(block)}</p>
      ))}
    </div>
  );
}

export function ProductPage({ offer, loading, related, inCart, cartIsFull, onOpenOffer, onAdd, onBuyNow }: ProductPageProps) {
  const [quantity, setQuantity] = useState(1);
  const [copied, setCopied] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [agreeHint, setAgreeHint] = useState(false);
  const [tint, setTint] = useState(0);
  const [added, setAdded] = useState(false);
  const pendingAdd = useRef<number | null>(null);

  useEffect(() => {
    if (pendingAdd.current === null) return;
    if (inCart > pendingAdd.current) {
      pendingAdd.current = null;
      setAdded(true);
    }
  }, [inCart]);

  useEffect(() => {
    if (!offer) return;
    setQuantity(offer.min_quantity);
    setCopied(false);
    setAgreed(false);
    setAgreeHint(false);
    setTint(0);
    setAdded(false);
    pendingAdd.current = null;
  }, [offer?.id]);

  if (!offer) {
    return (
      <section className="doc-page">
        <header className="page-intro">
          <span className="kicker">BlackMarket</span>
          <h1>{loading ? "Chargement…" : "Produit introuvable"}</h1>
          <p>
            <Link to={ROUTES.shop}>Retour à la boutique</Link>
          </p>
        </header>
      </section>
    );
  }

  const ceiling = maxOrderable(offer);
  const blocked = !offer.available || ceiling < offer.min_quantity;
  const lockedOut = cartIsFull && !inCart;
  const period = periodLabel(offer.period_days);
  const stockLabel = !offer.available ? "Épuisé" : offer.stock < 0 ? "En stock" : `${offer.stock} en stock`;
  const low = offer.available && offer.stock > 0 && offer.stock <= 3;
  const bar = offer.stock < 0 ? 100 : Math.max(6, Math.min(100, offer.stock * 8));
  const shopCategory = `${ROUTES.shop}?categorie=${encodeURIComponent(String(offer.service_id))}#catalogue`;
  const shareTitle = offer.name;
  const product = offer;
  const warranty = warrantyView(product);
  const mustAgree = product.description.trim().length > 0;

  function showDescription() {
    document.getElementById("product-desc")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function buy(action: "add" | "now") {
    if (mustAgree && !agreed) {
      setAgreeHint(true);
      showDescription();
      document.getElementById("agree-description")?.focus();
      return;
    }
    if (action === "now") onBuyNow(product, quantity);
    else {
      pendingAdd.current = inCart;
      onAdd(product, quantity);
      window.setTimeout(() => {
        pendingAdd.current = null;
      }, 50);
    }
  }

  async function share() {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: shareTitle, url });
        return;
      } catch {
        return;
      }
    }
    await navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <article className="pdp-page">
      <div className="pdp-top">
        <nav className="crumbs" aria-label="Fil d'Ariane">
          <Link to={ROUTES.shop} aria-label="Boutique">
            <ArrowLeft size={16} aria-hidden="true" />
          </Link>
          <Link to={ROUTES.shop}>Boutique</Link>
          <span>/</span>
          <Link to={shopCategory}>{offer.service_name}</Link>
        </nav>
        <button type="button" className="button button-ghost pdp-share" onClick={() => void share()}>
          <Share2 size={15} aria-hidden="true" />
          {copied ? "Lien copié" : "Partager"}
        </button>
      </div>

      <div className="pdp-layout">
        <div className="pdp-main">
          <div className="gal-stage">
            {offer.video_url ? (
              <video src={assetUrl(offer.video_url)} poster={offer.image_url ? assetUrl(offer.image_url) : undefined} controls playsInline preload="metadata" />
            ) : offer.image_url || offer.service_logo_url ? (
              <img src={assetUrl(offer.image_url || offer.service_logo_url)} alt="" decoding="async" />
            ) : (
              <span className="prod-ph">{offer.service_emoji}</span>
            )}
            {offer.available ? null : <span className="sold-stamp">Épuisé</span>}
            <span className="pricechip">{money(offer.price_millimes)}</span>
          </div>

          <div className="pdp-tags">
            <span className="tag tag-blue">{offer.service_name}</span>
            {offer.available ? (
              <span className="tag">
                <Zap size={13} aria-hidden="true" /> Livraison immédiate
              </span>
            ) : null}
            <span className={warrantyBadgeClass("poster-warranty", warranty.tone)}>
              {warranty.tone === "none" ? <ShieldOff size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}
              {warranty.label}
            </span>
            {offer.badge ? <span className="tag">{offer.badge}</span> : null}
          </div>

          <h1 id="product-title">{offer.name}</h1>
          <p className="pdp-meta">
            {period ? (
              <span>
                <Clock size={15} aria-hidden="true" /> {period}
              </span>
            ) : null}
            <span>
              <Package size={15} aria-hidden="true" /> {stockLabel}
            </span>
          </p>

          <section className="desc-card" id="product-desc" aria-labelledby="product-desc-title">
            <h2 id="product-desc-title">
              <List size={18} aria-hidden="true" /> Description
            </h2>
            <div className="desc-sec">
              <span className="label-caps">Ce que tu reçois</span>
              <DescriptionBody text={offer.description} />
            </div>
            <div className="desc-sec">
              <span className="label-caps">Livraison et garantie</span>
              <dl className="facts">
                <div>
                  <dt>
                    <Zap size={16} aria-hidden="true" /> Livraison
                  </dt>
                  <dd>{offer.delivery_delay || "Instantané, depuis le stock"}</dd>
                </div>
                <div>
                  <dt>
                    <Clock size={16} aria-hidden="true" /> Durée
                  </dt>
                  <dd>{period || "—"}</dd>
                </div>
                <div>
                  <dt>
                    <ShieldCheck size={16} aria-hidden="true" /> Garantie
                  </dt>
                  <dd>{warranty.label}</dd>
                </div>
                <div>
                  <dt>
                    <ShieldCheck size={16} aria-hidden="true" /> Remplacement
                  </dt>
                  <dd>{warranty.covered ? "Depuis la commande" : "Non couvert"}</dd>
                </div>
                <div>
                  <dt>
                    <Package size={16} aria-hidden="true" /> Enregistré dans
                  </dt>
                  <dd>Mes achats</dd>
                </div>
              </dl>
            </div>
          </section>

          {related.length ? (
            <section className="also" aria-labelledby="also-title">
              <span className="kicker">Tu pourrais aimer</span>
              <div className="also-head">
                <h2 id="also-title">Plus de {offer.service_name}</h2>
                <Link to={shopCategory}>
                  Voir tout <ArrowLeft size={14} aria-hidden="true" className="also-arrow" />
                </Link>
              </div>
              <div className="tile-grid">
                {related.slice(0, 4).map((item) => (
                  <ProductTile key={item.id} offer={item} onOpen={onOpenOffer} />
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <div className="pdp-side">
          <aside className="order-card">
            <span className="label-caps">Ta commande</span>
            <div className="oline">
              <span className="order-thumb">
                {offer.image_url || offer.service_logo_url ? <img src={assetUrl(offer.image_url || offer.service_logo_url)} alt="" /> : offer.service_emoji}
              </span>
              <div>
                <b>{offer.name}</b>
                <small>
                  BlackMarket · {money(offer.price_millimes)} l'unité
                </small>
              </div>
            </div>

            <div className={`stockbox${low ? " low" : ""}`}>
              <div>
                <span className="sb-label">
                  <Package size={16} aria-hidden="true" /> Stock disponible
                </span>
                <b className="sb-count">
                  {offer.available && offer.stock >= 0 ? (
                    <>
                      {offer.stock} <small>en stock</small>
                    </>
                  ) : (
                    stockLabel
                  )}
                </b>
              </div>
              <div className="sb-meter" aria-hidden="true">
                <i style={{ width: `${blocked ? 0 : bar}%` }} />
              </div>
              {low ? (
                <p className="sb-note">
                  <TriangleAlert size={14} aria-hidden="true" /> Plus que {offer.stock} — commande bientôt
                </p>
              ) : null}
            </div>

            {!offer.available ? (
              <StockAlert offerId={offer.id} />
            ) : blocked ? (
              <span className="offer-unavailable">Indisponible pour le moment</span>
            ) : (
              <>
                {ceiling > offer.min_quantity ? (
                  <div className="order-qty">
                    <span>Quantité</span>
                    <QuantityStepper
                      value={quantity}
                      min={offer.min_quantity}
                      max={ceiling}
                      label={`Quantité pour ${offer.name}`}
                      onChange={(next) => {
                        setQuantity(next);
                        setTint((value) => value + 1);
                      }}
                    />
                  </div>
                ) : null}
                <div className="order-total">
                  <div>
                    <span>Total</span>
                    <small>
                      {quantity} article{quantity > 1 ? "s" : ""} · sans frais ajoutés
                    </small>
                  </div>
                  <b className={tint ? "is-fresh" : undefined} key={tint}>
                    <span className="total-tint" aria-hidden="true" />
                    {money(offer.price_millimes * quantity)}
                  </b>
                </div>
                {offer.remark || offer.requires_info ? (
                  <p className="order-note">
                    <span className="remark-copy">
                      <b>{offer.requires_info ? "Informations à envoyer" : "Remarque"}</b>
                      {offer.remark || "Tu enverras tes informations au moment du paiement."}
                    </span>
                  </p>
                ) : null}
                <div className="info-box">
                  <div>
                    <b>Livraison · {offer.available ? "immédiate" : "indisponible"}</b>
                    <p>L'accès arrive sur ta commande dès que le paiement est confirmé.</p>
                  </div>
                  <div>
                    <b>Garantie · {warranty.label}</b>
                    <p>
                      {warranty.covered
                        ? "La demande se fait depuis la commande."
                        : "Vendu comme décrit. Le support reste joignable en cas de souci."}
                    </p>
                  </div>
                </div>
                {mustAgree ? (
                  <label className={agreeHint && !agreed ? "agree-desc is-needed" : "agree-desc"}>
                    <input
                      id="agree-description"
                      type="checkbox"
                      checked={agreed}
                      onChange={(event) => {
                        setAgreed(event.target.checked);
                        if (event.target.checked) setAgreeHint(false);
                      }}
                    />
                    <span>
                      J'ai lu et j'accepte la{" "}
                      <a
                        href="#product-desc"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          showDescription();
                        }}
                      >
                        description
                      </a>{" "}
                      de ce produit.
                    </span>
                  </label>
                ) : null}
                {agreeHint && !agreed ? (
                  <p className="agree-hint">Coche la case après avoir lu la description.</p>
                ) : null}
                <div className="order-actions">
                  <button
                    type="button"
                    className="button button-primary pdp-pay"
                    disabled={lockedOut}
                    onClick={() => buy("now")}
                  >
                    Acheter maintenant
                  </button>
                  <button
                    type="button"
                    className="button button-ghost pdp-pay"
                    disabled={lockedOut}
                    onClick={() => buy("add")}
                  >
                    {inCart ? <Check size={16} aria-hidden="true" /> : <ShoppingBag size={16} aria-hidden="true" />}
                    {inCart ? `Au panier (${inCart})` : "Ajouter au panier"}
                  </button>
                </div>
                {added ? (
                  <p className="add-confirm" role="status">
                    Ajouté au panier
                  </p>
                ) : null}
                {lockedOut ? <small className="drawer-notice">Ton panier a atteint sa limite de produits.</small> : null}
              </>
            )}
            <FavoriteButton offerId={offer.id} />
            <p className="order-secure">
              <Lock size={14} aria-hidden="true" /> Paiement sécurisé par <b>BlackMarket</b>
            </p>
          </aside>

          <aside className="pay-steps">
            <span className="label-caps">Du paiement à ton produit</span>
            <ol>
              {PAY_STEPS.map(([title, body], index) => (
                <li key={title}>
                  <span>{index + 1}</span>
                  <div>
                    <b>{title}</b>
                    <p>{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </aside>
        </div>
        <OfferReviews offerId={offer.id} />
      </div>
    </article>
  );
}

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

function usePublicReviews(offerId?: number) {
  const [reviews, setReviews] = useState<PublicReview[] | null>(null);
  const [average, setAverage] = useState(0);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setReviews(null);
    setError("");
    fetchReviews(offerId, controller.signal)
      .then((result) => {
        setReviews(result.reviews);
        setAverage(result.average ?? 0);
        setCount(result.count ?? result.reviews.length);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason, "Impossible de charger les avis."));
        setReviews([]);
      });
    return () => controller.abort();
  }, [offerId, attempt]);

  return { reviews, average, count, error, retry: () => setAttempt((value) => value + 1) };
}

function OfferReviews({ offerId }: { offerId: number }) {
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

export function PublicReviewList() {
  const { reviews, error, retry } = usePublicReviews();
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
