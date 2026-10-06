import AiManagerPage from "./pages/AiManagerPage.jsx";
import ActivityPage from "./pages/ActivityPage.jsx";
import ApiProductsPage from "./pages/ApiProductsPage.jsx";
import ProviderHistoryPage from "./pages/ProviderHistoryPage.jsx";
import BinanceWalletPage from "./pages/BinanceWalletPage.jsx";
import CatalogPage from "./pages/CatalogPage.jsx";
import CustomersPage from "./pages/CustomersPage.jsx";
import DepositsPage from "./pages/DepositsPage.jsx";
import FinancePage from "./pages/FinancePage.jsx";
import InteractionsPage from "./pages/InteractionsPage.jsx";
import InventoryPage from "./pages/InventoryPage.jsx";
import OrdersPage from "./pages/OrdersPage.jsx";
import ProductRequestsPage from "./pages/ProductRequestsPage.jsx";
import ResellerClientsPage from "./pages/ResellerClientsPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import SupportPage from "./pages/SupportPage.jsx";
import WarrantiesPage from "./pages/WarrantiesPage.jsx";
import WithdrawalsPage from "./pages/WithdrawalsPage.jsx";

export { CatalogPage };
export { ActionButton, Empty, Field, FilterBar, Modal, OperationsSummary, PageHeader, Pagination, date, useRemoteList } from "./admin-kit.jsx";
export { InventoryPage, ProductRequestsPage, SupportPage, WarrantiesPage };

export default function AdminPage({
  page,
  data,
  onAction,
  onHealthCheck,
  onNavigate,
  setToast,
}) {
  const props = { data, onAction, onHealthCheck, onNavigate, setToast };
  if (page === "binance-wallet") return <BinanceWalletPage {...props} />;
  if (page === "ai-manager") return <AiManagerPage {...props} />;
  if (page === "orders") return <OrdersPage {...props} />;
  if (page === "catalog") return <CatalogPage {...props} />;
  if (page === "api-products") return <ApiProductsPage {...props} />;
  if (page === "provider-history") return <ProviderHistoryPage {...props} />;
  if (page === "api-clients") return <ResellerClientsPage {...props} />;
  if (page === "inventory") return <InventoryPage {...props} />;
  if (page === "customers") return <CustomersPage {...props} />;
  if (page === "deposits") return <DepositsPage {...props} />;
  if (page === "withdrawals") return <WithdrawalsPage {...props} />;
  if (page === "warranties") return <WarrantiesPage {...props} />;
  if (page === "finance") return <FinancePage {...props} />;
  if (page === "support") return <SupportPage {...props} />;
  if (page === "product-requests") return <ProductRequestsPage {...props} />;
  if (page === "interactions") return <InteractionsPage {...props} />;
  if (page === "activity") return <ActivityPage {...props} />;
  if (page === "settings") return <SettingsPage {...props} />;
  return null;
}
