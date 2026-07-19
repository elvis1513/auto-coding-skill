#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const assetsRoot = path.join(packageRoot, "cli", "assets");
const assetSkill = path.join(assetsRoot, "skill");
const assetAgents = path.join(assetSkill, "data", "templates", "bridges", "AGENTS.md");
const pkg = JSON.parse(fs.readFileSync(path.join(packageRoot, "package.json"), "utf8"));
const bootstrapDocs = [
  ["ENVIRONMENT.md", "docs/ENVIRONMENT.md"],
  ["architecture/.gitkeep", "docs/architecture/.gitkeep"],
  ["design/.gitkeep", "docs/design/.gitkeep"],
  ["interfaces/.gitkeep", "docs/interfaces/.gitkeep"],
  ["deployment/.gitkeep", "docs/deployment/.gitkeep"],
  ["product/.gitkeep", "docs/product/.gitkeep"],
];

function fail(message) { console.error(`\n[autocoding] ERROR: ${message}\n`); process.exit(1); }
function exists(file) { try { fs.accessSync(file); return true; } catch { return false; } }
function sha256(file) { return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex"); }
function toJson(value, json) { if (json) console.log(JSON.stringify(value, null, 2)); else console.log(value); }
function mkdirFor(file) { fs.mkdirSync(path.dirname(file), { recursive: true }); }
function copyFile(source, target) { mkdirFor(target); fs.copyFileSync(source, target); }

function listFiles(root, base = root) {
  const out = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (entry.name === ".DS_Store" || entry.name === "__pycache__") continue;
    const file = path.join(root, entry.name);
    if (entry.isDirectory()) out.push(...listFiles(file, base));
    else out.push(path.relative(base, file).split(path.sep).join("/"));
  }
  return out.sort();
}

function copyTree(source, target) {
  for (const relative of listFiles(source)) copyFile(path.join(source, relative), path.join(target, relative));
}

function parseArgs(argv) {
  const [,, rawCommand, ...rest] = argv;
  const args = { command: (!rawCommand || rawCommand === "-h" || rawCommand === "--help") ? "help" : rawCommand, dest: null, projects: [], json: false };
  for (let index = 0; index < rest.length; index += 1) {
    const value = rest[index];
    if (value === "--dest") args.dest = rest[++index] || fail("--dest requires a path");
    else if (value === "--projects") args.projects.push(...(rest[++index] || fail("--projects requires paths")).split(",").filter(Boolean));
    else if (value === "--json") args.json = true;
    else if (value === "-h" || value === "--help") args.command = "help";
    else if (value.startsWith("--")) fail(`unknown argument: ${value}`);
    else args.projects.push(value);
  }
  return args;
}

function readManifest(project) {
  const file = path.join(project, ".agents", "managed-install.json");
  if (!exists(file)) return null;
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return null; }
}

function legacyManagedPath(relative) {
  return relative.startsWith(".agents/skills/auto-coding-skill/")
    || relative.startsWith(".agents/agents/")
    || relative === "docs/tools/autopipeline/ap.py"
    || relative === "docs/ENGINEERING.md";
}

function retireExactLegacyFiles(project) {
  const previous = readManifest(project);
  const retired = [];
  if (!Array.isArray(previous?.entries)) return retired;
  for (const entry of previous.entries) {
    if (!legacyManagedPath(entry?.path) || typeof entry.sha256 !== "string") continue;
    const target = path.join(project, ...entry.path.split("/"));
    if (exists(target) && fs.statSync(target).isFile() && sha256(target) === entry.sha256) {
      if (entry.path === "docs/ENGINEERING.md") {
        const version = String(previous.skill_version || "legacy").replace(/[^0-9A-Za-z._-]/g, "_");
        const archive = path.join(project, ".agents", "archive", "auto-coding-skill", version, "docs", "ENGINEERING.md");
        copyFile(target, archive);
      }
      fs.rmSync(target);
      retired.push(entry.path);
    }
  }
  return retired;
}

function buildManifest(project) {
  const entries = [];
  const installedSkill = path.join(project, ".agents", "skills", "auto-coding-skill");
  for (const relative of listFiles(installedSkill)) {
    const target = path.join(installedSkill, relative);
    entries.push({ path: `.agents/skills/auto-coding-skill/${relative}`, sha256: sha256(target), ownership: "managed" });
  }
  const agentsTarget = path.join(project, "AGENTS.md");
  entries.push({ path: "AGENTS.md", sha256: sha256(agentsTarget), ownership: "managed" });
  return {
    schema_version: 2,
    skill_version: pkg.version,
    entries,
    project_documents: bootstrapDocs.map(([, target]) => target),
    note: "Project documents are bootstrap-only and are never overwritten or validated as managed content.",
  };
}

function init(project) {
  const root = path.resolve(project);
  if (!exists(root)) fail(`project directory does not exist: ${root}`);
  const retired = retireExactLegacyFiles(root);
  const installedSkill = path.join(root, ".agents", "skills", "auto-coding-skill");
  fs.rmSync(installedSkill, { recursive: true, force: true });
  copyTree(assetSkill, installedSkill);
  copyFile(assetAgents, path.join(root, "AGENTS.md"));
  const created = [];
  for (const [assetRelative, targetRelative] of bootstrapDocs) {
    const source = path.join(assetSkill, "data", "templates", assetRelative);
    const target = path.join(root, targetRelative);
    if (!exists(target)) {
      copyFile(source, target);
      created.push(targetRelative);
    }
  }
  const manifest = buildManifest(root);
  const manifestPath = path.join(root, ".agents", "managed-install.json");
  mkdirFor(manifestPath);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return { project: root, version: pkg.version, created, retired, managed: manifest.entries.length };
}

function status(project) {
  const root = path.resolve(project);
  const manifest = readManifest(root);
  const errors = [];
  if (!manifest) errors.push("managed install manifest is missing");
  const entries = Array.isArray(manifest?.entries) ? manifest.entries : [];
  for (const entry of entries) {
    const target = path.join(root, ...entry.path.split("/"));
    if (!exists(target)) errors.push(`missing managed file: ${entry.path}`);
    else if (sha256(target) !== entry.sha256) errors.push(`modified managed file: ${entry.path}`);
  }
  const documents = Object.fromEntries(bootstrapDocs.map(([, target]) => [target, exists(path.join(root, target))]));
  return { project: root, version: manifest?.skill_version || "", ok: errors.length === 0, errors, documents };
}

function help() {
  console.log(`auto-coding-skill ${pkg.version}\n\nCommands:\n  autocoding init [--dest PATH]\n  autocoding sync [--projects PATH[,PATH...]]\n  autocoding status [--projects PATH[,PATH...]] [--json]\n\nThese commands only install, preserve, and report documentation. They do not run or require Gates, reviews, tests, tasks, worktrees, or deployment checks.`);
}

const args = parseArgs(process.argv);
if (args.command === "help") help();
else if (args.command === "init") toJson(init(args.dest || process.cwd(), args), args.json);
else if (args.command === "sync") {
  const projects = args.projects.length ? args.projects : [process.cwd()];
  toJson({ version: pkg.version, results: projects.map(project => init(project, args)) }, args.json);
} else if (args.command === "status") {
  const projects = args.projects.length ? args.projects : [process.cwd()];
  const results = projects.map(status);
  toJson({ version: pkg.version, results }, args.json);
  if (results.some(result => !result.ok)) process.exitCode = 1;
} else fail(`unknown command: ${args.command}`);
