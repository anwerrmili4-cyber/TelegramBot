import { useState } from "react";
import {
  Activity,
} from "lucide-react";
import { date, PageHeader, Empty, FilterBar } from "../admin-kit.jsx";

const INTERACTION_TYPE_LABELS = {
  button: "Bouton",
  message: "Message",
  command: "Commande",
  media: "Média",
  other: "Autre",
};

export default function InteractionsPage({ data }) {
  const analytics = data.interactions || {};
  const summary = analytics.summary || {};
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [type, setType] = useState("");
  const events = (analytics.events || []).filter(
    (event) => {
      const searchable = {
        user: `${event.full_name || ""} ${event.username || ""} ${event.user_id || ""}`,
        action: event.action || "",
        content: `${event.content || ""} ${event.screen || ""}`,
      };
      const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
      return (!type || event.interaction_type === type) && (!search || haystack.toLowerCase().includes(search.toLowerCase()));
    },
  );
  const max = Math.max(
    ...(analytics.daily || []).map((point) => point.count),
    1,
  );
  return (
    <>
      <PageHeader
        title="Interactions"
        description="Messages, commandes et clics enregistrés dans le bot."
      />
      <div className="mini-kpi-grid">
        <div>
          <span>Total</span>
          <strong>{summary.total || 0}</strong>
        </div>
        <div>
          <span>Aujourd’hui</span>
          <strong>{summary.today || 0}</strong>
        </div>
        <div>
          <span>Utilisateurs actifs</span>
          <strong>{summary.active_today || 0}</strong>
        </div>
        <div>
          <span>Clics boutons</span>
          <strong>{summary.button_clicks || 0}</strong>
        </div>
      </div>
      <section className="data-panel analytics-panel">
        <header>
          <h3>Interactions sur 30 jours</h3>
        </header>
        <div className="bar-chart">
          {(analytics.daily || []).map((point) => (
            <div key={point.date} title={`${point.date}: ${point.count}`}>
              <i
                style={{ height: `${Math.max(4, (point.count / max) * 100)}%` }}
              />
              <span>{point.date.slice(8)}</span>
            </div>
          ))}
        </div>
      </section>
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["user", "Utilisateur"], ["action", "Action"], ["content", "Message / écran"]]}
        resultCount={events.length}
        placeholder="Nom, utilisateur, message ou action…"
      >
        <select value={type} onChange={(event) => setType(event.target.value)} aria-label="Type d’interaction">
          <option value="">Tous les types</option>
          {Object.entries(INTERACTION_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Utilisateur</th>
                <th>Type</th>
                <th>Action</th>
                <th>Contenu / écran</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => (
                <tr key={event.id || index}>
                  <td>{date(event.created_at)}</td>
                  <td>
                    <strong>
                      {event.full_name || event.first_name || event.user_id}
                    </strong>
                    <small>
                      {event.username ? `@${event.username}` : event.user_id}
                    </small>
                  </td>
                  <td>
                    <span className="status">{INTERACTION_TYPE_LABELS[event.interaction_type] || event.interaction_type}</span>
                  </td>
                  <td>
                    <code>{event.action || "—"}</code>
                  </td>
                  <td>{event.content || event.screen || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.length && <Empty icon={Activity} title="Aucune interaction" />}
      </section>
    </>
  );
}
