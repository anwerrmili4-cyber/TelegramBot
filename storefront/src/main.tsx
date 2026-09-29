import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "@/App";
import { AuthProvider } from "@/hooks/useAuth";
import "@/styles/index.css";

const container = document.getElementById("root");
if (!container) throw new Error("Missing #root container");

createRoot(container).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
