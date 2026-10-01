import { useEffect, useState, type ComponentType } from "react";
import { ArrowRight, ShoppingCart } from "lucide-react";
import { CartDrawer } from "@/components/CartDrawer";
import { CatalogSection } from "@/components/CatalogSection";
import { CheckoutDialog } from "@/components/CheckoutDialog";
import { Hero } from "@/components/Hero";
import { IntroSplash } from "@/components/IntroSplash";
import { ProductPage } from "@/components/ProductPage";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { useCart } from "@/hooks/useCart";
import { useCatalog } from "@/hooks/useCatalog";
import { money, plural } from "@/lib/format";
import { Link, navigate, productId, productPath, RouteProgress, ROUTES, usePathname } from "@/lib/router";
import { AccountPage } from "@/pages/AccountPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import {
  CategoriesPage,
  CommunityPage,
  ContactPage,
  DealsPage,
  HelpPage,
  MessengerPage,
  NewsPage,
  PricesPage,
  PrivacyPage,
  ReportPage,
  TermsPage,
} from "@/pages/StorePages";
import type { Offer } from "@/types";

const PAGES: Record<string, ComponentType | undefined> = {
  [ROUTES.login]: LoginPage,
  [ROUTES.register]: RegisterPage,
  [ROUTES.verifyEmail]: VerifyEmailPage,
  [ROUTES.forgotPassword]: ForgotPasswordPage,
  [ROUTES.resetPassword]: ResetPasswordPage,
  [ROUTES.account]: AccountPage,
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
  const { catalog, offers, loading, error, reload } = useCatalog();
  const maxLines = catalog?.max_cart_lines ?? DEFAULT_MAX_LINES;
  const cart = useCart(offers, maxLines);

  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const path = usePathname();
  const openedId = productId(path);
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

  return (
    <div className="page" id="top">
      <RouteProgress />
      <IntroSplash />
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
        {Page ? (
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
              setCheckoutOpen(true);
            }}
          />
        ) : path === ROUTES.home || path === ROUTES.shop ? (
          <>
            {path === ROUTES.home ? (
              <Hero offers={offers} categories={categories} onOpenOffer={openProduct} />
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
      </main>

      <SiteFooter />

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
          setCheckoutOpen(true);
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
