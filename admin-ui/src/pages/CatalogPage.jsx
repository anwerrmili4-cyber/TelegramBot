import { useEffect, useRef, useState } from "react";
import {
  Archive,
  Boxes,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Cloud,
  Columns3,
  Copy,
  Database,
  Edit3,
  GripVertical,
  List,
  PackagePlus,
  Plus,
  ShoppingBag,
  SlidersHorizontal,
  ToggleLeft,
  ToggleRight,
  Trash2,
} from "lucide-react";
import { readPreference, savePreference } from "../control-utils.js";
import { catalogQueryString, filterCatalogServices, paginateCatalogServices, readCatalogQuery, reorderIds } from "../catalog-utils.js";
import { SERVICE_COLORS, providerLabel, money, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination } from "../admin-kit.jsx";

function OfferForm({ services, offer, onAction, onClose, defaultChannel = "both" }) {
  const currentChannels = offer?.sales_channels || ["bot"];
  const [form, setForm] = useState({
    service_id: offer?.service_id || services[0]?.id || "",
    name: offer?.name || "",
    emoji: offer?.custom_emoji_id || offer?.emoji || "",
    price: offer?.price ?? "",
    bulk_quantity: offer?.bulk_quantity ?? 0,
    bulk_unit_price: offer?.bulk_unit_price ?? "",
    description: offer?.description || "",
    note: offer?.note || "",
    period_value: offer?.period_value ?? offer?.period_days ?? 30,
    period_unit: offer?.period_unit || "days",
    warranty_value: offer?.warranty_value ?? offer?.warranty_days ?? (offer?.note === "NW" ? 0 : (Number((offer?.note || "").match(/\d+/)?.[0]) || 0)),
    warranty_unit: offer?.warranty_unit || "days",
    delivery_delay: offer?.delivery_delay || "Instantané après confirmation",
    low_stock_threshold: offer?.low_stock_threshold ?? 5,
    auto_delivery: offer?.auto_delivery !== false,
    initial_inventory: "",
    sales_channel: "bot",
    name_ar: offer?.name_ar || "",
    description_ar: offer?.description_ar || "",
  });
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event) => {
    event.preventDefault();
    const action = offer ? "update_offer" : "add_offer";
    const factors = { days: 1, months: 30, years: 365 };
    const periodDays = Number(form.period_value || 0) * factors[form.period_unit];
    const warrantyDays = Number(form.warranty_value || 0) * factors[form.warranty_unit];
    const payload = {
      ...form,
      period_days: periodDays,
      warranty_days: warrantyDays,
      note: warrantyDays === 0 ? "NW" : `${form.warranty_value} ${form.warranty_unit}`,
      action,
      custom_emoji_id: form.emoji,
      ...(offer
        ? { offer_id: offer.id, sort_order: offer.sort_order || 0 }
        : {}),
      auto_delivery: form.auto_delivery ? "on" : "",
    };
    if (await onAction(payload)) onClose();
  };
  return (
    <Modal
      title={offer ? "Modifier le produit" : "Nouveau produit"}
      onClose={onClose}
      wide
    >
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Service">
            <select
              value={form.service_id}
              onChange={(event) => set("service_id", event.target.value)}
            >
              {services.map((service) => (
                <option value={service.id} key={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Nom">
            <input
              required
              value={form.name}
              onChange={(event) => set("name", event.target.value)}
            />
          </Field>
          <Field label="Emoji / Icône">
            <input
              value={form.emoji}
              onChange={(event) => set("emoji", event.target.value)}
              placeholder="Ex: 🤖, 🍿, ✈️..."
              style={{ maxWidth: 100, textAlign: "center", fontSize: "1.2rem" }}
            />
          </Field>
          <Field label="Canal de vente">
            <select value={form.sales_channel} onChange={(event) => set("sales_channel", event.target.value)}>
              <option value="bot">Bot uniquement</option>
            </select>
          </Field>
          <Field label="Prix">
            <input
              required
              min="0"
              step="0.01"
              type="number"
              value={form.price}
              onChange={(event) => set("price", event.target.value)}
            />
          </Field>
          <Field label="Quantité en gros">
            <input
              min="0"
              step="1"
              type="number"
              value={form.bulk_quantity}
              onChange={(event) => set("bulk_quantity", event.target.value)}
              placeholder="0 = désactivé"
            />
          </Field>
          <Field label="Prix en gros / unité">
            <input
              min="0"
              step="0.01"
              type="number"
              value={form.bulk_unit_price}
              onChange={(event) => set("bulk_unit_price", event.target.value)}
              placeholder="Prix réduit par unité"
            />
          </Field>
          <Field label="Seuil de stock">
            <input
              min="0"
              type="number"
              value={form.low_stock_threshold}
              onChange={(event) =>
                set("low_stock_threshold", event.target.value)
              }
            />
          </Field>
          <Field label="Description" wide>
            <textarea
              value={form.description}
              onChange={(event) => set("description", event.target.value)}
            />
          </Field>
          <Field label="Nom arabe" wide>
            <input dir="rtl" value={form.name_ar} onChange={(event) => set("name_ar", event.target.value)} placeholder="اسم المنتج بالعربية" />
          </Field>
          <Field label="Description arabe" wide>
            <textarea dir="rtl" value={form.description_ar} onChange={(event) => set("description_ar", event.target.value)} placeholder="وصف المنتج بالعربية" />
          </Field>
          <Field label="Période">
            <div className="duration-input">
              <input type="number" min="1" value={form.period_value} onChange={(event) => set("period_value", event.target.value)} required />
              <select value={form.period_unit} onChange={(event) => set("period_unit", event.target.value)}>
                <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
              </select>
            </div>
          </Field>
          <Field label="Garantie (0 = NW)">
            <div className="duration-input">
              <input type="number" min="0" value={form.warranty_value} onChange={(event) => set("warranty_value", event.target.value)} required />
              <select value={form.warranty_unit} onChange={(event) => set("warranty_unit", event.target.value)}>
                <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
              </select>
            </div>
          </Field>
          {!offer && (
            <Field label="Stock initial" wide>
              <textarea
                value={form.initial_inventory}
                onChange={(event) =>
                  set("initial_inventory", event.target.value)
                }
                placeholder="#1&#10;Email: …&#10;Password: …"
              />
            </Field>
          )}
          <Field label="Livraison">
            <input
              value={form.delivery_delay}
              onChange={(event) => set("delivery_delay", event.target.value)}
            />
          </Field>
          <Field label="Automatisation">
            <label className="switch">
              <input
                type="checkbox"
                checked={form.auto_delivery}
                onChange={(event) => set("auto_delivery", event.target.checked)}
              />
              <span /> Livraison automatique
            </label>
          </Field>
        </div>
        <div className="dialog-actions">
          <ActionButton secondary onClick={onClose} type="button">
            Annuler
          </ActionButton>
          <ActionButton icon={Check} type="submit">
            Enregistrer
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}

export default function CatalogPage({ data, onAction }) {
  const initialCatalogState = useRef(null);
  if (!initialCatalogState.current) {
    const query = readCatalogQuery(typeof window === "undefined" ? "" : window.location.search);
    if (typeof window !== "undefined" && !new URLSearchParams(window.location.search).has("view")) query.view = readPreference("catalog-view", query.view);
    if (typeof window !== "undefined" && !new URLSearchParams(window.location.search).has("sort")) query.sort = readPreference("catalog-sort", query.sort);
    initialCatalogState.current = query;
  }
  const initial = initialCatalogState.current;
  const [search, setSearch] = useState(initial.search);
  const [category, setCategory] = useState(initial.category);
  const [searchField, setSearchField] = useState(initial.searchField);
  const [offer, setOffer] = useState(undefined);
  const [showOffer, setShowOffer] = useState(false);
  const [showService, setShowService] = useState(false);
  const [serviceName, setServiceName] = useState("");
  const [serviceNameAr, setServiceNameAr] = useState("");
  const [serviceChannel, setServiceChannel] = useState("bot");
  const [stockOffer, setStockOffer] = useState(null);
  const [stock, setStock] = useState("");
  const [editService, setEditService] = useState(null);
  const [editServiceName, setEditServiceName] = useState("");
  const [editServiceNameAr, setEditServiceNameAr] = useState("");
  const [editServiceChannel, setEditServiceChannel] = useState("both");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selectedOffers, setSelectedOffers] = useState(new Set());
  const [bulkOfferAction, setBulkOfferAction] = useState(null);
  const [bulkOfferValue, setBulkOfferValue] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [statusFilter, setStatusFilter] = useState(initial.status);
  const [stockFilter, setStockFilter] = useState(initial.stock);
  const [sourceFilter, setSourceFilter] = useState(initial.source);
  const [sortBy, setSortBy] = useState(initial.sort);
  const [viewMode, setViewMode] = useState(initial.view);
  const [page, setPage] = useState(initial.page);
  const [pageSize, setPageSize] = useState(initial.pageSize);
  const [collapsedServices, setCollapsedServices] = useState(new Set());
  const [draggedCatalogItem, setDraggedCatalogItem] = useState(null);
  const [dragTarget, setDragTarget] = useState(null);
  const filterResetReady = useRef(false);

  const startEditService = (service) => {
    setEditService(service);
    setEditServiceName(service.name || "");
    setEditServiceNameAr(service.name_ar || "");
    setEditServiceChannel("bot");
  };

  const updateService = async (event) => {
    event.preventDefault();
    if (!editService) return;
    if (
      await onAction({
        action: "update_service",
        service_id: editService.id,
        name: editServiceName,
        name_ar: editServiceNameAr,
        emoji: editService.emoji || "",
        suffix_emoji: editService.suffix_emoji || "",
        sales_channel: editServiceChannel,
      })
    )
      setEditService(null);
  };
  const createService = async (event) => {
    event.preventDefault();
    if (
      await onAction({
        action: "add_service",
        name: serviceName,
        name_ar: serviceNameAr,
        sales_channel: serviceChannel,
      })
    )
      setShowService(false);
  };
  const allServices = data.services || [];
  const allOffers = allServices.flatMap((service) => service.offers || []);
  const totalStock = allOffers.filter((item) => !item.unlimited_stock).reduce((total, item) => total + Math.max(0, Number(item.stock || 0)), 0);
  const unlimitedOffers = allOffers.filter((item) => item.unlimited_stock).length;
  const activeOffers = allOffers.filter((item) => item.active !== 0).length;
  const catalogFilters = { search, category, searchField, status: statusFilter, stock: stockFilter, source: sourceFilter, sort: sortBy };
  const visibleServices = filterCatalogServices(allServices, catalogFilters, providerLabel);
  const pagination = paginateCatalogServices(visibleServices, page, pageSize);
  const paginatedServices = pagination.items;
  const visibleOfferIds = paginatedServices.flatMap((service) => (service.offers || []).map((item) => item.id));
  const canReorder = sortBy === "default" && !search && statusFilter === "all" && stockFilter === "all" && sourceFilter === "all";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = catalogQueryString({ ...catalogFilters, view: viewMode, page: pagination.page, pageSize }, window.location.search);
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${query}${window.location.hash}`);
  }, [search, category, searchField, statusFilter, stockFilter, sourceFilter, sortBy, viewMode, pagination.page, pageSize]);
  useEffect(() => {
    if (!filterResetReady.current) { filterResetReady.current = true; return; }
    setPage(1);
  }, [search, category, searchField, statusFilter, stockFilter, sourceFilter, sortBy, pageSize]);
  useEffect(() => { if (page !== pagination.page) setPage(pagination.page); }, [page, pagination.page]);
  const toggleOfferSelection = (offerId) => setSelectedOffers((current) => {
    const next = new Set(current);
    if (next.has(offerId)) next.delete(offerId); else next.add(offerId);
    return next;
  });
  const setCatalogView = (value) => { setViewMode(value); savePreference("catalog-view", value); };
  const setCatalogSort = (value) => { setSortBy(value); savePreference("catalog-sort", value); };
  const resetAdvanced = () => { setStatusFilter("all"); setStockFilter("all"); setSourceFilter("all"); setCatalogSort("default"); };
  const toggleServiceCollapse = (serviceId) => setCollapsedServices((current) => {
    const next = new Set(current);
    if (next.has(serviceId)) next.delete(serviceId); else next.add(serviceId);
    return next;
  });
  const persistCatalogOrder = async (itemType, draggedId, targetId, serviceId = null) => {
    const source = itemType === "service"
      ? allServices.map((service) => service.id)
      : (allServices.find((service) => Number(service.id) === Number(serviceId))?.offers || []).map((item) => item.id);
    const orderedIds = reorderIds(source, draggedId, targetId);
    if (orderedIds.every((id, index) => id === Number(source[index]))) return;
    await onAction({ action: "reorder_catalog", item_type: itemType, ordered_ids: orderedIds.join(","), service_id: serviceId || "" });
  };
  const dropCatalogItem = async (itemType, targetId, serviceId = null) => {
    const dragged = draggedCatalogItem;
    setDraggedCatalogItem(null);
    setDragTarget(null);
    if (!dragged || dragged.type !== itemType || (itemType === "offer" && Number(dragged.serviceId) !== Number(serviceId))) return;
    await persistCatalogOrder(itemType, dragged.id, targetId, serviceId);
  };
  const moveCatalogItemWithKeyboard = (itemType, itemId, direction, serviceId = null) => {
    const source = itemType === "service"
      ? allServices.map((service) => service.id)
      : (allServices.find((service) => Number(service.id) === Number(serviceId))?.offers || []).map((item) => item.id);
    const index = source.map(Number).indexOf(Number(itemId));
    const targetIndex = index + direction;
    if (index < 0 || targetIndex < 0 || targetIndex >= source.length) return;
    persistCatalogOrder(itemType, itemId, source[targetIndex], serviceId);
  };
  const applyBulkOfferAction = async () => {
    if (!bulkOfferAction || !selectedOffers.size) return;
    const toggle = ["activate", "deactivate"].includes(bulkOfferAction);
    const operation = bulkOfferAction === "price" ? "price_percent" : bulkOfferAction === "move" ? "move_service" : bulkOfferAction;
    const result = await onAction(toggle ? {
      action: "bulk_toggle_offers", offer_ids: [...selectedOffers].join(","), active: bulkOfferAction === "activate" ? "1" : "0",
    } : {
      action: "bulk_update_offers", offer_ids: [...selectedOffers].join(","), operation, value: bulkOfferValue,
    });
    if (result) setSelectedOffers(new Set());
    setBulkOfferAction(null);
    setBulkOfferValue("");
  };
  return (
    <>
      <PageHeader
        title="Mon catalogue"
        description="Organisez, filtrez et publiez vos produits Telegram."
        actions={<>
          <ActionButton secondary icon={Plus} onClick={() => setShowService(true)}>Nouveau service</ActionButton>
          <ActionButton icon={PackagePlus} onClick={() => { setOffer(undefined); setShowOffer(true); }}>Nouveau produit</ActionButton>
        </>}
      />
      <div className="catalog-command-bar">
        <div><span>Collections</span><strong>{allServices.length}</strong><small>catégories actives</small></div>
        <div><span>Offres</span><strong>{allOffers.length}</strong><small>{activeOffers} visibles dans le bot</small></div>
        <div><span>Stock mesuré</span><strong>{totalStock}</strong><small>unités prêtes à livrer</small></div>
        <div><span>Stock illimité</span><strong>{unlimitedOffers}</strong><small>offres sans plafond</small></div>
        <div><span>Sélection</span><strong>{selectedOffers.size}</strong><small>pour une action groupée</small></div>
      </div>
      <div className="workspace-tabs" role="group" aria-label="Collections du catalogue"><button aria-pressed={!category} onClick={() => { setCategory(""); setSelectedOffers(new Set()); }}>Toutes les collections</button>{(data.services || []).map((service) => <button key={service.id} aria-pressed={category === String(service.id)} onClick={() => { setCategory(String(service.id)); setSelectedOffers(new Set()); }}>{service.name}<small> {(service.offers || []).length}</small></button>)}</div>
      <div className="catalog-toolbar">
        <FilterBar search={search} setSearch={setSearch} searchField={searchField} setSearchField={setSearchField} options={[["all", "Tout type"], ["service", "Service"], ["product", "Produit"], ["provider", "API fournisseur"]]} resultCount={visibleServices.length} placeholder="Rechercher un nom, ID, prix, stock, API…" />
        <div className="catalog-toolbar-actions">
          <button type="button" className={showAdvanced ? "active" : ""} aria-expanded={showAdvanced} onClick={() => setShowAdvanced((value) => !value)}><SlidersHorizontal size={16} /> Réglages avancés</button>
          <div className="catalog-view-switch" role="group" aria-label="Mode d’affichage"><button type="button" aria-pressed={viewMode === "grid"} title="Vue en grille" onClick={() => setCatalogView("grid")}><Columns3 size={16} /></button><button type="button" aria-pressed={viewMode === "list"} title="Vue en liste" onClick={() => setCatalogView("list")}><List size={16} /></button></div>
        </div>
      </div>
      <div className={`catalog-advanced ${showAdvanced ? "visible" : ""}`} aria-hidden={!showAdvanced}>
        <label><span>Visibilité</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Tous les statuts</option><option value="active">Actifs</option><option value="inactive">Désactivés</option></select></label>
        <label><span>Disponibilité</span><select value={stockFilter} onChange={(event) => setStockFilter(event.target.value)}><option value="all">Tous les stocks</option><option value="available">En stock</option><option value="empty">Stock épuisé</option><option value="unlimited">Stock illimité</option></select></label>
        <label><span>Source</span><select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="all">Toutes les sources</option><option value="internal">Stock interne</option><option value="api">API fournisseur</option></select></label>
        <label><span>Trier par</span><select value={sortBy} onChange={(event) => setCatalogSort(event.target.value)}><option value="default">Ordre du catalogue</option><option value="name">Nom A–Z</option><option value="offers">Nombre de produits</option><option value="stock">Stock disponible</option></select></label>
        <button type="button" onClick={resetAdvanced}>Réinitialiser</button>
      </div>
      <div className={`catalog-bulk-bar ${selectedOffers.size ? "visible" : ""}`}>
        <div><span>{selectedOffers.size}</span><strong>produit(s) sélectionné(s)</strong><button type="button" onClick={() => setSelectedOffers(new Set(visibleOfferIds))}>Tout sélectionner</button><button type="button" onClick={() => setSelectedOffers(new Set())}>Effacer</button></div>
        <div><ActionButton secondary icon={ToggleRight} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("activate")}>Activer</ActionButton><ActionButton secondary icon={ToggleLeft} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("deactivate")}>Désactiver</ActionButton><ActionButton secondary icon={CircleDollarSign} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("price")}>Prix</ActionButton><ActionButton secondary icon={ShoppingBag} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("move")}>Service</ActionButton><ActionButton danger icon={Archive} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("archive")}>Archiver</ActionButton></div>
      </div>
      {canReorder && <div className="catalog-order-hint"><GripVertical size={15} /><span>Glissez les poignées pour réordonner. Utilisez les flèches haut/bas lorsque la poignée est sélectionnée.</span></div>}
      <div className={`catalog-react-grid catalog-table-template ${viewMode === "list" ? "catalog-list-view" : ""}`}>
        {paginatedServices.map((service, serviceIndex) => {
          const providers = [...new Set((service.offers || []).map((item) => item.supplier_provider || "").filter(Boolean))];
          const collapsed = collapsedServices.has(service.id);
          const serviceOffers = service.offers || [];
          const selectedInService = serviceOffers.filter((item) => selectedOffers.has(item.id)).length;
          const allServiceSelected = serviceOffers.length > 0 && selectedInService === serviceOffers.length;
          const toggleServiceSelection = () => setSelectedOffers((current) => {
            const next = new Set(current);
            serviceOffers.forEach((item) => { if (allServiceSelected) next.delete(item.id); else next.add(item.id); });
            return next;
          });
          return (
          <section
            className={`data-panel catalog-collection ${collapsed ? "collapsed" : ""} ${dragTarget === `service-${service.id}` ? "drag-target" : ""} ${service.active === 0 ? "inactive" : ""}`}
            key={service.id}
            style={{ "--service-accent": SERVICE_COLORS[serviceIndex % SERVICE_COLORS.length], "--catalog-index": serviceIndex }}
            onDragOver={(event) => { if (canReorder && draggedCatalogItem?.type === "service") { event.preventDefault(); setDragTarget(`service-${service.id}`); } }}
            onDrop={(event) => { event.preventDefault(); dropCatalogItem("service", service.id); }}
          >
            <header className="panel-heading catalog-collection-heading">
              <div className="catalog-collection-title">
                {canReorder && !category && <button type="button" className="catalog-drag-handle" draggable onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; setDraggedCatalogItem({ type: "service", id: service.id }); }} onDragEnd={() => { setDraggedCatalogItem(null); setDragTarget(null); }} onKeyDown={(event) => { if (["ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); moveCatalogItemWithKeyboard("service", service.id, event.key === "ArrowUp" ? -1 : 1); } }} aria-label={`Réordonner la collection ${service.name}`} title="Glisser pour réordonner"><GripVertical size={17} /></button>}
                <button type="button" className="catalog-collection-toggle" onClick={() => toggleServiceCollapse(service.id)} aria-expanded={!collapsed} aria-label={`${collapsed ? "Déplier" : "Replier"} ${service.name}`}><ChevronRight size={16} /></button>
                <div>
                  <span className="eyebrow">Collection · {serviceOffers.length} produit(s) · {service.total_stock || 0} en stock</span>
                  <h2>{service.name}</h2>
                  <div className="service-providers">
                    {providers.length ? providers.map((provider) => (
                      <span key={provider}><Cloud size={11} />{providerLabel(provider)}</span>
                    )) : (
                      <span className="internal"><Database size={11} />Stock interne</span>
                    )}
                    {service.active === 0 && <span className="status cancelled">Désactivée</span>}
                  </div>
                </div>
              </div>
              <div className="catalog-service-actions">
                <button title="Modifier le service" onClick={() => startEditService(service)}>
                  <Edit3 size={16} />
                </button>
                <button title="Activer/désactiver" onClick={() => onAction({ action: "toggle_service", service_id: service.id })}>
                  {service.active === 0 ? <ToggleLeft /> : <ToggleRight />}
                </button>
                <button className="danger" title="Supprimer le service" onClick={() => setDeleteTarget({ type: "service", item: service })}>
                  <Trash2 size={16} />
                </button>
              </div>
            </header>
            <div className="catalog-offers">
              <div className="catalog-offers-content">
                {serviceOffers.length ? (
                <div className="responsive-table">
                  <table className="catalog-offer-table">
                    <thead>
                      <tr>
                        <th className="catalog-col-select"><button className={`offer-select ${allServiceSelected ? "checked" : ""}`} type="button" onClick={toggleServiceSelection} aria-pressed={allServiceSelected} aria-label={`${allServiceSelected ? "Désélectionner" : "Sélectionner"} tous les produits de ${service.name}`}>{allServiceSelected ? <Check size={13} /> : null}</button></th>
                        {canReorder && <th className="catalog-col-drag" aria-label="Ordre" />}
                        <th>Produit</th>
                        <th>Prix</th>
                        <th>Stock</th>
                        <th className="catalog-col-secondary">Source</th>
                        <th className="catalog-col-secondary">Canal</th>
                        <th>Statut</th>
                        <th className="catalog-col-actions" aria-label="Actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {serviceOffers.map((item, index) => (
                        <tr
                          className={`offer-row ${selectedOffers.has(item.id) ? "selected" : ""} ${dragTarget === `offer-${item.id}` ? "drag-target" : ""} ${item.active === 0 ? "inactive" : ""}`}
                          key={item.id || `${service.id}-${item.name}-${index}`}
                          onDragOver={(event) => { if (canReorder && draggedCatalogItem?.type === "offer" && Number(draggedCatalogItem.serviceId) === Number(service.id)) { event.preventDefault(); setDragTarget(`offer-${item.id}`); } }}
                          onDrop={(event) => { event.preventDefault(); dropCatalogItem("offer", item.id, service.id); }}
                        >
                          <td className="catalog-col-select"><button className="offer-select" type="button" onClick={() => toggleOfferSelection(item.id)} aria-pressed={selectedOffers.has(item.id)} aria-label={`${selectedOffers.has(item.id) ? "Désélectionner" : "Sélectionner"} ${item.name}`}>{selectedOffers.has(item.id) ? <Check size={13} /> : null}</button></td>
                          {canReorder && <td className="catalog-col-drag"><button type="button" className="catalog-drag-handle offer-drag-handle" draggable onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.effectAllowed = "move"; setDraggedCatalogItem({ type: "offer", id: item.id, serviceId: service.id }); }} onDragEnd={() => { setDraggedCatalogItem(null); setDragTarget(null); }} onKeyDown={(event) => { if (["ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); moveCatalogItemWithKeyboard("offer", item.id, event.key === "ArrowUp" ? -1 : 1, service.id); } }} aria-label={`Réordonner le produit ${item.name}`} title="Glisser pour réordonner"><GripVertical size={15} /></button></td>}
                          <td className="catalog-col-name">
                            <strong>{item.name}</strong>
                            {Number(item.bulk_quantity || 0) > 0 && item.bulk_unit_price != null && (
                              <small>Gros : {money(item.bulk_unit_price, data.currency)} / unité dès {item.bulk_quantity}</small>
                            )}
                          </td>
                          <td className="catalog-col-price"><strong>{money(item.price, data.currency)}</strong></td>
                          <td className="catalog-col-stock">
                            {item.unlimited_stock ? <span className="offer-stock unlimited">Illimité</span> : <span className={`offer-stock ${Number(item.stock || 0) > 0 ? "" : "empty"}`}>{item.stock || 0}</span>}
                          </td>
                          <td className="catalog-col-secondary">
                            <span className={`offer-provider ${item.supplier_provider ? "api" : "internal"}`}>
                              {item.supplier_provider ? <Cloud size={11} /> : <Database size={11} />}
                              {providerLabel(item.supplier_provider)}
                            </span>
                          </td>
                          <td className="catalog-col-secondary"><span className="offer-channel">Bot</span></td>
                          <td><span className={`status ${item.active === 0 ? "cancelled" : "delivered"}`}>{item.active === 0 ? "Masqué" : "Visible"}</span></td>
                          <td className="catalog-col-actions">
                            <div className="offer-actions">
                              <button title="Ajouter du stock" onClick={() => setStockOffer(item)}>
                                <Boxes size={15} />
                              </button>
                              <button title="Dupliquer" onClick={() => onAction({ action: "duplicate_offer", offer_id: item.id })}>
                                <Copy size={15} />
                              </button>
                              <button title="Modifier" onClick={() => { setOffer(item); setShowOffer(true); }}>
                                <Edit3 size={15} />
                              </button>
                              <button title="Activer/désactiver" onClick={() => onAction({ action: "toggle_offer", offer_id: item.id })}>
                                {item.active === 0 ? <ToggleLeft size={17} /> : <ToggleRight size={17} />}
                              </button>
                              <button className="danger" title="Supprimer le produit" onClick={() => setDeleteTarget({ type: "offer", item })}>
                                <Trash2 size={15} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                ) : (
                  <div className="catalog-collection-empty"><PackagePlus size={16} /><span>Aucun produit dans cette collection.</span><button type="button" onClick={() => { setOffer(undefined); setShowOffer(true); }}>Ajouter un produit</button></div>
                )}
              </div>
            </div>
          </section>
          );
        })}
      </div>
      {pagination.total > 0 && <nav className="catalog-pagination" aria-label="Pagination du catalogue"><span>{pagination.total} produit(s) · Page {pagination.page} sur {pagination.pages}</span><label>Afficher <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><div><button type="button" disabled={pagination.page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronLeft size={16} /> Précédent</button><button type="button" disabled={pagination.page >= pagination.pages} onClick={() => setPage((value) => Math.min(pagination.pages, value + 1))}>Suivant <ChevronRight size={16} /></button></div></nav>}
      {!visibleServices.length && (
        <Empty
          icon={ShoppingBag}
          title={search ? "Aucun résultat" : "Catalogue vide"}
          text={search ? "Essayez un autre nom, produit ou fournisseur API." : "Créez votre premier service puis ajoutez des produits."}
        />
      )}
      {showOffer && (
        <OfferForm
          services={data.services || []}
          offer={offer}
          onAction={onAction}
          onClose={() => setShowOffer(false)}
          defaultChannel="bot"
        />
      )}
      {bulkOfferAction && <Modal title="Confirmer l’action groupée" onClose={() => { setBulkOfferAction(null); setBulkOfferValue(""); }}><div className="bulk-confirm"><span className={["deactivate", "archive"].includes(bulkOfferAction) ? "deactivate" : "activate"}>{bulkOfferAction === "activate" ? <ToggleRight size={28} /> : bulkOfferAction === "price" ? <CircleDollarSign size={28} /> : bulkOfferAction === "move" ? <ShoppingBag size={28} /> : bulkOfferAction === "archive" ? <Archive size={28} /> : <ToggleLeft size={28} />}</span><strong>{{ activate: "Activer", deactivate: "Désactiver", price: "Modifier le prix de", move: "Déplacer", archive: "Archiver" }[bulkOfferAction]} {selectedOffers.size} produit(s) ?</strong>{bulkOfferAction === "price" && <Field label="Variation en pourcentage"><input type="number" min="-90" max="500" step="0.1" value={bulkOfferValue} onChange={(event) => setBulkOfferValue(event.target.value)} placeholder="Ex. 10 ou -5" /></Field>}{bulkOfferAction === "move" && <Field label="Service de destination"><select value={bulkOfferValue} onChange={(event) => setBulkOfferValue(event.target.value)}><option value="">Choisir un service</option>{(data.services || []).map((service) => <option value={service.id} key={service.id}>{service.name}</option>)}</select></Field>}<p>{bulkOfferAction === "archive" ? "Les produits disparaîtront du catalogue. Cette action pourra être restaurée depuis le journal pendant 24 heures." : "La modification sera auditée et pourra être restaurée depuis le journal pendant 24 heures."}</p><div><ActionButton secondary onClick={() => { setBulkOfferAction(null); setBulkOfferValue(""); }}>Annuler</ActionButton><ActionButton danger={["deactivate", "archive"].includes(bulkOfferAction)} icon={Check} disabled={["price", "move"].includes(bulkOfferAction) && !bulkOfferValue} onClick={applyBulkOfferAction}>Confirmer</ActionButton></div></div></Modal>}
      {showService && (
        <Modal title="Nouveau service" onClose={() => setShowService(false)}>
          <form onSubmit={createService}>
            <div className="form-grid">
              <Field label="Nom">
                <input
                  required
                  value={serviceName}
                  onChange={(event) => setServiceName(event.target.value)}
                />
              </Field>
              <Field label="Nom arabe" wide>
                <input dir="rtl" value={serviceNameAr} onChange={(event) => setServiceNameAr(event.target.value)} />
              </Field>
              <Field label="Canal" wide>
                <select value={serviceChannel} onChange={(event) => setServiceChannel(event.target.value)}>
                  <option value="bot">Bot uniquement</option>
                </select>
              </Field>
            </div>
            <div className="dialog-actions">
              <ActionButton type="submit" icon={Plus}>
                Créer
              </ActionButton>
            </div>
          </form>
        </Modal>
      )}
      {editService && (
        <Modal title={`Modifier le service · ${editService.name}`} onClose={() => setEditService(null)}>
          <form onSubmit={updateService}>
            <div className="form-grid">
              <Field label="Nom">
                <input
                  required
                  value={editServiceName}
                  onChange={(event) => setEditServiceName(event.target.value)}
                />
              </Field>
              <Field label="Nom arabe" wide>
                <input dir="rtl" value={editServiceNameAr} onChange={(event) => setEditServiceNameAr(event.target.value)} />
              </Field>
              <Field label="Canal" wide>
                <select value={editServiceChannel} onChange={(event) => setEditServiceChannel(event.target.value)}>
                  <option value="bot">Bot uniquement</option>
                </select>
              </Field>
            </div>
            <div className="dialog-actions">
              <ActionButton type="submit" icon={Check}>
                Enregistrer
              </ActionButton>
            </div>
          </form>
        </Modal>
      )}
      {stockOffer && (
        <Modal
          title={`Stock · ${stockOffer.name}`}
          onClose={() => setStockOffer(null)}
        >
          <Field label="Éléments à chiffrer">
            <textarea
              value={stock}
              onChange={(event) => setStock(event.target.value)}
              placeholder="#1&#10;Compte: …"
            />
          </Field>
          <div className="dialog-actions">
            <ActionButton
              icon={PackagePlus}
              onClick={async () => {
                if (
                  await onAction({
                    action: "add_inventory",
                    offer_id: stockOffer.id,
                    items: stock,
                  })
                )
                  setStockOffer(null);
              }}
            >
              Ajouter
            </ActionButton>
          </div>
        </Modal>
      )}
      {deleteTarget && (
        <Modal
          title={deleteTarget.type === "service" ? "Supprimer le service" : "Supprimer le produit"}
          onClose={() => setDeleteTarget(null)}
        >
          <div className="delete-confirmation">
            <span><Trash2 size={22} /></span>
            <div>
              <h4>Supprimer « {deleteTarget.item.name} » ?</h4>
              <p>
                {deleteTarget.type === "service"
                  ? `Le service et ses ${deleteTarget.item.offer_count || 0} produit(s) disparaîtront du catalogue. Les commandes historiques seront conservées.`
                  : "Le produit disparaîtra du catalogue et du bot. Les commandes historiques seront conservées."}
              </p>
            </div>
          </div>
          <div className="dialog-actions">
            <ActionButton secondary onClick={() => setDeleteTarget(null)}>Annuler</ActionButton>
            <ActionButton
              danger
              icon={Trash2}
              onClick={async () => {
                const payload = deleteTarget.type === "service"
                  ? { action: "archive_service", service_id: deleteTarget.item.id }
                  : { action: "archive_offer", offer_id: deleteTarget.item.id };
                if (await onAction(payload)) setDeleteTarget(null);
              }}
            >
              Supprimer
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}
