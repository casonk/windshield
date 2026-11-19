// One published port, several Playwright servers: route a WebSocket upgrade by its URL path
// (/1.64 or /1.64.1) to the run-server for that version. "/" goes to the newest version.
// No dependencies; plain TCP splice after rewriting the request path to "/".
const net = require("net");
const fs = require("fs");
const { spawn } = require("child_process");

const root = process.env.PW_ROOT || "/opt/pw";
const host = process.env.PLAYWRIGHT_HOST || "0.0.0.0";
const port = Number(process.env.PLAYWRIGHT_PORT || 3000);
const versions = fs
  .readdirSync(root)
  .filter((d) => /^\d+\.\d+\.\d+/.test(d))
  .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
if (!versions.length) { console.error("no Playwright versions under " + root); process.exit(2); }

const backends = new Map(); // route key -> internal port
const children = [];
let ready = 0;
versions.forEach((version, i) => {
  const internal = port + 100 + i;
  const minor = version.split(".").slice(0, 2).join(".");
  backends.set(version, internal);
  backends.set(minor, internal); // later (newer) patch of the same minor wins
  const child = spawn(`${root}/${version}/node_modules/.bin/playwright`,
    ["run-server", "--port", String(internal), "--host", "127.0.0.1"],
    { stdio: ["ignore", "pipe", "inherit"],
      env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: `${root}/browsers/${version}` } });
  child.stdout.on("data", (d) => {
    if (String(d).includes("Listening")) { console.log(`playwright ${version} ready`); if (++ready === versions.length) listen(); }
  });
  child.on("exit", (code) => { console.error(`playwright ${version} exited (${code})`); shutdown(code || 1); });
  children.push(child);
});
const newest = backends.get(versions[versions.length - 1]);

function shutdown(code) { children.forEach((c) => c.kill("SIGTERM")); process.exit(code); }
process.on("SIGTERM", () => shutdown(0));
process.on("SIGINT", () => shutdown(0));

function listen() {
  net.createServer((client) => {
    let head = Buffer.alloc(0);
    const onData = (chunk) => {
      head = Buffer.concat([head, chunk]);
      const end = head.indexOf("\r\n\r\n");
      if (end === -1) { if (head.length > 16384) client.destroy(); return; }
      client.removeListener("data", onData);
      client.pause();
      const line = head.subarray(0, head.indexOf("\r\n")).toString("latin1");
      const m = /^(\S+) (\S+) (HTTP\/\S+)$/.exec(line);
      const key = m ? m[2].split("?")[0].replace(/^\/+|\/+$/g, "") : "";
      const target = key === "" ? newest : backends.get(key);
      if (!m || target === undefined) {
        client.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\nunknown Playwright version; available: " +
          [...backends.keys()].join(", ") + "\n");
        return;
      }
      const rewritten = Buffer.concat([Buffer.from(`${m[1]} /${(m[2].split("?")[1] ? "?" + m[2].split("?")[1] : "")} ${m[3]}`, "latin1"), head.subarray(head.indexOf("\r\n"))]);
      const upstream = net.connect(target, "127.0.0.1", () => {
        upstream.write(rewritten);
        client.pipe(upstream); upstream.pipe(client); client.resume();
      });
      const drop = () => { client.destroy(); upstream.destroy(); };
      upstream.on("error", drop); client.on("error", drop);
      upstream.on("close", drop); client.on("close", drop);
    };
    client.on("data", onData);
    client.on("error", () => client.destroy());
  }).listen(port, host, () => console.log(`Listening on ws://${host}:${port}/ (versions: ${[...backends.keys()].join(", ")})`));
}
