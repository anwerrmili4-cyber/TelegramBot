import { expect, test } from "@playwright/test";

const stamp = new Date(2026, 9, 25, 11, 13).getTime() / 1000;
const names = ["ChatGPT Plus 1 mois · Garantie 15 jours", "Claude Pro", "Coursera Premium", "Canva Pro", "Netflix Premium", "Cursor Pro"];
const products = names.map((name, index) => ({
  key: `offer:${index + 1}`, offer_id: index + 1, name, service_name: name.split(" ")[0],
  catalog_state: index === 0 ? "archived" : "active", catalog_label: index === 0 ? "Archivé" : "Actif",
  period: "30 jours", warranty: "15 jours", sales_count: 8, buyer_count: 3, quantity: 9,
  spent: 46.1, first_sale_at: stamp - 86400, last_sale_at: stamp,
  fw_total: 2, fw_active: 1, fw_finished: 1,
}));

async function mockBuyers(page, channel = "bot") {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.addInitScript(() => localStorage.setItem("admin-theme", "dark"));
  await page.route("**/admin/api/**", async (route) => {
    const url = new URL(route.request().url());
    let body = { ok: true, items: [], total: 0 };
    if (url.pathname.endsWith("/data")) body = {
      shop_name: "Black Market · DÉMO", preview_mode: true, currency: "USDT", bot_username: "demonstration",
      summary: {}, orders: [], services: [], alerts: [], users: [], tickets: [],
    };
    if (url.pathname.endsWith("/notifications")) body = { items: [], summary: {}, poll_after_seconds: 30 };
    if (url.pathname.endsWith("/product-buyers")) {
      const search = url.searchParams.get("search")?.toLowerCase() || "";
      const coverage = url.searchParams.get("coverage") || "all";
      const rows = products.filter((product) => product.name.toLowerCase().includes(search));
      const selected = products.find((product) => product.key === url.searchParams.get("product"));
      const hasSales = !(Number(url.searchParams.get("from_ts")) > stamp);
      const buyers = ["Amina Salah", "Karim Ben Ali", "Youssef Mansour"].map((name, index) => ({
        key: `user:${42 + index}`, name, entity_id: 42 + index, page: channel === "site" ? "site-customers" : "customers",
        email: `client${index}@example.com`, orders_count: 1, quantity: 2, spent: channel === "site" ? 15000 : 15,
        last_purchase_at: stamp, fw_total: index < 2 ? 1 : 0, fw_active: index === 0 ? 1 : 0, fw_finished: index === 1 ? 1 : 0,
        details: [{ label: "Compte", value: "Actif" }, { label: "Nom d’utilisateur", value: `@client${index}` }],
        orders: [{
          order_id: 101 + index, cart_reference: channel === "site" ? `TN-${101 + index}` : "", quantity: 2,
          spent: channel === "site" ? 15000 : 15, status: "delivered", paid_at: stamp,
          is_full_warranty: index < 2, fw_status: index === 0 ? "active" : index === 1 ? "finished" : "",
          remaining_days: index === 0 ? 12 : index === 1 ? 0 : null, expires_at: index < 2 ? stamp + (index === 0 ? 12 : -2) * 86400 : null,
          pre_confirmation: index === 0 ? {
            prompt: channel === "site" ? "Email du compte à activer" : "",
            customer_info: channel === "site" ? "amina-login@example.com" : "",
            customer_note: "Profil enfants",
            admin_note: "Vérifié manuellement",
            messages: [
              { id: 1, sender_type: "admin", content: "Quel profil souhaitez-vous ?", created_at: stamp - 120 },
              { id: 2, sender_type: "client", content: "Le profil Enfants", created_at: stamp - 60 },
            ],
          } : undefined,
        }],
      })).filter((buyer) => coverage === "fw_active" ? buyer.fw_active : coverage === "fw_finished" ? buyer.fw_finished : coverage === "fw" ? buyer.fw_total : true);
      body = { ok: true, products: hasSales ? rows : [], product: selected && hasSales ? {
        ...selected, sales_count: buyers.length, buyer_count: buyers.length, fw_total: buyers.filter((buyer) => buyer.fw_total).length,
        fw_active: buyers.filter((buyer) => buyer.fw_active).length, fw_finished: buyers.filter((buyer) => buyer.fw_finished).length,
        facts: [{ label: "Description", value: "Accès premium avec assistance et garantie." }, { label: "Prix catalogue", value: "7.50 USDT" }],
        buyers,
      } : null };
    }
    if (url.pathname.endsWith("/customers") && url.searchParams.has("user_id")) body = { telegram_id: 42, first_name: "Amina", last_name: "Salah", orders: [], timeline: [] };
    if (url.pathname.endsWith("/site-customers")) body = { items: [{ id: 42, name: "Amina Salah", email: "client0@example.com", carts: [] }], total: 1 };
    if (url.pathname.endsWith("/orders") && url.searchParams.has("order_id")) body = { id: 101, offer_name: names[0], status: "delivered", user_id: 42, qty: 2, total_price: 15 };
    if (url.pathname.endsWith("/site-orders")) body = { items: [{ reference: "TN-101", customer_name: "Amina Salah", customer_id: 42, status: "delivered", items: [], total_millimes: 15000 }], total: 1 };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  return errors;
}

test("buyers retain period and selection through customer and order routes", async ({ page }) => {
  const errors = await mockBuyers(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("http://127.0.0.1:4174/admin/product-buyers");
  await expect(page.getByText("Sélectionnez un produit", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /ChatGPT Plus 1 mois/ }).click();
  await expect(page.getByRole("link", { name: "Ouvrir la fiche de Amina Salah" })).toBeVisible();
  await expect(page.locator(".fw-dot.active").first()).toContainText("1 en cours");
  await expect(page.locator(".fw-dot.finished").first()).toContainText("1 terminé");
  await page.getByRole("button", { name: /^Commandes 3$/ }).click();
  await expect(page.getByText("En cours · 12 j restants", { exact: true })).toBeVisible();
  await expect(page.getByText("Terminé", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Clients 3$/ }).click();
  await page.getByRole("combobox", { name: "Filtrer le suivi Full Warranty" }).selectOption("fw_active");
  await expect(page).toHaveURL(/coverage=fw_active/);
  await expect(page.getByRole("link", { name: "Ouvrir la fiche de Amina Salah" })).toBeVisible();
  await expect(page.getByText("Karim Ben Ali", { exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Filtrer le suivi Full Warranty" }).selectOption("all");
  await expect(page.getByText("Karim Ben Ali", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Filtrer par période" }).selectOption("custom");
  await expect(page.getByRole("alert")).toContainText("Choisissez une date");
  await page.getByLabel("Date de début").fill("2026-10-01");
  await page.getByLabel("Date de fin").fill("2026-10-25");
  await expect(page.getByRole("link", { name: "Ouvrir la fiche de Amina Salah" })).toBeVisible();
  await page.screenshot({ path: "test-results/buyers-desktop.png", fullPage: true });
  await expect(page.locator(".buyer-product-file")).not.toHaveAttribute("open");
  await page.getByRole("link", { name: "Ouvrir la fiche de Amina Salah" }).click();
  await expect(page).toHaveURL(/\/customers\?user=42$/);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("Date de début")).toHaveValue("2026-10-01");
  await expect(page.getByRole("heading", { name: names[0] })).toBeVisible();
  await page.getByRole("button", { name: "Afficher les achats de Amina Salah" }).click();
  await page.getByRole("button", { name: "Afficher les informations avant confirmation de la commande 101" }).click();
  await expect(page.getByText("Quel profil souhaitez-vous ?", { exact: true })).toBeVisible();
  await expect(page.getByText("Le profil Enfants", { exact: true })).toBeVisible();
  await expect(page.getByText("Profil enfants", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Commande #101" }).click();
  await expect(page).toHaveURL(/\/orders\/101$/);
  await expect(page.getByRole("heading", { name: "Commande #101" })).toBeVisible();
  await page.goBack();
  await page.getByRole("button", { name: /^Commandes 3$/ }).click();
  await expect(page.getByRole("link", { name: "Ouvrir la commande 101" })).toHaveAttribute("href", "/admin/orders?order=101");
  await page.reload();
  await expect(page.getByRole("button", { name: /^Commandes 3$/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Date de début").fill("2026-11-01");
  await expect(page.getByRole("alert")).toContainText("date de fin");
  await page.getByLabel("Date de fin").fill("2026-11-02");
  await expect(page.getByText("Aucune vente sur cette période", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Réinitialiser les filtres" }).click();
  await expect(page.getByRole("heading", { name: names[0] })).toBeVisible();
  expect(errors).toEqual([]);
});

test("site buyers open site customer and cart routes", async ({ page }) => {
  const errors = await mockBuyers(page, "site");
  await page.goto("http://127.0.0.1:4174/admin/site-product-buyers?product=offer%3A1");
  await page.getByRole("link", { name: "Ouvrir la fiche de Amina Salah" }).click();
  await expect(page).toHaveURL(/site-customers\?customer=42&search=client0%40example.com/);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.goBack();
  await page.getByRole("button", { name: /^Commandes 3$/ }).click();
  await page.getByRole("link", { name: "Ouvrir la commande TN-101" }).click();
  await expect(page).toHaveURL(/site-orders\?cart=TN-101/);
  await expect(page.getByRole("heading", { name: "TN-101" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("buyers respond to narrow viewports and offer a retry on failure", async ({ page }) => {
  const errors = await mockBuyers(page);
  await page.goto("http://127.0.0.1:4174/admin/product-buyers?product=offer%3A1");
  await expect(page.getByRole("heading", { name: names[0] })).toBeVisible();
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow, `No page overflow at ${width}px`).toBe(false);
    if (width === 390) await page.screenshot({ path: "test-results/buyers-mobile.png", fullPage: true });
  }
  await page.getByRole("searchbox", { name: "Rechercher un client" }).fill("absent");
  await expect(page.getByText("Aucun client", { exact: true })).toBeVisible();
  await page.getByRole("searchbox", { name: "Rechercher un client" }).fill("");
  await page.locator(".buyer-product-file summary").click();
  await expect(page.getByText("Accès premium avec assistance et garantie.")).toBeVisible();
  expect(errors).toEqual([]);
  await page.route("**/admin/api/product-buyers?**", (route) => route.fulfill({ status: 200, json: { ok: false, error: "Service indisponible" } }), { times: 1 });
  await page.getByRole("searchbox", { name: "Rechercher un produit vendu" }).fill("ChatGPT");
  await expect(page.getByRole("alert")).toContainText("Service indisponible");
  await page.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect(page.getByRole("heading", { name: names[0] })).toBeVisible();
});
