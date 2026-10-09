import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
import { ArrowRight, ShoppingCart } from "lucide-react";
import { CartDrawer } from "@/components/CartDrawer";
import { CatalogSection } from "@/components/CatalogSection";
import { CheckoutDialog } from "@/components/CheckoutDialog";
import { Hero } from "@/components/Hero";
import { IntroSplash } from "@/components/IntroSplash";
import { PublicReviewList } from "@/components/PublicReviews";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { MobileTabBar } from "@/components/MobileTabBar";
import { SignupGate } from "@/components/SignupGate";
import { useAuth } from "@/hooks/useAuth";
import { useCart } from "@/hooks/useCart";
import { useCatalog } from "@/hooks/useCatalog";
import { money, plural } from "@/lib/format";
import { LoadingPage } from "@/components/LoadMark";
import { Link, navigate, productId, productPath, RouteProgress, ROUTES, usePathname } from "@/lib/router";
import { trackInteraction, trackVisit } from "@/lib/track";
import type { Offer } from "@/types";

const ProductPage = lazy(() => import("@/components/ProductPage").then((mod) => ({ default: mod.ProductPage })));
const AccountPage = lazy(() => import("@/pages/AccountPage").then((mod) => ({ default: mod.AccountPage })));
const LoginPage = lazy(() => import("@/pages/LoginPage").then((mod) => ({ default: mod.LoginPage })));
const RegisterPage = lazy(() => import("@/pages/RegisterPage").then((mod) => ({ default: mod.RegisterPage })));
const VerifyEmailPage = lazy(() => import("@/pages/VerifyEmailPage").then((mod) => ({ default: mod.VerifyEmailPage })));
const ForgotPasswordPage = lazy(() => import("@/pages/ForgotPasswordPage").then((mod) => ({ default: mod.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage").then((mod) => ({ default: mod.ResetPasswordPage })));
const storePages = () => import("@/pages/StorePages");
const CategoriesPage = lazy(() => storePages().then((mod) => ({ default: mod.CategoriesPage })));
const DealsPage = lazy(() => storePages().then((mod) => ({ default: mod.DealsPage })));
const PricesPage = lazy(() => storePages().then((mod) => ({ default: mod.PricesPage })));
const NewsPage = lazy(() => storePages().then((mod) => ({ default: mod.NewsPage })));
const HelpPage = lazy(() => storePages().then((mod) => ({ default: mod.HelpPage })));
const TermsPage = lazy(() => storePages().then((mod) => ({ default: mod.TermsPage })));
const PrivacyPage = lazy(() => storePages().then((mod) => ({ default: mod.PrivacyPage })));
const ContactPage = lazy(() => storePages().then((mod) => ({ default: mod.ContactPage })));
const CommunityPage = lazy(() => storePages().then((mod) => ({ default: mod.CommunityPage })));
const ReportPage = lazy(() => storePages().then((mod) => ({ default: mod.ReportPage })));
const MessengerPage = lazy(() => storePages().then((mod) => ({ default: mod.MessengerPage })));

const PAGES: Record<string, ComponentType | undefined> = {
  [ROUTES.login]: LoginPage,
  [ROUTES.register]: RegisterPage,
  [ROUTES.verifyEmail]: VerifyEmailPage,
  [ROUTES.forgotPassword]: ForgotPasswordPage,
  [ROUTES.resetPassword]: ResetPasswordPage,
  [ROUTES.news]: NewsPage,
  [ROUTES.help]: HelpPage,
  "/aide": HelpPage,
  [ROUTES.terms]: TermsPage,
  [ROUTES.privacy]: PrivacyPage,
  [ROUTES.contact]: ContactPage,
  [ROUTES.community]: CommunityPage,
  [ROUTES.report]: ReportPage,
  [ROUTES.messenger]: MessengerPage,
};

const DEFAULT_MAX_LINES = 12;

export default function App() {
  const { customer, loading: authLoading, token } = useAuth();
  const { catalog, offers, loading, error, reload } = useCatalog();
  const maxLines = catalog?.max_cart_lines ?? DEFAULT_MAX_LINES;
  const cart = useCart(offers, maxLines);

  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const path = usePathname();
  const openedId = productId(path);
  useEffect(() => {
    if (authLoading || !customer) return;
    trackVisit(path);
  }, [path, authLoading, customer]);
  const openCheckout = () => {
    trackInteraction("checkout", { path });
    setCheckoutOpen(true);
  };
  const openProduct = (offer: Offer) => navigate(productPath(offer.id));
  const Page = PAGES[path];
  const categories = (catalog?.services ?? [])
    .filter((service) => service.offers.length)
    .map((service) => ({ id: String(service.id), label: service.name }));

  // Closing the last line should not leave an empty drawer or dialog on screen.
  useEffect(() => {
    if (!cart.lines.length) {
      setCheckoutOpen(false);
    }
  }, [cart.lines.length]);

  // The product page is its own file. Warm it after the first paint so opening
  // a product does not wait on a download, without blocking the home screen.
  useEffect(() => {
    const warm = () => {
      void import("@/components/ProductPage");
    };
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(warm, { timeout: 2500 });
      return () => window.cancelIdleCallback(id);
    }
    const timer = window.setTimeout(warm, 1200);
    return () => window.clearTimeout(timer);
  }, []);

  if (token && authLoading) {
    return (
      <div className="page">
        <LoadingPage />
      </div>
    );
  }

  if (!customer) return <SignupGate />;

  return (
    <div className="page" id="top">
      <RouteProgress />
      <IntroSplash />
      {loading && !offers.length && !error ? <LoadingPage /> : null}
      <SiteHeader
        cartCount={cart.count}
        cartTotalMillimes={cart.totalMillimes}
        categories={categories.map((category) => ({
          ...category,
          count: offers.filter((offer) => String(offer.service_id) === category.id).length,
        }))}
        onOpenCart={() => setCartOpen(true)}
      />

      <main key={path} className="page-enter">
        <Suspense fallback={<LoadingPage />}>
        {path === ROUTES.account ? (
          <AccountPage
            offers={offers}
            catalogLoading={loading}
            catalogError={error}
            reloadCatalog={reload}
            maxLines={maxLines}
            place={(offer, quantity) => {
              if (!cart.place(offer, quantity)) return false;
              openCheckout();
              return true;
            }}
          />
        ) : Page ? (
          <Page />
        ) : path === ROUTES.categories ? (
          <CategoriesPage categories={categories} offers={offers} />
        ) : path === ROUTES.deals ? (
          <DealsPage offers={offers} onOpenOffer={openProduct} />
        ) : path === ROUTES.prices ? (
          <PricesPage offers={offers} onOpenOffer={openProduct} />
        ) : openedId ? (
          <ProductPage
            offer={offers.find((item) => item.id === openedId) ?? null}
            loading={loading}
            related={offers.filter((item) => item.id !== openedId && item.service_id === offers.find((offer) => offer.id === openedId)?.service_id)}
            inCart={cart.quantityOf(openedId)}
            cartIsFull={cart.isFull}
            onOpenOffer={openProduct}
            onAdd={(offer, quantity) => cart.add(offer, quantity)}
            onBuyNow={(offer, quantity) => {
              if (!cart.quantityOf(offer.id)) cart.add(offer, quantity);
              openCheckout();
            }}
          />
        ) : path === ROUTES.home || path === ROUTES.shop ? (
          <>
            {path === ROUTES.home ? (
              <>
                <Hero offers={offers} categories={categories} onOpenOffer={openProduct} />
                <PublicReviewList />
              </>
            ) : (
              <CatalogSection
                offers={offers}
                categories={categories}
                loading={loading}
                error={error}
                onReload={reload}
                onOpenOffer={openProduct}
              />
            )}
          </>
        ) : (
          <section className="doc-page">
            <header className="page-intro">
              <span className="kicker">BlackMarket</span>
              <h1>Page introuvable</h1>
              <p>
                <Link to={ROUTES.home}>Retour à l'accueil</Link>
              </p>
            </header>
          </section>
        )}
        </Suspense>
      </main>

      <SiteFooter />
      <MobileTabBar />

      {cart.count && !cartOpen && !checkoutOpen && (path === ROUTES.home || path === ROUTES.shop) ? (
        <button type="button" className="cart-bar" onClick={() => setCartOpen(true)}>
          <ShoppingCart size={18} aria-hidden="true" />
          <span>
            {cart.count} {plural(cart.count, "article", "articles")} · {money(cart.totalMillimes)}
          </span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      ) : null}

      <CartDrawer
        open={cartOpen}
        cart={cart}
        maxLines={maxLines}
        onClose={() => setCartOpen(false)}
        onCheckout={() => {
          setCartOpen(false);
          openCheckout();
        }}
      />

      <CheckoutDialog
        open={checkoutOpen}
        cart={cart}
        paymentMethods={catalog?.payment_methods ?? []}
        onClose={() => setCheckoutOpen(false)}
        onConfirmed={cart.clear}
      />
    </div>
  );
}
