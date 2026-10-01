import { useState } from "react";
import {
  Boxes,
  Copy,
  Download,
  Eye,
  ToggleLeft,
  ToggleRight,
  X,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";

export default function InventoryPage({ data, onAction, shared = false }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("");
  const [offerId, setOfferId] = useState("");
  const [page, setPage] = useState(1);
  const [revealed, setRevealed] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/inventory", {
    search,
    search_field: searchField,
    status,
    offer_id: offerId,
    page,
    per_page: 25,
  });
  const reveal = async (item) => {
    const response = await fetch("/admin", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-Dashboard-Write-Token": data.dashboard_write_token || "",
      },
      body: new URLSearchParams({
        action: "reveal_inventory",
        inventory_id: item.reference_id,
      }),
    });
    const payload = await response.json();
    if (response.ok) setRevealed({ item, value: payload.value });
  };
  return (
    <>
      <PageHeader
        title={shared ? "Inventaire partagé" : "Inventaire"}
        description={shared
          ? "Même stock que le bot Telegram. Ajouter ou retirer une ligne change le nombre disponible des deux côtés."
          : "Stock chiffré, réservations et livraisons automatiques."}
        actions={
          <a
            className="action-button secondary"
            href="/admin/api/inventory-export"
          >
            <Download size={16} />
            Exporter CSV
          </a>
        }
      />
      <FilterBar
        search={search}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["preview", "Aperçu masqué"], ["reference_id", "ID référence"], ["product_id", "ID produit"], ["order_id", "ID commande"]]}
        resultCount={result.total}
        setSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
        placeholder="Référence, produit, commande ou aperçu…"
      >
        <select
          value={offerId}
          onChange={(event) => {
            setOfferId(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Tous les produits</option>
          {data.services
            ?.flatMap((service) => service.offers || [])
            .map((offer, index) => (
              <option
                value={offer.id}
                key={offer.id || `${offer.name}-${index}`}
              >
                {offer.name}
              </option>
            ))}
        </select>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Tous les états</option>
          {["available", "reserved", "delivered", "disabled"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Référence</th>
                <th>Produit</th>
                <th>Aperçu</th>
                <th>État</th>
                <th>Commande</th>
                <th>Date</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={item.reference_id}>
                  <td>#{item.reference_id}</td>
                  <td>#{item.offer_id}</td>
                  <td>
                    <code>{item.masked_preview || "••••••"}</code>
                  </td>
                  <td>
                    <span className={`status ${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.reserved_order_id || item.delivered_order_id || "—"}
                  </td>
                  <td>{date(item.created_at)}</td>
                  <td>
                    <div className="inline-actions">
                      <button title="Révéler" onClick={() => reveal(item)}>
                        <Eye size={15} />
                      </button>
                      <button
                        title="Activer/désactiver"
                        onClick={() =>
                          onAction({
                            action: "toggle_inventory",
                            inventory_id: item.reference_id,
                            disabled: item.status === "disabled" ? "0" : "1",
                          })
                        }
                      >
                        {item.status === "disabled" ? (
                          <ToggleLeft size={16} />
                        ) : (
                          <ToggleRight size={16} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !result.items.length && <Empty icon={Boxes} title="Inventaire vide" />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {revealed && (
        <Modal
          title={`Référence #${revealed.item.reference_id}`}
          onClose={() => setRevealed(null)}
        >
          <pre className="secret-preview">{revealed.value}</pre>
          <div className="dialog-actions">
            <ActionButton
              icon={Copy}
              onClick={() => navigator.clipboard.writeText(revealed.value)}
            >
              Copier
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}
