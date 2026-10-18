import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspace = new URL("../../", import.meta.url);

async function source(relativePath) {
  return readFile(new URL(relativePath, workspace), "utf8");
}

test("admin and storefront builds define explicit vendor chunk groups", async () => {
  const [adminConfig, storefrontConfig, signupGate, accountPage] = await Promise.all([
    source("admin-ui/vite.config.js"),
    source("storefront/vite.config.ts"),
    source("storefront/src/components/SignupGate.tsx"),
    source("storefront/src/pages/AccountPage.tsx"),
  ]);

  assert.match(adminConfig, /codeSplitting/);
  assert.match(adminConfig, /animation-vendor/);
  assert.match(storefrontConfig, /manualChunks/);
  assert.match(storefrontConfig, /animation-vendor/);
  assert.match(signupGate, /lazy\(\(\) => import/);
  assert.match(accountPage, /@\/lib\/verifyEmailPath/);
});

test("both production builds enforce the JavaScript chunk budget", async () => {
  const [adminPackage, storefrontPackage, budgetScript, dockerfile] = await Promise.all([
    source("admin-ui/package.json"),
    source("storefront/package.json"),
    source("scripts/check-js-bundle-size.mjs"),
    source("Dockerfile"),
  ]);

  assert.match(adminPackage, /check-js-bundle-size/);
  assert.match(storefrontPackage, /check-js-bundle-size/);
  assert.match(budgetScript, /500/);
  assert.equal(
    dockerfile.match(/COPY scripts\/check-js-bundle-size\.mjs \/build\/scripts\/check-js-bundle-size\.mjs/g)?.length,
    2,
  );
});

test("storefront production source maps are opt-in to keep container builds memory-safe", async () => {
  const storefrontConfig = await source("storefront/vite.config.ts");

  assert.match(storefrontConfig, /sourcemap:\s*process\.env\.GENERATE_SOURCEMAP === ["']true["']/);
});
