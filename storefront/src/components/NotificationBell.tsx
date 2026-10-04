import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { fetchNotifications, markNotificationRead, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { accountPath } from "@/lib/accountPath";
import { navigate, ROUTES, usePathname, withNext } from "@/lib/router";
import type { SiteNotification } from "@/types";

export function noticeClass(item: SiteNotification): string {
  const tone = item.kind === "balance"
    ? (item.title.toLocaleLowerCase("fr").includes("crédit") ? "credit" : "debit")
    : item.kind;
  return ["notice-row", item.read ? "" : "is-new", `is-${tone}`].filter(Boolean).join(" ");
}

export function NotificationBell() {
  const { customer, token, loading } = useAuth();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SiteNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) {
      setItems([]);
      setUnread(0);
      return undefined;
    }
    const controller = new AbortController();
    const load = () => {
      fetchNotifications(token, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setItems(result.items);
          setUnread(result.unread);
        })
        .catch(() => undefined);
    };
    load();
    window.addEventListener("focus", load);
    return () => {
      controller.abort();
      window.removeEventListener("focus", load);
    };
  }, [token]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function openItem(item: SiteNotification) {
    if (!token) return;
    setError("");
    try {
      if (!item.read) {
        const result = await markNotificationRead(token, item.id);
        setItems(result.items);
        setUnread(result.unread);
      }
      setOpen(false);
      if (item.href) navigate(item.href);
    } catch (reason) {
      setError(errorMessage(reason, "La notification n'a pas pu être ouverte."));
    }
  }

  if (loading) return null;

  if (!customer) {
    return (
      <button
        type="button"
        className="icon-button notice-toggle"
        aria-label="Notifications"
        onClick={() => navigate(withNext(ROUTES.login, path || ROUTES.home))}
      >
        <Bell size={17} aria-hidden="true" />
      </button>
    );
  }

  return (
    <div className={open ? "notice-bell open" : "notice-bell"} ref={root}>
      <button
        type="button"
        className="icon-button notice-toggle"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={unread ? `${unread} notifications non lues` : "Notifications"}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={17} aria-hidden="true" />
        {unread ? <b>{unread > 9 ? "9+" : unread}</b> : null}
      </button>
      {open ? (
        <div className="notice-panel" role="dialog" aria-label="Notifications">
          <header className="notice-head">
            <strong>Notifications</strong>
            {unread ? <span>{unread} nouvelles</span> : <span>À jour</span>}
          </header>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {!items.length ? <p className="notice-empty">Aucune notification pour le moment.</p> : null}
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={noticeClass(item)}
                  onClick={() => void openItem(item)}
                >
                  <i className="notice-mark" aria-hidden="true" />
                  <small>{item.kind_label}</small>
                  <strong>{item.title}</strong>
                  {item.body ? <span>{item.body}</span> : null}
                  <time dateTime={new Date(item.created_at * 1000).toISOString()}>{dateTime(item.created_at)}</time>
                </button>
              </li>
            ))}
          </ul>
          {items.length ? (
            <button
              type="button"
              className="notice-more"
              onClick={() => {
                setOpen(false);
                navigate(accountPath("notifications"));
              }}
            >
              Voir tout
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
