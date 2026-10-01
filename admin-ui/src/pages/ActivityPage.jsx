import { useState } from "react";
import {
  Activity,
  RefreshCw,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Empty, FilterBar } from "../admin-kit.jsx";

export default function ActivityPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [undoTarget, setUndoTarget] = useState(null);
  const events = (data.audits || []).filter(
    (item) => {
      const searchable = {
        action: item.action || "",
        actor: `${item.actor_id || ""} ${item.user_id || ""}`,
        details: JSON.stringify(item.details || {}),
      };
      const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
      return !search || haystack.toLowerCase().includes(search.toLowerCase());
    },
  );
  return (
    <>
      <PageHeader
        title="Journal des actions"
        description="Historique des actions administratives et événements système."
      />
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["action", "Action"], ["actor", "Acteur / utilisateur"], ["details", "Détails"]]}
        resultCount={events.length}
        placeholder="Action, acteur, utilisateur ou détail…"
      />
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Action</th>
                <th>Acteur</th>
                <th>Détails</th>
                <th>Restauration</th>
              </tr>
            </thead>
            <tbody>
              {events.map((item, index) => (
                <tr key={item.id || index}>
                  <td>{date(item.created_at)}</td>
                  <td>
                    <strong>{item.action}</strong>
                  </td>
                  <td>{item.actor_id || item.user_id || "Système"}</td>
                  <td>
                    <code className="audit-details">
                      {typeof item.details === "string"
                        ? item.details
                        : JSON.stringify(item.details || {})}
                    </code>
                  </td>
                  <td>{item.details?.undone ? <span className="status delivered">Restauré</span> : item.id && item.details?.reversible ? <button className="audit-undo-button" onClick={() => setUndoTarget(item)}><RefreshCw size={13} />Annuler</button> : <span className="audit-not-reversible">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.length && <Empty icon={Activity} title="Aucun événement" />}
      </section>
      {undoTarget && <Modal title="Restaurer cette modification ?" onClose={() => setUndoTarget(null)}><div className="undo-confirm"><span><RefreshCw size={27} /></span><strong>{undoTarget.action}</strong><p>La restauration fonctionne pendant 24 heures. Les éléments modifiés depuis cet événement seront ignorés afin de ne pas écraser un changement plus récent.</p><code>Événement #{undoTarget.id}</code><div><ActionButton secondary onClick={() => setUndoTarget(null)}>Conserver</ActionButton><ActionButton icon={RefreshCw} onClick={async () => { await onAction({ action: "undo_audit_event", event_id: undoTarget.id }); setUndoTarget(null); }}>Restaurer</ActionButton></div></div></Modal>}
    </>
  );
}
