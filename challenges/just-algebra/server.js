// Verification server for "Just Algebra". Runs as its own container, apart from the wargame.
import express from "express";
import fs from "fs";
import path from "path";
import crypto from "crypto";
import { fileURLToPath } from "url";
import * as snarkjs from "snarkjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(HERE, "public");
const vkey = JSON.parse(fs.readFileSync(path.join(HERE, "verification_key.json"), "utf8"));

// The flag comes from the environment and must match the challenge's flag in the wargame.
const FLAG = (process.env.FLAG || "").trim() || "USG{flag_not_configured}";
if (!process.env.FLAG) console.warn("warning: FLAG is not set");

// BN254 scalar field prime
const P = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

const LEVELS = 10;
const TARGET_LEAF = "9999";
const SESSION_TTL_MS = Number(process.env.SESSION_TTL_MS || 20_000);
const MAX_SESSIONS = Number(process.env.MAX_SESSIONS || 10_000);

// sid -> { createdAt, expectedPublicSignals }
const sessions = new Map();

function cleanupSessions() {
  const now = Date.now();
  for (const [sid, s] of sessions) {
    if (now - s.createdAt > SESSION_TTL_MS) sessions.delete(sid);
  }
}

const bad = (res, code, msg) => res.status(code).json({ error: msg });

// 31 bytes => always < 2^248 < P
const randField = () => BigInt("0x" + crypto.randomBytes(31).toString("hex"));

function customHash(left, right) {
  const t = (left + 3n * right + 42n) % P;
  return (t * t + 1337n) % P;
}

function buildTree(leaf, directions, oddLevel) {
  const siblings = [];
  let cur = leaf;
  for (let i = 0; i < LEVELS; i++) {
    const sib = i === oddLevel ? cur : randField();
    siblings.push(sib);
    const [L, R] = directions[i] === 0 ? [cur, sib] : [sib, cur];
    cur = customHash(L, R);
  }
  return { siblings, root: cur };
}

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "64kb" }));

app.get("/", (_req, res) => res.type("html").send(LANDING));
app.get("/healthz", (_req, res) => res.send("ok"));
app.use("/files", express.static(PUBLIC_DIR, { index: false, dotfiles: "ignore" }));

app.post("/challenge", async (req, res) => {
  cleanupSessions();
  const { action } = req.body || {};

  if (action === "start") {
    if (sessions.size >= MAX_SESSIONS) return bad(res, 503, "server busy, try again");

    const sid = crypto.randomBytes(16).toString("hex");
    const original_leaf = randField();
    const direction_bits = Array.from({ length: LEVELS }, () => crypto.randomInt(0, 2));
    const { siblings, root } = buildTree(original_leaf, direction_bits, crypto.randomInt(1, LEVELS));

    const expectedPublicSignals = [TARGET_LEAF, root.toString(), ...siblings.map(String)];
    sessions.set(sid, { createdAt: Date.now(), expectedPublicSignals });

    return res.json({
      sid,
      root: root.toString(),
      original_leaf: original_leaf.toString(),
      siblings: siblings.map(String),
      direction_bits,
      ttl_ms: SESSION_TTL_MS,
      target_leaf: TARGET_LEAF,
    });
  }

  if (action === "submit") {
    const { sid, proof, publicSignals } = req.body || {};
    if (!sid) return bad(res, 400, "missing sid");
    if (!proof || typeof proof !== "object" || !publicSignals) return bad(res, 400, "missing proof/publicSignals");

    const sess = sessions.get(String(sid));
    if (!sess) return bad(res, 400, "invalid or expired sid");
    // one-shot: a session is spent on its first submit
    sessions.delete(String(sid));
    if (Date.now() - sess.createdAt > SESSION_TTL_MS) return bad(res, 400, "expired sid");

    if (!Array.isArray(publicSignals)) return bad(res, 400, "publicSignals must be array");
    const ps = publicSignals.map(String);
    const expected = sess.expectedPublicSignals;
    if (ps.length !== expected.length) return bad(res, 400, "publicSignals length mismatch");
    for (let i = 0; i < expected.length; i++) {
      if (ps[i] !== expected[i]) return bad(res, 400, `publicSignals[${i}] mismatch`);
    }

    let ok = false;
    try {
      ok = await snarkjs.groth16.verify(vkey, ps, proof);
    } catch {
      ok = false;
    }
    if (!ok) return bad(res, 400, "invalid proof");
    return res.json({ flag: FLAG });
  }

  return bad(res, 404, "unknown action");
});

const LANDING = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Just Algebra</title>
<style>
  body{font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:760px;margin:40px auto;padding:0 16px;background:#0d1117;color:#c9d1d9}
  a{color:#58a6ff} pre{background:#161b22;padding:12px;overflow-x:auto;border-radius:6px} h1{font-size:22px} h2{font-size:17px;margin-top:28px}
</style></head><body>
<h1>Just Algebra</h1>
<p>A verification server accepts only valid zero-knowledge proofs.</p>

<h2>Files</h2>
<ul>
  <li><a href="/files/circuit.circom">circuit.circom</a></li>
  <li><a href="/files/circuit.wasm">circuit.wasm</a></li>
  <li><a href="/files/circuit_final.zkey">circuit_final.zkey</a></li>
</ul>

<h2>API</h2>
<pre>POST /challenge  {"action": "start"}
  → {sid, root, original_leaf, siblings, direction_bits, ttl_ms, target_leaf}

POST /challenge  {"action": "submit", "sid": ..., "proof": ..., "publicSignals": [...]}
  → {flag} if the proof checks out</pre>
<p>A session lives for ${SESSION_TTL_MS / 1000} seconds and can be submitted once.</p>
</body></html>`;

const PORT = Number(process.env.PORT || 8000);
app.listen(PORT, () => console.log(`Listening on ${PORT}`));
