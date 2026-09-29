import { useEffect, useState, type ComponentType } from "react";
import { ArrowRight, ShoppingCart } from "lucide-react";
import { CartDrawer } from "@/components/CartDrawer";
import { CatalogSection } from "@/components/CatalogSection";
import { CheckoutDialog } from "@/components/CheckoutDialog";
import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/HowItWorks";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { useCart } from "@/hooks/useCart";
import { useCatalog } from "@/hooks/useCatalog";
import { WHATSAPP_FALLBACK } from "@/lib/api";
import { money, plural } from "@/lib/format";
import { ROUTES, usePathname } from "@/lib/router";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";

const AUTH_PAGES: Record<string, ComponentType | undefined> = {
  [ROUTES.login]: LoginPage,
  [ROUTES.register]: RegisterPage,
  [ROUTES.forgotPassword]: ForgotPasswordPage,
  [ROUTES.resetPassword]: ResetPasswordPage,
};

const DEFAULT_MAX_LINES = 12;
const DEFAULT_METHODS = [
  { id: "d17", label: "D17" },
  { id: "flouci", label: "Flouci" },
];

export default function App() {
  const { catalog, offers, loading, error, reload } = useCatalog();
  const maxLines = catalog?.max_cart_lines ?? DEFAULT_MAX_LINES;
  const cart = useCart(offers, maxLines);
  const whatsappNumber = catalog?.whatsapp || WHATSAPP_FALLBACK;

  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const AuthPage = AUTH_PAGES[usePathname()];

  // Closing the last line should not leave an empty drawer or dialog on screen.
  useEffect(() => {
    if (!cart.lines.length) {
      setCheckoutOpen(false);
    }
  }, [cart.lines.length]);

  return (
    <div className="page" id="top">
      <SiteHeader
        cartCount={cart.count}
        cartTotalMillimes={cart.totalMillimes}
        whatsappNumber={whatsappNumber}
        onOpenCart={() => setCartOpen(true)}
      />

      <main>
        {AuthPage ? (
          <AuthPage />
        ) : (
          <>
            <Hero whatsappNumber={whatsappNumber} />
            <CatalogSection
              offers={offers}
              categories={catalog?.categories ?? []}
              loading={loading}
              error={error}
              cart={cart}
              onReload={reload}
            />
            <HowItWorks />
          </>
        )}
      </main>

      <SiteFooter whatsappNumber={whatsappNumber} />

      {cart.count && !cartOpen && !checkoutOpen && !AuthPage ? (
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
        paymentMethods={catalog?.payment_methods ?? DEFAULT_METHODS}
        onClose={() => setCheckoutOpen(false)}
        onConfirmed={cart.clear}
      />
    </div>
  );
}
