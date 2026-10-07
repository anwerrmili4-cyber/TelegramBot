import { lazyPage, PageSuspense } from "./lazy-page.jsx";

export { ActionButton, Empty, Field, FilterBar, Modal, OperationsSummary, PageHeader, Pagination, date, useRemoteList } from "./admin-kit.jsx";

const PAGES = {
  "binance-wallet": lazyPage(() => import("./pages/BinanceWalletPage.jsx")),
  "ai-manager": lazyPage(() => import("./pages/AiManagerPage.jsx")),
  orders: lazyPage(() => import("./pages/OrdersPage.jsx")),
  catalog: lazyPage(() => import("./pages/CatalogPage.jsx")),
  "api-products": lazyPage(() => import("./pages/ApiProductsPage.jsx")),
  "provider-history": lazyPage(() => import("./pages/ProviderHistoryPage.jsx")),
  "api-clients": lazyPage(() => import("./pages/ResellerClientsPage.jsx")),
  inventory: lazyPage(() => import("./pages/InventoryPage.jsx")),
  customers: lazyPage(() => import("./pages/CustomersPage.jsx")),
  deposits: lazyPage(() => import("./pages/DepositsPage.jsx")),
  withdrawals: lazyPage(() => import("./pages/WithdrawalsPage.jsx")),
  warranties: lazyPage(() => import("./pages/WarrantiesPage.jsx")),
  finance: lazyPage(() => import("./pages/FinancePage.jsx")),
  support: lazyPage(() => import("./pages/SupportPage.jsx")),
  "product-requests": lazyPage(() => import("./pages/ProductRequestsPage.jsx")),
  interactions: lazyPage(() => import("./pages/InteractionsPage.jsx")),
  activity: lazyPage(() => import("./pages/ActivityPage.jsx")),
  settings: lazyPage(() => import("./pages/SettingsPage.jsx")),
};

export default function AdminPage({
  page,
  data,
  onAction,
  onHealthCheck,
  onNavigate,
  setToast,
}) {
  const Page = PAGES[page];
  if (!Page) return null;
  return (
    <PageSuspense>
      <Page data={data} onAction={onAction} onHealthCheck={onHealthCheck} onNavigate={onNavigate} setToast={setToast} />
    </PageSuspense>
  );
}
