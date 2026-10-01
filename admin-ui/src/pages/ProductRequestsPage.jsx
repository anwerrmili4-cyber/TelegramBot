import { useEffect, useState } from "react";
import SupportInbox from "../SupportInbox.jsx";
import { PageHeader, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";

export default function ProductRequestsPage({ onAction, onNavigate, data, channel = "" }) {
  const initialRequest = new URLSearchParams(window.location.search).get("request") || "";
  const [search, setSearch] = useState(initialRequest);
  const [searchField, setSearchField] = useState(initialRequest ? "ticket_id" : "all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [targetTicketId, setTargetTicketId] = useState(initialRequest);
  const site = channel === "tn_site";
  useEffect(() => {
    const navigateToRequest = (event) => {
      const pageId = site ? "site-product-requests" : "product-requests";
      if (event.detail?.page !== pageId || event.detail?.entityId == null) return;
      const id = String(event.detail.entityId);
      setTargetTicketId(id);
      setSearchField("ticket_id");
      setSearch(id);
      setStatus("");
      setPage(1);
    };
    window.addEventListener("admin:navigate", navigateToRequest);
    return () => window.removeEventListener("admin:navigate", navigateToRequest);
  }, [site]);
  const [result, loading] = useRemoteList("/admin/api/tickets", {
    category: "catalog_request", status, search, search_field: searchField, page, per_page: 25,
    ...(site ? { channel: "tn_site" } : {}),
  }, { refreshInterval: 4000 });
  const scoped = (payload) => onAction({ ...payload, channel: site ? "tn_site" : "bot" });
  const summary = result.summary || {};
  return <div className="product-requests-page">
    <PageHeader
      title="Demandes produits"
      description={site ? "Produits demandés par les clients d’ourblackmarket. Le bot ne voit pas ces demandes." : "Les produits recherchés par vos clients, pour repérer les prochaines offres à ajouter."}
    />
    <OperationsSummary items={[
      ["Total demandes", summary.total || 0, "accent"],
      ["À traiter", summary.actionable || 0, "warning"],
      ["Réponse client", summary.waiting_customer || 0, "info"],
      ["Terminées", summary.completed || 0, "success"],
    ]} />
    <SupportInbox result={result} loading={loading} search={search}
      setSearch={(value) => { setSearch(value); setPage(1); }}
      searchField={searchField} setSearchField={(value) => { setSearchField(value); setPage(1); }}
      status={status} setStatus={(value) => { setStatus(value); setPage(1); }}
      targetTicketId={targetTicketId}
      pagination={<Pagination value={result} onChange={setPage} />} onAction={scoped}
      onNavigate={onNavigate}
      writeToken={data?.dashboard_write_token || ""}
      variant="product-requests"
      showBulkActions={false} />
  </div>;
}
