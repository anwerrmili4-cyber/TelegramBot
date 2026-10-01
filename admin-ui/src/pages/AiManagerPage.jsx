import { useEffect, useState } from "react";
import {
  Check,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { PageHeader, ActionButton, Modal } from "../admin-kit.jsx";

const AI_QUICK_PROMPTS = [
  ["Vue d’ensemble", "Donne-moi une vue d’ensemble opérationnelle du bot et les trois priorités du moment."],
  ["Commandes à vérifier", "Analyse les commandes récentes et identifie celles qui demandent l’attention d’un administrateur."],
  ["Stock critique", "Analyse l’inventaire et propose les actions les plus urgentes, sans les exécuter."],
  ["Optimiser les ventes", "Analyse les ventes, les prix et le catalogue, puis suggère des améliorations concrètes."],
  ["Support urgent", "Résume les tickets de support et les alertes qui demandent une réponse rapide."],
];

export default function AiManagerPage({ data, onAction, setToast }) {
  const [config, setConfig] = useState({ configured: false, models: [] });
  const [model, setModel] = useState(window.localStorage.getItem("ai-manager-model") || "");
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: "Bonjour. Je peux répondre à vos questions sur les données du bot, analyser l’activité et proposer des actions d’administration, toujours soumises à votre confirmation.",
  }]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  useEffect(() => {
    let active = true;
    fetch("/admin/api/ai-manager/config", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "La configuration de l’assistant est indisponible.");
        if (!active) return;
        setConfig(payload);
        const selected = payload.models?.includes(model) ? model : payload.models?.[0] || "";
        setModel(selected);
      })
      .catch((error) => active && setToast({ type: "error", title: "Assistant IA", message: error.message }));
    return () => { active = false; };
  }, []);

  const selectModel = (value) => {
    setModel(value);
    window.localStorage.setItem("ai-manager-model", value);
  };

  const send = async (preset) => {
    const content = String(preset || input).trim();
    if (!content || sending || !model) return;
    const userMessage = { role: "user", content };
    const history = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setSending(true);
    try {
      const response = await fetch("/admin/api/ai-manager/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Dashboard-Write-Token": data?.dashboard_write_token || "",
        },
        body: JSON.stringify({
          model,
          messages: history.map(({ role, content: messageContent }) => ({ role, content: messageContent })),
        }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "La réponse de l’assistant est indisponible.");
      setMessages((current) => [...current, {
        role: "assistant",
        content: payload.reply,
        actions: payload.suggested_actions || [],
        model: payload.model,
      }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", error: true, content: error.message }]);
    } finally {
      setSending(false);
    }
  };

  const executeAction = async () => {
    if (!pendingAction) return;
    const completed = await onAction(pendingAction.parameters);
    if (completed) {
      setMessages((current) => [...current, {
        role: "assistant",
        content: `L’action « ${pendingAction.label} » a été exécutée et les données du bot ont été actualisées.`,
      }]);
    }
    setPendingAction(null);
  };

  return (
    <>
      <PageHeader
        title="Assistant IA"
        description="Interrogez les données du bot et gérez les opérations en conversation. Chaque modification demande votre confirmation."
        actions={(
          <div className={`ai-manager-status ${config.configured ? "ready" : ""}`}>
            <span />{config.configured ? "OpenAI configuré" : "Clé OpenAI requise"}
          </div>
        )}
      />
      <section className="ai-manager-layout">
        <aside className="ai-manager-sidebar">
          <div className="ai-manager-brand"><Sparkles size={21} /><div><strong>Assistant d’administration</strong><span>Données du bot actualisées à chaque question</span></div></div>
          <label className="ai-model-select"><span>Modèle actif</span><select value={model} onChange={(event) => selectModel(event.target.value)}>{config.models?.map((item) => <option key={item} value={item}>{item}</option>)}</select>{config.endpoint_host && <small>API: {config.provider || config.endpoint_host}</small>}</label>
          <div className="ai-quick-list"><span>Questions rapides</span>{AI_QUICK_PROMPTS.map(([label, prompt]) => <button key={label} disabled={sending || !config.configured} onClick={() => send(prompt)}><Sparkles size={13} />{label}</button>)}</div>
          <div className="ai-safety-note"><ShieldCheck size={17} /><div><strong>Contrôle humain</strong><span>L’assistant propose, vous confirmez chaque action avant son exécution.</span></div></div>
        </aside>
        <div className="ai-chat-panel">
          <div className="ai-chat-messages">
            {messages.map((message, index) => (
              <article className={`ai-message ${message.role} ${message.error ? "error" : ""}`} key={`${message.role}-${index}`}>
                <div className="ai-message-avatar">{message.role === "assistant" ? <Sparkles size={15} /> : "A"}</div>
                <div className="ai-message-body"><div className="ai-message-meta"><strong>{message.role === "assistant" ? "Assistant IA" : "Vous"}</strong>{message.model && <span>{message.model}</span>}</div><p>{message.content}</p>
                  {!!message.actions?.length && <div className="ai-proposals">{message.actions.map((action, actionIndex) => <div className={`ai-proposal risk-${action.risk}`} key={`${action.action}-${actionIndex}`}><div><span>{action.risk === "high" ? "Risque élevé" : action.risk === "medium" ? "Confirmation requise" : "Risque faible"}</span><strong>{action.label}</strong><p>{action.description}</p></div><button onClick={() => setPendingAction(action)}>Vérifier et exécuter</button></div>)}</div>}
                </div>
              </article>
            ))}
            {sending && <article className="ai-message assistant"><div className="ai-message-avatar"><RefreshCw className="spin" size={15} /></div><div className="ai-message-body"><p>Analyse des données du bot…</p></div></article>}
          </div>
          <form className="ai-chat-composer" onSubmit={(event) => { event.preventDefault(); send(); }}><textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={config.configured ? "Posez une question sur les données, une analyse ou une action…" : "Ajoutez d’abord HP_OPENAI_API_KEY dans Railway"} disabled={!config.configured || sending} rows={2} /><button type="submit" disabled={!input.trim() || sending || !config.configured}><Send size={17} /></button></form>
        </div>
      </section>
      {pendingAction && <Modal title="Confirmer l’action proposée" onClose={() => setPendingAction(null)}><div className="ai-confirm"><ShieldCheck size={30} /><strong>{pendingAction.label}</strong><p>{pendingAction.confirmation}</p><pre>{JSON.stringify(pendingAction.parameters, null, 2)}</pre><div><ActionButton secondary onClick={() => setPendingAction(null)}>Annuler</ActionButton><ActionButton danger={pendingAction.risk === "high"} icon={Check} onClick={executeAction}>Confirmer et exécuter</ActionButton></div></div></Modal>}
    </>
  );
}
