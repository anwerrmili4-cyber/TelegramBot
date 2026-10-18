import { readdir, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const directory = path.resolve(process.argv[2] || "dist");
const limitKb = Number(process.argv[3] || 500);
const limitBytes = limitKb * 1024;

async function JavaScriptFiles(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) return JavaScriptFiles(target);
    return entry.isFile() && entry.name.endsWith(".js") ? [target] : [];
  }));
  return nested.flat();
}

const files = await JavaScriptFiles(directory);
const sizes = await Promise.all(files.map(async (file) => ({
  file,
  bytes: (await stat(file)).size,
})));
const oversized = sizes.filter(({ bytes }) => bytes > limitBytes);
const largest = sizes.sort((a, b) => b.bytes - a.bytes)[0];

if (oversized.length) {
  for (const { file, bytes } of oversized) {
    console.error(`${path.relative(directory, file)} is ${(bytes / 1024).toFixed(2)} kB; limit is ${limitKb} kB.`);
  }
  process.exitCode = 1;
} else if (largest) {
  console.log(`Bundle budget passed. Largest JS chunk: ${path.relative(directory, largest.file)} (${(largest.bytes / 1024).toFixed(2)} kB).`);
}
