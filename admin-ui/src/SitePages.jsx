import InventoryPage from "./pages/InventoryPage.jsx";
import ProductRequestsPage from "./pages/ProductRequestsPage.jsx";
import SiteCatalogPage from "./pages/SiteCatalogPage.jsx";
import SiteCustomersPage from "./pages/SiteCustomersPage.jsx";
import SiteDepositsPage from "./pages/SiteDepositsPage.jsx";
import SiteMailPage from "./pages/SiteMailPage.jsx";
import SiteNotificationsPage from "./pages/SiteNotificationsPage.jsx";
import SiteOrdersPage from "./pages/SiteOrdersPage.jsx";
import SiteOverviewPage from "./pages/SiteOverviewPage.jsx";
import SiteReviewsPage from "./pages/SiteReviewsPage.jsx";
import SiteSettingsPage from "./pages/SiteSettingsPage.jsx";
import SupportPage from "./pages/SupportPage.jsx";
import WarrantiesPage from "./pages/WarrantiesPage.jsx";

export const SITE_PAGE_IDS = new Set(["site-overview", "site-orders", "site-deposits", "site-catalog", "site-inventory", "site-customers", "site-support", "site-product-requests", "site-warranties", "site-reviews", "site-mail", "site-notifications", "site-settings"]);

export default function SitePage({ page, ...props }) {
  if (page === "site-overview") return <SiteOverviewPage {...props} />;
  if (page === "site-orders") return <SiteOrdersPage {...props} />;
  if (page === "site-deposits") return <SiteDepositsPage {...props} />;
  if (page === "site-catalog") return <SiteCatalogPage {...props} />;
  if (page === "site-inventory") return <InventoryPage {...props} shared />;
  if (page === "site-customers") return <SiteCustomersPage {...props} />;
  if (page === "site-support") return <SupportPage {...props} channel="tn_site" />;
  if (page === "site-product-requests") return <ProductRequestsPage {...props} channel="tn_site" />;
  if (page === "site-warranties") return <WarrantiesPage {...props} channel="tn_site" />;
  if (page === "site-reviews") return <SiteReviewsPage {...props} />;
  if (page === "site-mail") return <SiteMailPage {...props} />;
  if (page === "site-notifications") return <SiteNotificationsPage {...props} />;
  if (page === "site-settings") return <SiteSettingsPage {...props} />;
  return null;
}
