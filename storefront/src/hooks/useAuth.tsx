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
  changePassword as apiChangePassword,
  fetchMe,
  googleLogin as apiGoogleLogin,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  updateProfile as apiUpdateProfile,
  verifyEmail as apiVerifyEmail,
} from "@/lib/api";
import type { AuthSession, Customer } from "@/types";

const STORAGE_KEY = "blackmarket-tn-session";

type Auth = {
  customer: Customer | null;
  /** Session token for the account endpoints; empty when signed out. */
  token: string;
  /** True until a stored session has been checked against the server. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Signs in, or creates the account, from a Google ID token. */
  loginWithGoogle: (credential: string) => Promise<void>;
  /** Creates the account and emails a code; no session is opened yet. */
  register: (name: string, email: string, password: string) => Promise<void>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  updateProfile: (name: string, phone: string) => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  /** Sign out locally when an account call reports the session is gone. */
  handleError: (reason: unknown) => void;
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

  const loginWithGoogle = useCallback(
    async (credential: string) => openSession(await apiGoogleLogin(credential)),
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

  const handleError = useCallback((reason: unknown) => {
    if (reason instanceof ApiError && reason.status === 401) {
      writeToken("");
      setToken("");
      setCustomer(null);
    }
  }, []);

  const updateProfile = useCallback(
    async (name: string, phone: string) => {
      try {
        setCustomer((await apiUpdateProfile(token, { name, phone })).customer);
      } catch (reason) {
        handleError(reason);
        throw reason;
      }
    },
    [token, handleError],
  );

  const changePassword = useCallback(
    async (current: string, next: string) => {
      try {
        await apiChangePassword(token, { current_password: current, new_password: next });
        setCustomer((known) => (known ? { ...known, has_password: true } : known));
      } catch (reason) {
        handleError(reason);
        throw reason;
      }
    },
    [token, handleError],
  );

  const value = useMemo(
    () => ({
      customer,
      token,
      loading,
      login,
      loginWithGoogle,
      register,
      verifyEmail,
      updateProfile,
      changePassword,
      handleError,
      logout,
    }),
    [customer, token, loading, login, loginWithGoogle, register, verifyEmail, updateProfile, changePassword, handleError, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}
