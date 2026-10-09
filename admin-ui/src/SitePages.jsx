import { lazyPage, PageSuspense } from "./lazy-page.jsx";

export const SITE_PAGE_IDS = new Set(["site-overview", "site-orders", "site-deposits", "site-catalog", "site-inventory", "site-customers", "site-support", "site-product-requests", "site-warranties", "site-reviews", "site-mail", "site-notifications", "site-stats", "site-settings"]);

const InventoryPage = lazyPage(() => import("./pages/InventoryPage.jsx"));
const ProductRequestsPage = lazyPage(() => import("./pages/ProductRequestsPage.jsx"));
const SupportPage = lazyPage(() => import("./pages/SupportPage.jsx"));
const WarrantiesPage = lazyPage(() => import("./pages/WarrantiesPage.jsx"));

const PAGES = {
  "site-overview": [lazyPage(() => import("./pages/SiteOverviewPage.jsx")), {}],
  "site-orders": [lazyPage(() => import("./pages/SiteOrdersPage.jsx")), {}],
  "site-deposits": [lazyPage(() => import("./pages/SiteDepositsPage.jsx")), {}],
  "site-catalog": [lazyPage(() => import("./pages/SiteCatalogPage.jsx")), {}],
  "site-inventory": [InventoryPage, { shared: true }],
  "site-customers": [lazyPage(() => import("./pages/SiteCustomersPage.jsx")), {}],
  "site-support": [SupportPage, { channel: "tn_site" }],
  "site-product-requests": [ProductRequestsPage, { channel: "tn_site" }],
  "site-warranties": [WarrantiesPage, { channel: "tn_site" }],
  "site-reviews": [lazyPage(() => import("./pages/SiteReviewsPage.jsx")), {}],
  "site-mail": [lazyPage(() => import("./pages/SiteMailPage.jsx")), {}],
  "site-notifications": [lazyPage(() => import("./pages/SiteNotificationsPage.jsx")), {}],
  "site-stats": [lazyPage(() => import("./pages/SiteStatsPage.jsx")), {}],
  "site-settings": [lazyPage(() => import("./pages/SiteSettingsPage.jsx")), {}],
};

export default function SitePage({ page, ...props }) {
  const entry = PAGES[page];
  if (!entry) return null;
  const [Page, extra] = entry;
  return (
    <PageSuspense>
      <Page {...props} {...extra} />
    </PageSuspense>
  );
}
