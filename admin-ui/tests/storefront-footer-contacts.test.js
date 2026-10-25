import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = new URL("../../", import.meta.url);

async function source(relativePath) {
  return readFile(new URL(relativePath, workspace), "utf8");
}

test("contact QR links live in the shared footer instead of the homepage hero", async () => {
  const [hero, footer, contacts] = await Promise.all([
    source("storefront/src/components/Hero.tsx"),
    source("storefront/src/components/SiteFooter.tsx"),
    source("storefront/src/components/FooterContacts.tsx"),
  ]);

  assert.doesNotMatch(hero, /HeroContacts/);
  assert.match(footer, /import \{ FooterContacts \}/);
  assert.match(footer, /<FooterContacts \/>/);
  assert.match(contacts, /className="footer-contacts"/);
  assert.match(contacts, /WhatsApp/);
  assert.match(contacts, /Instagram/);
  assert.match(contacts, /Facebook/);
});

test("footer QR images use the compact presentation", async () => {
  const [contacts, styles] = await Promise.all([
    source("storefront/src/components/FooterContacts.tsx"),
    source("storefront/src/styles/reference.css"),
  ]);

  assert.match(contacts, /width="88" height="88"/);
  assert.match(styles, /\.footer-contact-qr\s*\{[^}]*width:\s*min\(100%,\s*88px\)/s);
});
