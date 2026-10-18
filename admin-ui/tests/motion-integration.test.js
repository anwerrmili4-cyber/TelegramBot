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

test("Lenis is driven by GSAP and keeps ScrollTrigger synchronized", async () => {
  const smoothScroll = await source("src/components/motion/SmoothScroll.jsx");

  assert.match(smoothScroll, /lenis\.on\(["']scroll["'],\s*ScrollTrigger\.update\)/);
  assert.match(smoothScroll, /lenis\.raf\(time \* 1000\)/);
  assert.match(smoothScroll, /gsap\.ticker\.add\(tick\)/);
  assert.match(smoothScroll, /prefers-reduced-motion:\s*reduce/);
});

test("admin sections reveal with ScrollTrigger and reduced motion stays static", async () => {
  const reveals = await source("src/components/motion/useAdminReveals.js");

  assert.match(reveals, /ScrollTrigger/);
  assert.match(reveals, /once:\s*true/);
  assert.match(reveals, /prefers-reduced-motion:\s*reduce/);
});

test("admin homepage uses the requested React Bits components", async () => {
  const homepage = await source("src/WorkspaceHome.jsx");

  assert.match(homepage, /<BlurText/);
  assert.match(homepage, /<LightRays/);
  assert.match(homepage, /<CountUp/);
  assert.match(homepage, /<StarBorder/);
});
