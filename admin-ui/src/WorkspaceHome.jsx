import { lazy, Suspense, useEffect, useState } from "react";
import { ArrowUpRight, Boxes, ClipboardList, Cloud, Headphones, Plus, ShieldCheck, Wallet } from "lucide-react";
import BlurText from "./components/bits/BlurText.jsx";
import CountUp from "./components/bits/CountUp.jsx";
import StarBorder from "./components/bits/StarBorder.jsx";
import { LiveRevenue } from "./ControlCenter";

const LightRays = lazy(() => import("./components/bits/LightRays.jsx"));
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

const money = (value, currency) => `${Number(value || 0).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} ${currency || "USDT"}`;

function useAdminVisualPreferences() {
  const [preferences, setPreferences] = useState({ accent: "#5b45c9", light: true, reduced: false });

  useEffect(() => {
    const media = window.matchMedia(REDUCED_MOTION_QUERY);
    const update = () => {
      const styles = getComputedStyle(document.documentElement);
      setPreferences({
        accent: styles.getPropertyValue("--accent").trim() || "#5b45c9",
        light: document.documentElement.dataset.adminTheme !== "dark",
        reduced: media.matches,
      });
    };
    const themeObserver = new MutationObserver(update);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-admin-theme"] });
    media.addEventListener("change", update);
    update();
    return () => {
      themeObserver.disconnect();
      media.removeEventListener("change", update);
    };
  }, []);

  return preferences;
}

function AnimatedNumber({ value }) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return <CountUp to={Number(value)} duration={0.85} />;
}

export default function WorkspaceHome({ data, onNavigate }) {
  const [tab, setTab] = useState("priorities");
  const { accent, light, reduced } = useAdminVisualPreferences();
  const s = data.summary || {};
  const queues = [
    { page: "orders", icon: ClipboardList, title: "Commandes à traiter", count: s.pending_orders, text: "Contrôler les paiements et suivre les livraisons", tone: "amber" },
    { page: "support", icon: Headphones, title: "Demandes de support", count: s.open_tickets, text: "Retrouver les conversations en attente", tone: "blue" },
    { page: "inventory", icon: Boxes, title: "Stock à surveiller", count: s.low_stock_offers, text: "Réapprovisionner les offres sous le seuil", tone: "rose" },
  ];

  return (
    <div className="workspace-home">
      <div className="workspace-home-rays" aria-hidden="true">
        {reduced ? null : (
          <Suspense fallback={null}>
            <LightRays
              raysOrigin="top-right"
              raysColor={accent}
              raysSpeed={0.32}
              lightSpread={0.5}
              rayLength={1.8}
              rayDensity={0.55}
              glow={0.2}
              haze={0.08}
              intensity={light ? 0.2 : 0.28}
              followMouse={false}
              cursorShadow={false}
              clickPulse={false}
              intro
              opacity={0.45}
              maxDevicePixelRatio={1.25}
              lightMode={light}
            />
          </Suspense>
        )}
      </div>

      <div className="page-heading">
        <div>
          <h2>
            <BlurText as="span" text="Accueil" animateBy="words" direction="bottom" blur={7} distance={12} delay={55} stepDuration={0.38} trigger="load" />
          </h2>
          <p>Votre boutique aujourd’hui : ventes, priorités et accès rapides.</p>
        </div>
        <div className="page-actions">
          <StarBorder
            className="primary-button"
            color={accent}
            trailColor={accent}
            backgroundColor="var(--mono-action)"
            textColor="var(--mono-action-text)"
            borderColor="var(--line-bright)"
            duration={7}
            thickness={1}
            glow={0.32}
            trailLength={0.2}
            hover="brighten"
            sparkle={false}
            onClick={() => onNavigate("catalog")}
          >
            <Plus size={16} />Gérer le catalogue
          </StarBorder>
        </div>
      </div>

      <section className="workspace-scoreboard" aria-label="Chiffres clés">
        <div><span>Revenus aujourd’hui</span><strong>{money(s.revenue_today, data.currency)}</strong><small>Commandes encaissées</small></div>
        <div><span>Commandes du jour</span><strong><AnimatedNumber value={s.orders_today} /></strong><small>Activité de la boutique</small></div>
        <div><span>Stock disponible</span><strong><AnimatedNumber value={s.available_inventory} /></strong><small>Unités dans l’inventaire</small></div>
        <div><span>Nouveaux clients</span><strong><AnimatedNumber value={s.new_users_today} /></strong><small>Aujourd’hui</small></div>
      </section>

      <div className="workspace-columns">
        <div className="workspace-main">
          <div className="workspace-tabs" role="group" aria-label="Vue de l’accueil">
            <button aria-pressed={tab === "priorities"} onClick={() => setTab("priorities")}>Mes priorités</button>
            <button aria-pressed={tab === "performance"} onClick={() => setTab("performance")}>Performance</button>
            <button aria-pressed={tab === "recent"} onClick={() => setTab("recent")}>Dernières commandes</button>
          </div>

          {tab === "priorities" && (
            <section className="workspace-inbox">
              <header><span>FILE DE TRAVAIL</span><small>Selon le dernier état synchronisé</small></header>
              {queues.map(({ page, icon: Icon, title, text, count, tone }) => (
                <button key={page} onClick={() => onNavigate(page)}>
                  <span className={`workspace-task-icon ${tone}`}><Icon size={22} /></span>
                  <span className="workspace-task-copy"><strong>{title}</strong><small>{text}</small></span>
                  <b><AnimatedNumber value={count} /></b>
                  <ArrowUpRight size={20} />
                </button>
              ))}
              <footer><ShieldCheck size={16} />Chaque intervention reste reliée à son outil de gestion.</footer>
            </section>
          )}
          {tab === "performance" && <LiveRevenue currency={data.currency} />}
          {tab === "recent" && (
            <section className="workspace-inbox">
              <header><span>COMMANDES RÉCENTES</span><button onClick={() => onNavigate("orders")}>Tout consulter →</button></header>
              {(data.orders || []).slice(0, 6).map((order) => (
                <button key={order.id} onClick={() => onNavigate("orders", order.id)}>
                  <span className="workspace-task-icon"><ClipboardList size={20} /></span>
                  <span className="workspace-task-copy"><strong>#{order.id} · {order.offer_name || "Commande"}</strong><small>{order.username ? `@${order.username}` : `Client ${order.user_id}`}</small></span>
                  <b>{money(order.charged_total ?? Number(order.total_price || 0) + Number(order.wallet_amount || 0), data.currency)}</b>
                  <ArrowUpRight size={18} />
                </button>
              ))}
              {!data.orders?.length && <p className="control-empty">Aucune commande récente à afficher.</p>}
            </section>
          )}

          <section className="workspace-launcher">
            <header><h3>Votre espace de travail</h3><p>Des outils organisés autour de vos opérations.</p></header>
            <div>
              {[["catalog", Boxes, "Catalogue", "Offres, prix et disponibilités"], ["api-products", Cloud, "Fournisseurs", "Connexions et produits externes"], ["deposits", Wallet, "Finance", "Dépôts et vérifications"], ["data-explorer", ClipboardList, "Données", "Rechercher, filtrer, exporter"]].map(([page, Icon, title, text]) => (
                <button key={page} onClick={() => onNavigate(page)}><Icon size={23} /><strong>{title}</strong><small>{text}</small><ArrowUpRight size={18} /></button>
              ))}
            </div>
          </section>
        </div>

        <aside className="workspace-context">
          <div className="workspace-bot-card"><span>VOTRE BOUTIQUE</span><div className="workspace-orbit"><span>↗</span></div><h3>{data.shop_name || "Black Market"}</h3><p>@{data.bot_username || "—"}</p><button onClick={() => onNavigate("control-center")}>Ouvrir le centre de contrôle <ArrowUpRight size={16} /></button></div>
          <section><span className="eyebrow">ACCÈS DIRECT</span><h3>Un espace, tous vos outils.</h3><p>Retrouvez les diagnostics, les préférences et les connexions dans Administration.</p><button onClick={() => onNavigate("settings")}>Paramètres de la boutique →</button></section>
        </aside>
      </div>
    </div>
  );
}
