export function csvCell(value) {
  let text = String(value ?? "");
  // Spreadsheet applications may execute formulas even in quoted CSV cells.
  if (/^[\s\u0000-\u001f]*[=+@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function csvDocument(columns, rows) {
  return "\ufeff" + [columns.map(([, label]) => csvCell(label)).join(","),
    ...rows.map((row) => columns.map(([key]) => csvCell(row[key])).join(","))].join("\r\n");
}

export function readPreference(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}

export function savePreference(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}

export function normalizeSearchValue(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

export function searchableText(value, seen = new WeakSet()) {
  if (value == null) return "";
  if (["string", "number", "boolean", "bigint"].includes(typeof value)) return normalizeSearchValue(value);
  if (value instanceof Date) return normalizeSearchValue(value.toISOString());
  if (typeof value !== "object" || seen.has(value)) return "";
  seen.add(value);
  const entries = Array.isArray(value) ? value : Object.entries(value).flatMap(([key, item]) => [key, item]);
  return entries.map((item) => searchableText(item, seen)).filter(Boolean).join(" ");
}

export async function getAdminJson(path, signal) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", signal });
  if (response.status === 401) {
    window.dispatchEvent(new Event("admin:session-expired"));
    throw new Error("Session expirée. Reconnectez-vous.");
  }
  if (!response.ok) throw new Error(`Lecture indisponible (${response.status}). Réessayez.`);
  const data = await response.json();
  if (data.ok === false) throw new Error(data.message || data.error || "Lecture indisponible.");
  return data;
}
