import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  verifyEmail as apiVerifyEmail,
} from "@/lib/api";
import type { AuthSession, Customer } from "@/types";

const STORAGE_KEY = "blackmarket-tn-session";

type Auth = {
  customer: Customer | null;
  /** True until a stored session has been checked against the server. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Creates the account and emails a code; no session is opened yet. */
  register: (name: string, email: string, password: string) => Promise<void>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<Auth | null>(null);

function readToken(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeToken(token: string) {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Private browsing: the session simply lasts until the tab closes.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(readToken);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(() => Boolean(readToken()));

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    fetchMe(token, controller.signal)
      .then((result) => setCustomer(result.customer))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        // Keep the token through a network blip; drop it only when rejected.
        if (reason instanceof ApiError && reason.status === 401) {
          writeToken("");
          setToken("");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token]);

  const openSession = useCallback((session: AuthSession) => {
    writeToken(session.token);
    setCustomer(session.customer);
    setToken(session.token);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => openSession(await apiLogin({ email, password })),
    [openSession],
  );

  const register = useCallback(async (name: string, email: string, password: string) => {
    await apiRegister({ name, email, password });
  }, []);

  const verifyEmail = useCallback(
    async (email: string, code: string) => openSession(await apiVerifyEmail({ email, code })),
    [openSession],
  );

  const logout = useCallback(async () => {
    const current = token;
    writeToken("");
    setToken("");
    setCustomer(null);
    if (current) await apiLogout(current).catch(() => undefined);
  }, [token]);

  const value = useMemo(
    () => ({ customer, loading, login, register, verifyEmail, logout }),
    [customer, loading, login, register, verifyEmail, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}
