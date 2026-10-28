function fold(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr");
}

export function adminPageId(pathname) {
  return String(pathname || "").replace(/^\/admin(?:-v2)?\/?/, "").split("/").filter(Boolean)[0] || "overview";
}

export function resolveAdminPage(pathname, knownIds) {
  const page = adminPageId(pathname);
  return knownIds.includes(page) ? page : "overview";
}

export function filterNavEntries(groups, query) {
  const needle = fold(query).trim();
  return groups.flatMap((group) => group.items
    .filter((item) => !needle || fold(`${group.label} ${item.label} ${item.id}`).includes(needle))
    .map((item) => ({ id: item.id, label: item.label, icon: item.icon, group: group.label })));
}
