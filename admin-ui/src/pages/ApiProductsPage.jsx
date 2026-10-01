import { useEffect, useRef, useState } from "react";
import {
  Archive,
  Check,
  CheckCircle2,
  Cloud,
  Edit3,
  Globe2,
  KeyRound,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { supplierMonogram, money, date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar } from "../admin-kit.jsx";

export default function ApiProductsPage({ data, onAction, setToast }) {
  const [provider, setProvider] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState("catalog");
  const [providerError, setProviderError] = useState("");
  const providerRequest = useRef(0);
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(false);
  const [providerMeta, setProviderMeta] = useState([]);
  const [providerHealth, setProviderHealth] = useState({});
  const [checkingAll, setCheckingAll] = useState(false);
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [usageFilter, setUsageFilter] = useState("all");
  const [comparison, setComparison] = useState(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const loadProvider = async (providerId, { showToast = false, selectCatalog = true } = {}) => {
    if (!providerId) return false;
    const requestId = selectCatalog ? ++providerRequest.current : null;
    const startedAt = performance.now();
    if (selectCatalog) { setLoading(true); setCatalog(null); }
    setProviderHealth((current) => ({
      ...current,
      [providerId]: { ...current[providerId], status: "checking", error: "" },
    }));
    try {
      const response = await fetch(
        `/admin/api/reseller-products?provider=${encodeURIComponent(providerId)}`,
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "API indisponible");
      if (selectCatalog && requestId === providerRequest.current) setCatalog(payload);
      setProviderHealth((current) => ({
        ...current,
        [providerId]: {
          status: "online",
          latency: Math.max(1, Math.round(performance.now() - startedAt)),
          balance: payload.balance,
          currency: payload.currency || "USDT",
          products: payload.products?.length || 0,
          inStock: (payload.products || []).filter((item) => Number(item.stock || 0) > 0).length,
          used: payload.used_count ?? payload.selected_count ?? 0,
          checkedAt: new Date().toISOString(),
          error: "",
        },
      }));
      return true;
    } catch (error) {
      if (selectCatalog && requestId === providerRequest.current) setCatalog(null);
      setProviderHealth((current) => ({
        ...current,
        [providerId]: {
          ...current[providerId],
          status: "offline",
          latency: Math.max(1, Math.round(performance.now() - startedAt)),
          checkedAt: new Date().toISOString(),
          error: error.message,
        },
      }));
      if (showToast) setToast({ type: "error", title: "Fournisseur indisponible", message: error.message });
      return false;
    } finally {
      if (selectCatalog && requestId === providerRequest.current) setLoading(false);
    }
  };
  const load = () => loadProvider(provider, { showToast: true, selectCatalog: true });
  useEffect(() => {
    fetch("/admin/api/reseller-providers", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Configuration fournisseurs indisponible");
        setProviderMeta(payload.providers || []);
        setProvider((current) => current || (payload.providers || []).find((item) => item.configured)?.id || "");
      })
      .catch((error) => setProviderError(error.message));
  }, []);
  useEffect(() => {
    if (provider) load();
  }, [provider]);
  const testAllProviders = async () => {
    const configured = providerMeta.filter((item) => item.configured);
    if (!configured.length) {
      setToast({ type: "warning", title: "Aucune API configurée", message: "Ajoutez au moins une clé fournisseur dans Railway." });
      return;
    }
    setCheckingAll(true);
    const results = await Promise.all(configured.map((item) => loadProvider(item.id, {
      selectCatalog: item.id === provider,
    })));
    const online = results.filter(Boolean).length;
    setToast({
      type: online === configured.length ? "success" : "warning",
      title: "Diagnostic terminé",
      message: `${online}/${configured.length} fournisseur(s) opérationnel(s).`,
    });
    setCheckingAll(false);
  };
  const comparePrices = async () => {
    setComparisonLoading(true);
    try {
      const response = await fetch(
        "/admin/api/reseller-comparison?refresh=1",
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Comparaison indisponible");
      }
      setComparison(payload);
      if (payload.method !== "external_ai") {
        setToast({
          type: "warning",
          title: "Mode de secours utilisé",
          message: "Configurez HP_AI_API_URL, HP_AI_API_KEY et HP_AI_MODELS dans Railway.",
        });
      }
    } catch (error) {
      setToast({ type: "error", title: "Comparaison impossible", message: error.message });
    } finally {
      setComparisonLoading(false);
    }
  };
  const chooseComparedOffer = async (offer) => {
    setProvider(offer.provider);
    try {
      const response = await fetch(
        `/admin/api/reseller-products?provider=${encodeURIComponent(offer.provider)}`,
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Produit indisponible");
      setCatalog(payload);
      const product = (payload.products || []).find(
        (item) => String(item.id) === String(offer.product_id),
      );
      if (!product) throw new Error("Ce produit n’est plus disponible chez le fournisseur.");
      setEditing(product);
    } catch (error) {
      setToast({ type: "error", title: "Sélection impossible", message: error.message });
    }
  };
  const catalogProducts = catalog?.products || [];
  const usedCount = catalog?.used_count ?? catalogProducts.filter((product) => product.enabled).length;
  const unusedCount = catalog?.unused_count ?? catalogProducts.length - usedCount;
  const visibleProducts = catalogProducts.filter((product) => {
    if (usageFilter === "used" && !product.enabled) return false;
    if (usageFilter === "unused" && product.enabled) return false;
    const searchable = {
      name: `${product.display_name || ""} ${product.name || ""}`,
      product_id: `${product.id || ""}`,
      description: product.description || "",
    };
    const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
    return !search || haystack.toLowerCase().includes(search.toLowerCase());
  }).sort((left, right) => Number(Boolean(right.enabled)) - Number(Boolean(left.enabled)));
  const activeProvider = providerMeta.find((item) => item.id === provider);
  const supplierName = catalog?.supplier_name || activeProvider?.name || provider || "";
  const health = providerHealth[provider] || {};
  const connectionState = !provider
    ? ""
    : loading || health.status === "checking"
      ? "checking"
      : health.status || (catalog ? "online" : "unknown");
  const connectionLabel = {
    online: "Catalogue synchronisé",
    checking: "Synchronisation…",
    offline: health.error || "Connexion interrompue",
    unknown: "En attente de synchronisation",
  }[connectionState] || "";
  const usageRatio = catalogProducts.length ? Math.round((usedCount / catalogProducts.length) * 100) : 0;
  const saveProduct = async (payload) => {
    const result = await onAction(payload);
    if (result) await loadProvider(provider, { selectCatalog: true });
    return result;
  };
  return (
    <>
      <PageHeader
        title="Fournisseurs & API"
        description="Connectez les fournisseurs et publiez leurs produits dans votre boutique."
        actions={
          <div className="inline-actions">
            <ActionButton icon={Sparkles} onClick={comparePrices} disabled={comparisonLoading || !providerMeta.some((item) => item.configured)}>
              {comparisonLoading ? "Analyse IA…" : "Comparer les prix avec l’IA"}
            </ActionButton>
            <ActionButton secondary icon={RefreshCw} onClick={load} disabled={!provider || loading}>
              Synchroniser
            </ActionButton>
          </div>
        }
      />
      <div className="workspace-tabs supplier-workspace-tabs" role="group" aria-label="Espace fournisseurs">{[["catalog", "Catalogue fournisseur"], ["health", "Connexions & diagnostics"], ["keys", "Clés clients"], ["connectors", "Connecteurs personnalisés"]].map(([id, label]) => <button key={id} aria-pressed={workspaceTab === id} onClick={() => setWorkspaceTab(id)}>{label}</button>)}</div>
      {providerError && <p className="control-error" role="alert">{providerError}</p>}
      {workspaceTab === "health" && <section className="provider-health-center">

        <header>
          <div><span className="comparison-kicker"><Cloud size={14} /> Centre de santé API</span><h2>État des fournisseurs externes</h2><p>Testez les connexions uniquement à la demande pour éviter les appels inutiles.</p></div>
          <ActionButton secondary icon={RefreshCw} onClick={testAllProviders} disabled={checkingAll || !providerMeta.length}>{checkingAll ? "Diagnostic…" : "Tester toutes les API"}</ActionButton>
        </header>
        <div className="provider-health-grid">
          {providerMeta.map((item) => {
            const health = providerHealth[item.id] || {};
            const state = !item.configured ? "unconfigured" : health.status || "unknown";
            return <article className={`provider-health-card ${state} ${provider === item.id ? "selected" : ""}`} key={item.id}>
              <button className="provider-health-main" onClick={() => setProvider(item.id)}>
                <div className="provider-health-title"><span className="provider-health-icon"><Cloud size={17} /></span><div><strong>{item.name}</strong><small>{item.configured ? "Clé configurée" : "Non configurée"}</small></div><i /></div>
                <div className="provider-health-stats"><span><small>Solde</small><b>{health.balance == null ? "—" : money(health.balance, health.currency)}</b></span><span><small>Produits</small><b>{health.products ?? "—"}</b></span><span><small>Utilisés</small><b>{health.used ?? "—"}</b></span><span><small>En stock</small><b>{health.inStock ?? "—"}</b></span></div>
                <div className="provider-health-foot"><span>{state === "online" ? `Opérationnelle · ${health.latency} ms` : state === "offline" ? "Connexion échouée" : state === "checking" ? "Test en cours…" : state === "unconfigured" ? "Ajoutez la clé dans Railway" : "Pas encore testée"}</span>{health.checkedAt && <small>{date(health.checkedAt)}</small>}</div>
                {health.error && <p title={health.error}>{health.error}</p>}
              </button>
              <button className="provider-test-button" disabled={!item.configured || state === "checking"} onClick={() => loadProvider(item.id, { showToast: true, selectCatalog: item.id === provider })}>{state === "checking" ? <RefreshCw className="spin" size={13} /> : <ShieldCheck size={13} />}Tester</button>
            </article>;
          })}
        </div>
      </section>}
      {workspaceTab === "catalog" && comparison && (
        <section className="ai-comparison-panel">
          <header>
            <div>
              <span className="comparison-kicker"><Sparkles size={14} /> Comparateur intelligent</span>
              <h2>{comparison.compared_group_count} service(s) commun(s) détecté(s)</h2>
              <p>
                {comparison.method === "external_ai"
                  ? `Analyse IA avec ${comparison.ai_model}`
                  : "Analyse locale de secours — configurez votre API IA pour une détection sémantique"}
                {` · ${comparison.catalog_product_count} produits · ${comparison.provider_count} fournisseurs`}
              </p>
            </div>
            <button className="comparison-close" onClick={() => setComparison(null)} aria-label="Fermer">
              <X size={17} />
            </button>
          </header>
          {!!comparison.provider_errors?.length && (
            <div className="comparison-warning">
              {comparison.provider_errors.length} fournisseur(s) indisponible(s) pendant l’analyse.
            </div>
          )}
          <div className="comparison-grid">
            {(comparison.groups || []).map((group, groupIndex) => (
              <article className="comparison-card" key={`${group.label}-${groupIndex}`}>
                <div className="comparison-title">
                  <div>
                    <h3>{group.label}</h3>
                    <span>Confiance {Math.round((group.confidence || 0) * 100)}%</span>
                  </div>
                  {!!group.savings_vs_next && (
                    <strong>Économie {money(group.savings_vs_next, group.currency)}</strong>
                  )}
                </div>
                <p>{group.reason}</p>
                <div className="comparison-offers">
                  {group.offers.map((offer) => {
                    const cheapest = offer.item_id === group.cheapest_item_id;
                    return (
                      <div className={cheapest ? "cheapest" : ""} key={offer.item_id}>
                        <div>
                          <span>{offer.provider_name}</span>
                          <small>{offer.name} · {offer.stock > 0 ? `${offer.stock} en stock` : "épuisé"}</small>
                        </div>
                        <strong>{money(offer.price, group.currency)}</strong>
                        {cheapest && <b>Meilleur prix</b>}
                        <button disabled={offer.stock <= 0} onClick={() => chooseComparedOffer(offer)}>
                          Choisir
                        </button>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
          {!comparison.groups?.length && (
            <Empty
              icon={Sparkles}
              title="Aucun service commun détecté"
              text="Les catalogues disponibles ne contiennent pas encore d’offres suffisamment équivalentes."
            />
          )}
        </section>
      )}
      {workspaceTab === "catalog" && (
        <div className="supplier-workbench">
          <div className="supplier-dock">
            <div className="supplier-switcher">
              <span className="supplier-switcher-label">Fournisseurs <b>{providerMeta.length}</b></span>
              <div className="supplier-switcher-rail" role="tablist" aria-label="Fournisseurs">
              {providerMeta.map((item) => {
                const itemHealth = providerHealth[item.id] || {};
                const meta = !item.configured
                  ? "À configurer"
                  : itemHealth.products != null
                    ? `${itemHealth.products} produits`
                    : "Connecté";
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={provider === item.id}
                    disabled={!item.configured}
                    className={provider === item.id ? "active" : ""}
                    onClick={() => setProvider(item.id)}
                  >
                    <span className="supplier-monogram">{supplierMonogram(item.name || item.id)}</span>
                    <span className="supplier-switcher-copy">
                      <strong>{item.name || item.id}</strong>
                      <small>{meta}</small>
                    </span>
                  </button>
                );
              })}
              {!providerMeta.length && (
                <p className="control-caption">{providerError ? "Liste indisponible." : "Aucun fournisseur disponible."}</p>
              )}
              </div>
            </div>
            {provider && (
              <>
                <header className="supplier-command">
                  <div className="supplier-identity">
                    <span className="supplier-monogram lg">{supplierMonogram(supplierName || activeProvider?.name || provider)}</span>
                    <div>
                      {activeProvider?.name && activeProvider.name !== supplierName && (
                        <span className="supplier-provider-kicker">{activeProvider.name}</span>
                      )}
                      <strong>{supplierName || provider}</strong>
                      <small className={`supplier-live ${connectionState}`} title={health.error || undefined}>
                        <i />
                        {connectionLabel}
                      </small>
                    </div>
                  </div>
                  <dl className="supplier-metrics">
                    <div>
                      <dt>Solde</dt>
                      <dd>{catalog ? money(catalog.balance, catalog.currency || "USDT") : "—"}</dd>
                    </div>
                    <div>
                      <dt>Utilisés</dt>
                      <dd>{catalog ? usedCount : "—"}</dd>
                    </div>
                    <div>
                      <dt>Disponibles</dt>
                      <dd>{catalog ? catalogProducts.length : "—"}</dd>
                    </div>
                  </dl>
                  <div className="supplier-meter" role="img" aria-label={`${usageRatio}% du catalogue est publié dans la boutique`}>
                    <span style={{ width: `${usageRatio}%` }} />
                  </div>
                </header>
                <div className="supplier-toolbar">
                  <div className="supplier-segments" role="group" aria-label="Classer les produits API">
                    <button type="button" aria-pressed={usageFilter === "all"} className={usageFilter === "all" ? "active" : ""} onClick={() => setUsageFilter("all")}>
                      Tous <b>{catalogProducts.length}</b>
                    </button>
                    <button type="button" aria-pressed={usageFilter === "used"} className={usageFilter === "used" ? "active" : ""} onClick={() => setUsageFilter("used")}>
                      Utilisés <b>{usedCount}</b>
                    </button>
                    <button type="button" aria-pressed={usageFilter === "unused"} className={usageFilter === "unused" ? "active" : ""} onClick={() => setUsageFilter("unused")}>
                      Non utilisés <b>{unusedCount}</b>
                    </button>
                  </div>
                  <FilterBar
                    search={search}
                    setSearch={setSearch}
                    searchField={searchField}
                    setSearchField={setSearchField}
                    options={[["all", "Tout"], ["name", "Nom du produit"], ["product_id", "ID fournisseur"], ["description", "Description"]]}
                    resultCount={visibleProducts.length}
                    placeholder="Nom, ID fournisseur ou description…"
                  />
                </div>
              </>
            )}
          </div>
          {!provider && (
            <div className="supplier-empty">
              <Cloud size={38} />
              <h3>Connectez votre premier fournisseur</h3>
              <p>Les produits apparaîtront après configuration d’une connexion. Consultez les diagnostics ou ajoutez un connecteur personnalisé.</p>
              <ActionButton secondary onClick={() => setWorkspaceTab("connectors")}>Ouvrir les connecteurs</ActionButton>
            </div>
          )}
          {provider && (
            <section className="data-panel supplier-products">
              {!!visibleProducts.length && (
                <div className="responsive-table">
                  <table className="supplier-product-table">
                    <thead>
                      <tr>
                        <th>Produit</th>
                        <th className="num">Achat</th>
                        <th className="num">Vente</th>
                        <th className="num">Marge</th>
                        <th className="num">Stock</th>
                        <th>Utilisation</th>
                        <th className="supplier-col-actions" aria-label="Actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {visibleProducts.map((product) => {
                        const wholesale = Number(product.wholesale_price);
                        const retail = Number(product.retail_price);
                        const margin = Number.isFinite(wholesale) && retail > 0 ? retail - wholesale : null;
                        const marginPercent = margin != null && wholesale > 0 ? Math.round((margin / wholesale) * 100) : null;
                        const stock = Number(product.stock || 0);
                        const summary = product.description || "Produit fournisseur";
                        return (
                          <tr
                            className={product.enabled ? "api-product-used" : "api-product-unused"}
                            key={product.id}
                            onClick={() => setEditing(product)}
                          >
                            <td>
                              <div className="supplier-product-name">
                                <strong>{product.display_name || product.name}</strong>
                                <small title={summary}>ID {product.id} · {summary}</small>
                              </div>
                            </td>
                            <td className="num">{money(product.wholesale_price, product.currency)}</td>
                            <td className="num"><strong className="supplier-retail">{money(product.retail_price, product.currency)}</strong></td>
                            <td className="num">
                              {margin == null ? "—" : <span className={`supplier-margin ${margin < 0 ? "negative" : ""}`}>{money(margin, product.currency)}{marginPercent != null && <small> {marginPercent}%</small>}</span>}
                            </td>
                            <td className="num">
                              <span className={stock > 0 ? "supplier-stock" : "supplier-stock empty"}>
                                <i />
                                {stock > 0 ? stock.toLocaleString("fr-FR") : "Épuisé"}
                              </span>
                            </td>
                            <td><span className={product.enabled ? "api-usage-badge used" : "api-usage-badge unused"}>{product.enabled ? <CheckCircle2 size={11} /> : <Archive size={11} />}{product.enabled ? "Utilisé" : "Non utilisé"}</span></td>
                            <td className="supplier-col-actions">
                              <div className="inline-actions">
                                <button type="button" aria-label={`Configurer ${product.display_name || product.name}`} title="Configurer" onClick={(event) => { event.stopPropagation(); setEditing(product); }}>
                                  <Edit3 size={15} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {loading && (
                <div className="table-loading">Connexion au fournisseur…</div>
              )}
              {!loading && !visibleProducts.length && (
                <Empty
                  icon={Cloud}
                  title={search || usageFilter !== "all" ? "Aucun résultat" : "Aucun produit API"}
                  text={search || usageFilter !== "all" ? "Essayez un autre nom, identifiant ou filtre." : "Vérifiez la configuration de ce fournisseur."}
                />
              )}
            </section>
          )}
        </div>
      )}
      {workspaceTab === "keys" && <BuyerKeys setToast={setToast} writeToken={data.dashboard_write_token} />}
      {workspaceTab === "connectors" && <CustomExternalApis setToast={setToast} writeToken={data.dashboard_write_token} />}
      {editing && (
        <ApiProductEditor
          product={editing}
          provider={provider}
          services={data.services || []}
          onAction={saveProduct}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function BuyerKeys({ setToast, writeToken }) {
  const [keys, setKeys] = useState([]);
  const [show, setShow] = useState(false);
  const [userId, setUserId] = useState("");
  const [label, setLabel] = useState("Buyer API");
  const [issued, setIssued] = useState("");
  const [revoking, setRevoking] = useState(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const load = () =>
    fetch("/admin/api/buyer-keys", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((payload) => setKeys(payload.keys || []));
  useEffect(() => {
    load();
  }, []);
  const request = async (body) => {
    const response = await fetch("/admin/api/buyer-keys", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Dashboard-Write-Token": writeToken || "",
      },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      setToast({
        type: "error",
        title: "Clé API",
        message: payload.message || payload.error || "Action refusée",
      });
      return null;
    }
    await load();
    return payload;
  };
  return (
    <section className="data-panel buyer-keys">
      <header>
        <div>
          <span className="eyebrow">Accès revendeurs</span>
          <h3>Clés Buyer API</h3>
        </div>
        <ActionButton icon={KeyRound} onClick={() => setShow(true)}>
          Nouvelle clé
        </ActionButton>
      </header>
      <div className="responsive-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Client</th>
              <th>Libellé</th>
              <th>Créée</th>
              <th>Dernière utilisation</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id}>
                <td>#{key.id}</td>
                <td>{key.user_id}</td>
                <td>{key.label}</td>
                <td>{date(key.created_at)}</td>
                <td>{date(key.last_used_at)}</td>
                <td>
                  <button
                    className="row-action"
                    onClick={() => setRevoking(key)}
                    title="Révoquer la clé"
                    aria-label={`Révoquer la clé #${key.id}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!keys.length && <Empty icon={KeyRound} title="Aucune clé active" />}
      {revoking && (
        <Modal title="Révoquer la clé Buyer API" onClose={() => setRevoking(null)}>
          <div className="delete-confirmation"><span><Trash2 size={22} /></span><div><h4>Révoquer la clé #{revoking.id} « {revoking.label} » ?</h4><p>Le client {revoking.user_id} ne pourra plus utiliser cette clé. Cette action est définitive.</p></div></div>
          <div className="dialog-actions"><ActionButton secondary onClick={() => setRevoking(null)}>Annuler</ActionButton><ActionButton danger icon={Trash2} disabled={revokeBusy} onClick={async () => { setRevokeBusy(true); try { if (await request({ action: "revoke", key_id: revoking.id })) setRevoking(null); } finally { setRevokeBusy(false); } }}>Révoquer</ActionButton></div>
        </Modal>
      )}
      {show && (
        <Modal title="Créer une clé Buyer API" onClose={() => setShow(false)}>
          <div className="form-grid">
            <Field label="Telegram ID">
              <input
                type="number"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              />
            </Field>
            <Field label="Libellé">
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
              />
            </Field>
          </div>
          {issued && <pre className="secret-preview">{issued}</pre>}
          <div className="dialog-actions">
            <ActionButton
              icon={KeyRound}
              onClick={async () => {
                const payload = await request({
                  action: "create",
                  user_id: userId,
                  label,
                });
                if (payload)
                  setIssued(
                    payload.key?.secret ||
                      payload.key?.key ||
                      JSON.stringify(payload.key),
                  );
              }}
            >
              Créer
            </ActionButton>
          </div>
        </Modal>
      )}
    </section>
  );
}

function CustomExternalApis({ setToast, writeToken }) {
  const emptyForm = {
    name: "",
    endpoint: "https://",
    method: "GET",
    auth_type: "none",
    auth_header: "X-API-Key",
    secret: "",
    headers: "{}",
    body_template: "",
  };
  const [connectors, setConnectors] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(false);
  const [running, setRunning] = useState(null);
  const [runBody, setRunBody] = useState("");
  const [runResult, setRunResult] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => fetch("/admin/api/external-connectors", {
    credentials: "same-origin",
    cache: "no-store",
  }).then((response) => response.json()).then((payload) => setConnectors(payload.connectors || []));
  useEffect(() => { load(); }, []);
  const post = async (payload) => {
    setBusy(true);
    try {
      const response = await fetch("/admin", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-Dashboard-Write-Token": writeToken || "",
        },
        body: new URLSearchParams(Object.entries(payload).map(([key, value]) => [key, value == null ? "" : String(value)])),
      });
      const result = await response.json();
      if (!response.ok || result.ok === false) {
        const error = new Error(result.message || result.error || `Erreur HTTP ${response.status}`);
        error.payload = result;
        throw error;
      }
      return result;
    } finally {
      setBusy(false);
    }
  };
  const openEditor = (connector = null) => {
    setForm(connector ? {
      connector_id: connector.id,
      name: connector.name,
      endpoint: connector.endpoint,
      method: connector.method,
      auth_type: connector.auth_type,
      auth_header: connector.auth_header || "X-API-Key",
      secret: "",
      headers: JSON.stringify(connector.headers || {}, null, 2),
      body_template: connector.body_template || "",
    } : emptyForm);
    setEditing(true);
  };
  return (
    <section className="data-panel custom-apis">
      <header>
        <div><span className="eyebrow">Connexion libre</span><h3>API personnalisées</h3><p>Ajoutez et utilisez manuellement un endpoint externe sécurisé.</p></div>
        <ActionButton icon={Plus} onClick={() => openEditor()}>Ajouter une API</ActionButton>
      </header>
      <div className="custom-api-grid">
        {connectors.map((connector) => (
          <article key={connector.id}>
            <div className="custom-api-icon"><Globe2 size={20} /></div>
            <div className="custom-api-copy">
              <div><strong>{connector.name}</strong><span className={`method-badge ${connector.method.toLowerCase()}`}>{connector.method}</span></div>
              <code>{connector.endpoint}</code>
              <small>{connector.auth_type === "none" ? "Sans authentification" : connector.auth_type === "bearer" ? "Bearer token chiffré" : `${connector.auth_header} chiffrée`}</small>
            </div>
            <div className="custom-api-actions">
              <button title="Exécuter" onClick={() => { setRunning(connector); setRunBody(connector.body_template || ""); setRunResult(null); }}><Send size={15} /></button>
              <button title="Modifier" onClick={() => openEditor(connector)}><Edit3 size={15} /></button>
              <button className="danger" title="Supprimer" onClick={() => setDeleting(connector)}><Trash2 size={15} /></button>
            </div>
          </article>
        ))}
      </div>
      {!connectors.length && <Empty icon={Globe2} title="Aucune API personnalisée" text="Ajoutez votre premier endpoint HTTPS directement depuis le site." />}
      {editing && (
        <Modal title={form.connector_id ? "Modifier l’API externe" : "Ajouter une API externe"} onClose={() => setEditing(false)} wide>
          <div className="form-grid">
            <Field label="Nom"><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Mon fournisseur" /></Field>
            <Field label="Méthode"><select value={form.method} onChange={(event) => setForm({ ...form, method: event.target.value })}>{["GET", "POST", "PUT", "PATCH", "DELETE"].map((method) => <option key={method}>{method}</option>)}</select></Field>
            <Field label="Endpoint HTTPS" wide><input value={form.endpoint} onChange={(event) => setForm({ ...form, endpoint: event.target.value })} placeholder="https://api.example.com/v1/products" /></Field>
            <Field label="Authentification"><select value={form.auth_type} onChange={(event) => setForm({ ...form, auth_type: event.target.value })}><option value="none">Aucune</option><option value="bearer">Bearer token</option><option value="api_key">Clé API</option></select></Field>
            {form.auth_type === "api_key" && <Field label="Nom de l’en-tête"><input value={form.auth_header} onChange={(event) => setForm({ ...form, auth_header: event.target.value })} /></Field>}
            {form.auth_type !== "none" && <Field label={form.connector_id ? "Nouvelle clé (laisser vide pour conserver)" : "Clé ou token"} wide><input type="password" value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} autoComplete="new-password" /></Field>}
            <Field label="En-têtes JSON" wide><textarea value={form.headers} onChange={(event) => setForm({ ...form, headers: event.target.value })} placeholder={'{"Accept": "application/json"}'} /></Field>
            <Field label="Corps JSON par défaut" wide><textarea value={form.body_template} onChange={(event) => setForm({ ...form, body_template: event.target.value })} placeholder={'{"product_id": "123", "quantity": 1}'} /></Field>
          </div>
          <div className="external-api-notice"><ShieldCheck size={16} /><span>HTTPS public uniquement. Les clés sont chiffrées et ne seront jamais réaffichées.</span></div>
          <div className="dialog-actions"><ActionButton secondary onClick={() => setEditing(false)}>Annuler</ActionButton><ActionButton icon={Check} disabled={busy} onClick={async () => { try { await post({ action: "save_external_connector", ...form }); await load(); setEditing(false); setToast({ title: "API enregistrée", message: "La connexion externe est prête à être testée." }); } catch (error) { setToast({ type: "error", title: "API refusée", message: error.message }); } }}>Enregistrer</ActionButton></div>
        </Modal>
      )}
      {running && (
        <Modal title={`Exécuter · ${running.name}`} onClose={() => setRunning(null)} wide>
          <div className="external-run-meta"><span className={`method-badge ${running.method.toLowerCase()}`}>{running.method}</span><code>{running.endpoint}</code></div>
          {running.method !== "GET" && <Field label="Corps JSON"><textarea value={runBody} onChange={(event) => setRunBody(event.target.value)} /></Field>}
          {runResult && <div className={`external-response ${runResult.ok ? "success" : "error"}`}><header><strong>HTTP {runResult.status}</strong><span>{runResult.duration_ms} ms</span></header><pre>{JSON.stringify(runResult.response, null, 2)}</pre></div>}
          <div className="dialog-actions"><ActionButton icon={Send} disabled={busy} onClick={async () => { try { const result = await post({ action: "run_external_connector", connector_id: running.id, body: runBody }); setRunResult(result); } catch (error) { if (error.payload?.status) setRunResult(error.payload); setToast({ type: "error", title: "Appel API échoué", message: error.message }); } }}>Envoyer la requête</ActionButton></div>
        </Modal>
      )}
      {deleting && (
        <Modal title="Supprimer la connexion API" onClose={() => setDeleting(null)}>
          <div className="delete-confirmation"><span><Trash2 size={22} /></span><div><h4>Supprimer « {deleting.name} » ?</h4><p>L’endpoint et sa clé chiffrée seront définitivement supprimés.</p></div></div>
          <div className="dialog-actions"><ActionButton secondary onClick={() => setDeleting(null)}>Annuler</ActionButton><ActionButton danger icon={Trash2} disabled={busy} onClick={async () => { try { await post({ action: "delete_external_connector", connector_id: deleting.id }); await load(); setDeleting(null); setToast({ title: "API supprimée", message: "La connexion externe a été retirée." }); } catch (error) { setToast({ type: "error", title: "Suppression impossible", message: error.message }); } }}>Supprimer</ActionButton></div>
        </Modal>
      )}
    </section>
  );
}

function ApiProductEditor({ product, provider, services, onAction, onClose }) {
  const [form, setForm] = useState({
    display_name: product.display_name || product.name,
    retail_price: product.retail_price || "",
    service_id: product.service_id || services[0]?.id || "",
    emoji: product.service_emoji || product.custom_emoji_id || product.emoji || "📦",
    enabled: Boolean(product.enabled),
    description: product.description || "",
    warranty: product.warranty || "",
    period_value: product.period_value ?? product.period_days ?? 30,
    period_unit: product.period_unit || "days",
    warranty_value: product.warranty_value ?? product.warranty_days ?? (product.warranty === "NW" ? 0 : (Number((product.warranty || "").match(/\d+/)?.[0]) || 0)),
    warranty_unit: product.warranty_unit || "days",
    delivery_delay: product.delivery_delay || "Instantané après confirmation",
    low_stock_threshold: product.low_stock_threshold || 5,
  });
  const [newServiceName, setNewServiceName] = useState("");
  const [newServiceEmoji, setNewServiceEmoji] = useState("📦");
  const [creatingSvc, setCreatingSvc] = useState(false);
  const isNewService = form.service_id === "__new__";
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));

  const wholesalePrice = Number(product.wholesale_price || 0);
  const retailPrice = Number(form.retail_price || 0);
  const margin = wholesalePrice > 0 && retailPrice > 0
    ? (((retailPrice - wholesalePrice) / wholesalePrice) * 100).toFixed(1)
    : null;
  const marginColor = margin === null ? "var(--muted)" : Number(margin) >= 30 ? "#34d399" : Number(margin) >= 10 ? "#f59e0b" : "#fb7185";

  const handlePublish = async () => {
    let serviceId = form.service_id;
    const activeEmoji = isNewService ? (newServiceEmoji || "📦") : (form.emoji || "📦");
    if (isNewService) {
      if (!newServiceName.trim()) return;
      setCreatingSvc(true);
      try {
        const result = await onAction({
          action: "add_service",
          name: newServiceName.trim(),
          emoji: activeEmoji,
        });
        if (!result) { setCreatingSvc(false); return; }
        serviceId = result.service_id || result.id || "";
        if (!serviceId) { setCreatingSvc(false); return; }
      } catch {
        setCreatingSvc(false);
        return;
      }
      setCreatingSvc(false);
    }
    const factors = { days: 1, months: 30, years: 365 };
    const periodDays = Number(form.period_value || 0) * factors[form.period_unit];
    const warrantyDays = Number(form.warranty_value || 0) * factors[form.warranty_unit];
    if (
      await onAction({
        action: "save_reseller_product",
        provider,
        product_id: product.id,
        ...form,
        period_days: periodDays,
        warranty_days: warrantyDays,
        warranty: warrantyDays === 0 ? "NW" : `${form.warranty_value} ${form.warranty_unit}`,
        service_id: serviceId,
        service_emoji: activeEmoji,
        custom_emoji_id: activeEmoji,
        emoji: activeEmoji,
        enabled: form.enabled ? "1" : "0",
      })
    )
      onClose();
  };

  return (
    <Modal title={product.name} onClose={onClose} wide>
      <div className="detail-grid" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
        <div>
          <span>Prix d'achat (fournisseur)</span>
          <strong>{money(wholesalePrice, product.currency)}</strong>
        </div>
        <div>
          <span>Prix de vente</span>
          <strong style={{ color: retailPrice > 0 ? "#22d3ee" : "var(--muted)" }}>
            {retailPrice > 0 ? money(retailPrice, product.currency) : "Non défini"}
          </strong>
        </div>
        <div>
          <span>Marge bénéficiaire</span>
          <strong style={{ color: marginColor }}>
            {margin !== null ? `${margin}%` : "—"}
          </strong>
        </div>
      </div>
      <div className="form-grid">
        <Field label="Nom public">
          <input
            value={form.display_name}
            onChange={(event) => set("display_name", event.target.value)}
          />
        </Field>
        <Field label="Prix de vente">
          <input
            type="number"
            step="0.01"
            value={form.retail_price}
            onChange={(event) => set("retail_price", event.target.value)}
            placeholder={wholesalePrice > 0 ? `Min. ${wholesalePrice}` : ""}
          />
        </Field>
        <Field label="Service">
          <select
            value={form.service_id}
            onChange={(event) => set("service_id", event.target.value)}
          >
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
            <option disabled>──────────</option>
            <option value="__new__">＋ Nouvelle catégorie…</option>
          </select>
        </Field>
        {!isNewService && (
          <Field label="Emoji / Icône">
            <input
              value={form.emoji}
              onChange={(event) => set("emoji", event.target.value)}
              placeholder="Ex: 🤖, 🍿, ✈️..."
              style={{ maxWidth: 90, textAlign: "center", fontSize: "1.2rem" }}
            />
          </Field>
        )}
        {isNewService && (
          <>
            <Field label="Nom de la catégorie">
              <input
                value={newServiceName}
                onChange={(event) => setNewServiceName(event.target.value)}
                placeholder="Ex. Spotify, Disney+…"
                autoFocus
              />
            </Field>
            <Field label="Emoji">
              <input
                value={newServiceEmoji}
                onChange={(event) => setNewServiceEmoji(event.target.value)}
                style={{ maxWidth: 80, textAlign: "center", fontSize: "1.25rem" }}
              />
            </Field>
          </>
        )}
        <Field label="Publication">
          <label className="switch">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => set("enabled", event.target.checked)}
            />
            <span />
            Visible dans le bot
          </label>
        </Field>
        <Field label="Description" wide>
          <textarea
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
          />
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
        <Field label="Délai de livraison">
          <input
            value={form.delivery_delay}
            onChange={(event) => set("delivery_delay", event.target.value)}
          />
        </Field>
      </div>
      <div className="dialog-actions">
        <ActionButton
          icon={Check}
          disabled={creatingSvc || (isNewService && !newServiceName.trim())}
          onClick={handlePublish}
        >
          {creatingSvc ? "Création…" : "Publier"}
        </ActionButton>
      </div>
    </Modal>
  );
}
