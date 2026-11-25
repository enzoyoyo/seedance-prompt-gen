import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const root = path.dirname(fileURLToPath(import.meta.url));
const realRoot = fs.realpathSync(root);
const SECURITY_HEADERS = {
  "x-content-type-options": "nosniff",
  "cross-origin-resource-policy": "same-origin",
};
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".bin": "application/octet-stream",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

const server = http.createServer((req, res) => {
  let url;
  try {
    url = new URL(req.url || "/", "http://127.0.0.1");
  } catch {
    res.writeHead(400, SECURITY_HEADERS).end("bad request");
    return;
  }
  if (url.pathname === "/api/health") {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { ...SECURITY_HEADERS, allow: "GET, HEAD" }).end("method not allowed");
      return;
    }
    res.writeHead(200, {
      ...SECURITY_HEADERS,
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-cache",
    });
    res.end(req.method === "HEAD" ? undefined : JSON.stringify({ ok: true, version: 1 }));
    return;
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { ...SECURITY_HEADERS, allow: "GET, HEAD" }).end("method not allowed");
    return;
  }
  let rel;
  try {
    rel = decodeURIComponent(url.pathname);
  } catch {
    res.writeHead(400, SECURITY_HEADERS).end("bad request");
    return;
  }
  if (rel.includes("\0")) {
    res.writeHead(400, SECURITY_HEADERS).end("bad request");
    return;
  }
  if (rel.endsWith("/")) rel += "index.html";
  const file = path.normalize(path.join(realRoot, rel));
  if (file !== realRoot && !file.startsWith(realRoot + path.sep)) {
    res.writeHead(403, SECURITY_HEADERS).end("forbidden");
    return;
  }
  fs.realpath(file, (rpErr, resolved) => {
    if (rpErr) {
      res.writeHead(404, SECURITY_HEADERS).end("not found");
      return;
    }
    if (resolved !== realRoot && !resolved.startsWith(realRoot + path.sep)) {
      res.writeHead(403, SECURITY_HEADERS).end("forbidden");
      return;
    }
    fs.stat(resolved, (stErr, st) => {
      if (stErr || !st.isFile()) {
        res.writeHead(404, SECURITY_HEADERS).end("not found");
        return;
      }
      if (req.method === "HEAD") {
        res.writeHead(200, {
          ...SECURITY_HEADERS,
          "content-type": types[path.extname(resolved)] || "application/octet-stream",
          "cache-control": "no-cache",
        });
        res.end();
        return;
      }
      fs.readFile(resolved, (err, data) => {
        if (err) {
          res.writeHead(404, SECURITY_HEADERS).end("not found");
          return;
        }
        res.writeHead(200, {
          ...SECURITY_HEADERS,
          "content-type": types[path.extname(resolved)] || "application/octet-stream",
          "cache-control": "no-cache",
        });
        res.end(data);
      });
    });
  });
});

const preferred = Number(process.env.PORT || 4173);

function listen(port) {
  server.listen(port, "127.0.0.1");
}

server.on("error", (error) => {
  if (error.code === "EADDRINUSE") {
    listen(preferred + 1 + Math.floor(Math.random() * 20));
    return;
  }
  throw error;
});

server.on("listening", () => {
  const address = server.address();
  const url = `http://127.0.0.1:${address.port}/`;
  console.log(url);
  if (process.env.NO_OPEN !== "1") {
    const opener = process.platform === "darwin"
      ? ["open", [url]]
      : process.platform === "win32"
        ? ["cmd", ["/c", "start", "", url]]
        : ["xdg-open", [url]];
    const child = spawn(opener[0], opener[1], { stdio: "ignore", detached: true });
    child.on("error", () => {});
    child.unref();
  }
});

listen(preferred);
