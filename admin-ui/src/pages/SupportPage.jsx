import { useEffect, useState } from "react";
import SupportInbox from "../SupportInbox.jsx";
import { Pagination, useRemoteList } from "../admin-kit.jsx";

export default function SupportPage({ onAction, onNavigate, data, channel = "" }) {
  const initialTicket = new URLSearchParams(window.location.search).get("ticket") || "";
  const [search, setSearch] = useState(initialTicket);
  const [searchField, setSearchField] = useState(initialTicket ? "ticket_id" : "all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [targetTicketId, setTargetTicketId] = useState(initialTicket);
  const site = channel === "tn_site";
  useEffect(() => {
    const navigateToTicket = (event) => {
      const pageId = site ? "site-support" : "support";
      if (event.detail?.page !== pageId || event.detail?.entityId == null) return;
      const id = String(event.detail.entityId);
      setTargetTicketId(id);
      setSearchField("ticket_id");
      setSearch(id);
      setStatus("");
      setPage(1);
    };
    window.addEventListener("admin:navigate", navigateToTicket);
    return () => window.removeEventListener("admin:navigate", navigateToTicket);
  }, [site]);
  const [result, loading] = useRemoteList("/admin/api/tickets", {
    status, search, search_field: searchField, page, per_page: 25,
    ...(site ? { channel: "tn_site", exclude_category: "catalog_request" } : {}),
  }, { refreshInterval: 4000 });
  const scoped = (payload) => onAction({ ...payload, channel: site ? "tn_site" : "bot" });
  return <SupportInbox result={result} loading={loading} search={search}
    setSearch={(value) => { setSearch(value); setPage(1); }}
    searchField={searchField} setSearchField={(value) => { setSearchField(value); setPage(1); }}
    status={status} setStatus={(value) => { setStatus(value); setPage(1); }}
    targetTicketId={targetTicketId}
    pagination={<Pagination value={result} onChange={setPage} />} onAction={scoped}
    onNavigate={onNavigate}
    writeToken={data?.dashboard_write_token || ""} />;
}
