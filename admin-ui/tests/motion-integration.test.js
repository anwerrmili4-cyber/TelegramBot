import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("admin motion dependencies are installed", async () => {
  const pkg = JSON.parse(await source("package.json"));

  assert.ok(pkg.dependencies.gsap);
  assert.ok(pkg.dependencies["@gsap/react"]);
  assert.ok(pkg.dependencies.lenis);
  assert.ok(pkg.dependencies.motion);
});

test("admin shell scrolls inside the page instead of smoothing the document", async () => {
  const smoothScroll = await source("src/components/motion/SmoothScroll.jsx");
  const reveals = await source("src/components/motion/useAdminReveals.js");

  assert.doesNotMatch(smoothScroll, /lenis/i);
  assert.doesNotMatch(smoothScroll, /ScrollTrigger/);
  assert.match(reveals, /prefers-reduced-motion:\s*reduce/);
  assert.match(reveals, /slice\(0,\s*12\)/);
  assert.doesNotMatch(reveals, /ScrollTrigger/);
});

test("admin homepage uses the requested React Bits components", async () => {
  const homepage = await source("src/WorkspaceHome.jsx");

  assert.match(homepage, /<BlurText/);
  assert.match(homepage, /<LightRays/);
  assert.match(homepage, /<CountUp/);
  assert.match(homepage, /<StarBorder/);
});
