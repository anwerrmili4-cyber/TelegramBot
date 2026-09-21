import test from "node:test";
import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import config from "../vite.config.js";

test("Vite forwards writes and API reads while deep links serve React", async () => {
  const received = [];
  const backend = createHttpServer((request, response) => {
    received.push([request.method, request.url]);
    request.resume();
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ ok: true }));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const target = `http://127.0.0.1:${backend.address().port}`;
  let vite;
  try {
    vite = await createServer({ ...config, configFile: false, root: fileURLToPath(new URL("../", import.meta.url)), logLevel: "silent", server: { host: "127.0.0.1", port: 0, proxy: Object.fromEntries(Object.entries(config.server.proxy).map(([key, value]) => [key, typeof value === "string" ? target : { ...value, target }])) } });
    await vite.listen();
    const origin = `http://127.0.0.1:${vite.httpServer.address().port}`;
    const write = await fetch(`${origin}/admin`, { method: "POST", body: "action=test" });
    assert.deepEqual(await write.json(), { ok: true });
    const read = await fetch(`${origin}/admin/api/orders`);
    assert.deepEqual(await read.json(), { ok: true });
    for (const path of ["/admin", "/admin/phone", "/admin/data-explorer"]) {
      const page = await fetch(`${origin}${path}`);
      assert.equal(page.status, 200);
      assert.match(await page.text(), /<div id="root"><\/div>/);
    }
    assert.deepEqual(received, [["POST", "/admin"], ["GET", "/admin/api/orders"]]);
  } finally {
    if (vite) await vite.close();
    await new Promise((resolve) => backend.close(resolve));
  }
});
