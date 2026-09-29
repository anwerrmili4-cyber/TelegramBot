import { useEffect, useState, type ComponentType } from "react";
import { ArrowRight, ShoppingCart } from "lucide-react";
import { CartDrawer } from "@/components/CartDrawer";
import { CatalogSection } from "@/components/CatalogSection";
import { CheckoutDialog } from "@/components/CheckoutDialog";
import { Hero } from "@/components/Hero";
import { IntroSplash } from "@/components/IntroSplash";
import { HowItWorks } from "@/components/HowItWorks";
import { ProductDialog } from "@/components/ProductDialog";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { useCart } from "@/hooks/useCart";
import { useCatalog } from "@/hooks/useCatalog";
import { money, plural } from "@/lib/format";
import { ROUTES, usePathname } from "@/lib/router";
import { AccountPage } from "@/pages/AccountPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import type { Offer } from "@/types";

const PAGES: Record<string, ComponentType | undefined> = {
  [ROUTES.login]: LoginPage,
  [ROUTES.register]: RegisterPage,
  [ROUTES.verifyEmail]: VerifyEmailPage,
  [ROUTES.forgotPassword]: ForgotPasswordPage,
  [ROUTES.resetPassword]: ResetPasswordPage,
  [ROUTES.account]: AccountPage,
};

const DEFAULT_MAX_LINES = 12;

export default function App() {
  const { catalog, offers, loading, error, reload } = useCatalog();
  const maxLines = catalog?.max_cart_lines ?? DEFAULT_MAX_LINES;
  const cart = useCart(offers, maxLines);

  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [openOffer, setOpenOffer] = useState<Offer | null>(null);
  const Page = PAGES[usePathname()];

  // Closing the last line should not leave an empty drawer or dialog on screen.
  useEffect(() => {
    if (!cart.lines.length) {
      setCheckoutOpen(false);
    }
  }, [cart.lines.length]);

  return (
    <div className="page" id="top">
      <IntroSplash />
      <SiteHeader cartCount={cart.count} cartTotalMillimes={cart.totalMillimes} onOpenCart={() => setCartOpen(true)} />

      <main>
        {Page ? (
          <Page />
        ) : (
          <>
            <Hero />
            <CatalogSection
              offers={offers}
              categories={catalog?.categories ?? []}
              loading={loading}
              error={error}
              cart={cart}
              onReload={reload}
              onOpenOffer={setOpenOffer}
            />
            <HowItWorks />
          </>
        )}
      </main>

      <SiteFooter />

      {cart.count && !cartOpen && !checkoutOpen && !openOffer && !Page ? (
        <button type="button" className="cart-bar" onClick={() => setCartOpen(true)}>
          <ShoppingCart size={18} aria-hidden="true" />
          <span>
            {cart.count} {plural(cart.count, "article", "articles")} · {money(cart.totalMillimes)}
          </span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      ) : null}

      <ProductDialog
        offer={openOffer}
        inCart={openOffer ? cart.quantityOf(openOffer.id) : 0}
        cartIsFull={cart.isFull}
        onClose={() => setOpenOffer(null)}
        onAdd={(offer, quantity) => cart.add(offer, quantity)}
        onBuyNow={(offer, quantity) => {
          if (!cart.quantityOf(offer.id)) cart.add(offer, quantity);
          setOpenOffer(null);
          setCheckoutOpen(true);
        }}
      />

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
