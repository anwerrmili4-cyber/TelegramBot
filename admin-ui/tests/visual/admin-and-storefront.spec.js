import { expect, test } from "@playwright/test";

const adminData = {
  shop_name: "Black Market · DÉMO",
  preview_mode: true,
  currency: "USDT",
  bot_username: "demonstration",
  summary: {
    pending_orders: 1,
    open_tickets: 1,
    product_requests: 2,
    low_stock_offers: 1,
    revenue_today: 18,
    orders_today: 2,
    new_users_today: 1,
    available_inventory: 8,
  },
  orders: [],
  services: [],
  alerts: [],
  users: [],
  tickets: [],
};

const catalog = {
  ok: true,
  currency: "TND",
  max_cart_lines: 12,
  categories: [{ id: "streaming", label: "Streaming" }],
  payment_methods: [],
  services: [{
    id: 1,
    name: "Black Market",
    emoji: "✦",
    logo_url: "",
    offers: [{
      id: 1,
      package_number: "BM-01",
      name: "Accès premium",
      description: "Un accès numérique prêt à utiliser.",
      price_millimes: 18000,
      currency: "TND",
      available: true,
      stock: 8,
      min_quantity: 1,
      max_quantity: 3,
      delivery_delay: "Rapide",
      period_days: 30,
      warranty: "30 jours",
      warranty_days: 30,
      featured: true,
      badge: "Populaire",
      image_url: "",
      category: "streaming",
      category_label: "Streaming",
      service_id: 1,
      service_name: "Black Market",
      service_emoji: "✦",
      service_logo_url: "",
    }],
  }],
};

async function mockAdmin(page) {
  await page.route("**/admin/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = pathname.endsWith("/notifications")
      ? { items: [], generated_at: 0, poll_after_seconds: 30, summary: { total: 0, critical: 0, actionable: 0, information: 0 } }
      : adminData;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function mockStorefront(page) {
  await page.addInitScript(() => sessionStorage.setItem("bm-intro-seen", "1"));
  await page.route("**/api/storefront/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    let body = { ok: true };
    if (pathname.endsWith("/catalog")) body = catalog;
    if (pathname.endsWith("/reviews")) body = { ok: true, reviews: [], average: 0, count: 0 };
    if (pathname.endsWith("/auth/config")) body = { ok: true, google_client_id: "" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`admin homepage matches the ${viewport.name} reference`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockAdmin(page);
    await page.goto("http://127.0.0.1:4174/admin");
    await expect(page.getByRole("heading", { name: "Accueil", level: 2 })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`admin-${viewport.name}.png`);
  });

  test(`storefront homepage matches the ${viewport.name} reference`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockStorefront(page);
    await page.goto("http://127.0.0.1:4175/");
    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByText("Accès premium", { exact: true }).first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`storefront-${viewport.name}.png`);
  });
}

test("reduced motion keeps content static and disables smooth scrolling", async ({ page }) => {
  await mockAdmin(page);
  await page.goto("http://127.0.0.1:4174/admin");
  await expect(page.getByRole("heading", { name: "Accueil", level: 2 })).toBeVisible();

  const state = await page.evaluate(() => ({
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
    lenis: document.documentElement.classList.contains("lenis"),
    raysDisplay: getComputedStyle(document.querySelector(".workspace-home-rays")).display,
    headingOpacity: getComputedStyle(document.querySelector(".page-heading")).opacity,
  }));

  expect(state).toEqual({ reduced: true, lenis: false, raysDisplay: "none", headingOpacity: "1" });
});
