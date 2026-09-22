import { Component, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./premium.css";
import "./workspace.css";
import "./orders.css";
import "./monochrome.css";
import "./motion.css";
import "./finance.css";
import "./operations.css";

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, details) {
    console.error("Admin dashboard render failed", error, details);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="fatal-error-page">
        <section>
          <strong>Le dashboard doit être rechargé</strong>
          <p>La page précédente n’a pas pu être restaurée correctement.</p>
          <div>
            <button type="button" onClick={() => window.location.reload()}>Recharger</button>
            <button type="button" className="secondary" onClick={() => window.location.assign("/admin")}>Retour à l’accueil</button>
          </div>
        </section>
      </main>
    );
  }
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
);
