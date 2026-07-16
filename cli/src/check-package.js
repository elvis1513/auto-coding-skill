#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const packed = spawnSync(
  npmCommand,
  ["pack", "--dry-run", "--json", "--ignore-scripts"],
  { cwd: repoRoot, encoding: "utf8" },
);

if (packed.status !== 0) {
  process.stderr.write(packed.stderr || packed.stdout || "npm pack --dry-run failed\n");
  process.exit(packed.status || 1);
}

let payload;
try {
  payload = JSON.parse(packed.stdout);
} catch (error) {
  process.stderr.write(`Cannot parse npm pack output: ${error.message}\n`);
  process.exit(1);
}

const files = payload?.[0]?.files?.map(item => String(item.path || "")) || [];
const forbidden = files.filter(file =>
  /(^|\/)__pycache__(\/|$)/.test(file) || /\.py[cod]$/i.test(file),
);
if (!files.includes("cli/assets/managed-install.json")) {
  process.stderr.write("Managed install manifest is missing from the package\n");
  process.exit(1);
}
if (forbidden.length > 0) {
  process.stderr.write(`Generated Python cache leaked into package:\n- ${forbidden.join("\n- ")}\n`);
  process.exit(1);
}

process.stdout.write(`[package-check] OK files=${files.length}\n`);
