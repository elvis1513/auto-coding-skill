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
const managedDocs = [
  ["ENVIRONMENT.md", "docs/ENVIRONMENT.md"],
];
const projectDocs = [
  ["PROJECT.md", "docs/PROJECT.md"],
  ["architecture/.gitkeep", "docs/architecture/.gitkeep"],
  ["design/.gitkeep", "docs/design/.gitkeep"],
  ["interfaces/.gitkeep", "docs/interfaces/.gitkeep"],
  ["deployment/.gitkeep", "docs/deployment/.gitkeep"],
  ["product/.gitkeep", "docs/product/.gitkeep"],
];
const bootstrapDocs = [...managedDocs, ...projectDocs];

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
  const file = managedTarget(project, ".agents/managed-install.json");
  if (!file || !exists(file)) return null;
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return null; }
}

function safeRelativePath(relative) {
  return typeof relative === "string" && relative.length > 0
    && !relative.includes("\\") && !relative.includes("\0")
    && !relative.includes(":")
    && relative.split("/").every(part => part && part !== "." && part !== "..");
}

// Managed paths must stay inside the project, including through parent symlinks.
function managedTarget(project, relative) {
  if (!safeRelativePath(relative)) return null;
  let target = project;
  for (const part of relative.split("/")) {
    target = path.join(target, part);
    try { if (fs.lstatSync(target).isSymbolicLink()) return null; }
    catch (error) { if (error.code !== "ENOENT") return null; }
  }
  return target;
}

function sourceRepository(project) {
  return exists(path.join(project, "src/auto-coding-skill/SKILL.md"))
    && exists(path.join(project, "cli/src/index.js"));
}

function legacyManagedPath(relative) {
  return safeRelativePath(relative) && (relative.startsWith(".agents/skills/auto-coding-skill/")
    || relative.startsWith(".agents/agents/")
    || relative === "docs/tools/autopipeline/ap.py"
    || relative === "docs/ENGINEERING.md");
}

function retireExactLegacyFiles(project) {
  const previous = readManifest(project);
  const retired = [];
  const retained = [];
  const entries = [...(Array.isArray(previous?.entries) ? previous.entries : []),
    ...(Array.isArray(previous?.legacy_entries) ? previous.legacy_entries : [])];
  for (const entry of entries) {
    if (!legacyManagedPath(entry?.path) || typeof entry.sha256 !== "string") continue;
    const target = managedTarget(project, entry.path);
    if (!target) continue;
    if (exists(target) && fs.statSync(target).isFile() && sha256(target) === entry.sha256) {
      if (entry.path === "docs/ENGINEERING.md") {
        const version = String(previous.skill_version || "legacy").replace(/[^0-9A-Za-z._-]/g, "_");
        const archive = managedTarget(project, `.agents/archive/auto-coding-skill/${version}/docs/ENGINEERING.md`);
        if (!archive) fail("unsafe legacy archive path; no policy file was removed");
        copyFile(target, archive);
      }
      fs.rmSync(target);
      retired.push(entry.path);
    } else if (exists(target) && !entry.path.startsWith(".agents/skills/auto-coding-skill/")) {
      retained.push(entry);
    }
  }
  return { retired, retained };
}

function isManaged(previous, relative) {
  return Array.isArray(previous?.entries) && previous.entries.some(entry => entry?.path === relative && entry?.ownership === "managed");
}

function migrateLegacyEnvironment(project) {
  const previous = readManifest(project);
  const environment = path.join(project, "docs", "ENVIRONMENT.md");
  const projectConfig = path.join(project, "docs", "PROJECT.md");
  if (exists(projectConfig)) return false;
  if (!exists(environment) || isManaged(previous, "docs/ENVIRONMENT.md")) return false;
  const legacy = fs.readFileSync(environment, "utf8");
  if (!legacy.trim()) return false;
  const template = fs.readFileSync(path.join(assetSkill, "data", "templates", "PROJECT.md"), "utf8").trimEnd();
  mkdirFor(projectConfig);
  fs.writeFileSync(projectConfig, `${template}\n\n## Migrated pre-5.0.1 environment context\n\n${legacy}\n`);
  return true;
}

function buildManifest(project, retained) {
  const entries = [];
  const installedSkill = path.join(project, ".agents", "skills", "auto-coding-skill");
  for (const relative of listFiles(installedSkill)) {
    const target = path.join(installedSkill, relative);
    entries.push({ path: `.agents/skills/auto-coding-skill/${relative}`, sha256: sha256(target), ownership: "managed" });
  }
  const agentsTarget = path.join(project, "AGENTS.md");
  entries.push({ path: "AGENTS.md", sha256: sha256(agentsTarget), ownership: "managed" });
  const environmentTarget = path.join(project, "docs", "ENVIRONMENT.md");
  entries.push({ path: "docs/ENVIRONMENT.md", sha256: sha256(environmentTarget), ownership: "managed" });
  return {
    schema_version: 3,
    skill_version: pkg.version,
    entries,
    legacy_entries: retained,
    managed_documents: managedDocs.map(([, target]) => target),
    project_documents: projectDocs.map(([, target]) => target),
    note: "AGENTS.md and docs/ENVIRONMENT.md are refreshed by init/sync. Project documents are bootstrap-only and are never overwritten.",
  };
}

function init(project) {
  const root = path.resolve(project);
  if (!exists(root)) fail(`project directory does not exist: ${root}`);
  if (sourceRepository(root)) fail("this is the skill source repository; use npm run sync-assets and npm run release:check, not init/sync");
  for (const relative of [".agents/skills/auto-coding-skill", ".agents/managed-install.json", "AGENTS.md", ...bootstrapDocs.map(([, target]) => target)]) {
    if (!managedTarget(root, relative)) fail(`unsafe install path (symlink or invalid path): ${relative}`);
  }
  const { retired, retained } = retireExactLegacyFiles(root);
  const installedSkill = path.join(root, ".agents", "skills", "auto-coding-skill");
  fs.rmSync(installedSkill, { recursive: true, force: true });
  copyTree(assetSkill, installedSkill);
  copyFile(assetAgents, path.join(root, "AGENTS.md"));
  const migratedEnvironment = migrateLegacyEnvironment(root);
  const created = [];
  for (const [assetRelative, targetRelative] of managedDocs) {
    const source = path.join(assetSkill, "data", "templates", assetRelative);
    copyFile(source, path.join(root, targetRelative));
  }
  for (const [assetRelative, targetRelative] of projectDocs) {
    const source = path.join(assetSkill, "data", "templates", assetRelative);
    const target = path.join(root, targetRelative);
    if (!exists(target)) {
      copyFile(source, target);
      created.push(targetRelative);
    }
  }
  const manifest = buildManifest(root, retained);
  const manifestPath = path.join(root, ".agents", "managed-install.json");
  mkdirFor(manifestPath);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return { project: root, version: pkg.version, created, retired, legacy_files: legacyFiles(root, manifest), migrated_environment: migratedEnvironment, managed: manifest.entries.length };
}

function expectedEntries() {
  return [...listFiles(assetSkill).map(relative => ({
    path: `.agents/skills/auto-coding-skill/${relative}`, sha256: sha256(path.join(assetSkill, relative)),
  })), { path: "AGENTS.md", sha256: sha256(assetAgents) },
  ...managedDocs.map(([source, target]) => ({ path: target, sha256: sha256(path.join(assetSkill, "data/templates", source)) }))];
}

function legacyFiles(project, manifest) {
  const candidates = new Set(["docs/tools/autopipeline/ap.py"]);
  for (const entry of Array.isArray(manifest?.legacy_entries) ? manifest.legacy_entries : []) {
    if (legacyManagedPath(entry?.path)) candidates.add(entry.path);
  }
  const agents = managedTarget(project, ".agents/agents");
  const scan = ["docs/ENGINEERING.md"];
  if (agents && exists(agents) && fs.statSync(agents).isDirectory()) {
    scan.push(...fs.readdirSync(agents).filter(file => file.endsWith(".toml")).map(file => `.agents/agents/${file}`));
  }
  for (const relative of scan) {
    const target = managedTarget(project, relative);
    if (!target || !exists(target) || !fs.statSync(target).isFile()) continue;
    const text = fs.readFileSync(target, "utf8");
    if (/orchestration-v1\.schema\.json|ap\.py classify|docs\/tools\/autopipeline\//.test(text)
        || (relative === "docs/ENGINEERING.md" && text.includes("auto-coding-skill"))) candidates.add(relative);
  }
  return [...candidates].filter(relative => {
    const target = managedTarget(project, relative);
    return target && exists(target);
  }).sort();
}

function sourceStatus(root) {
  const errors = [];
  const source = path.join(root, "src/auto-coding-skill");
  const packaged = path.join(root, "cli/assets/skill");
  const discovery = path.join(root, ".agents/skills/auto-coding-skill");
  if (!exists(discovery) || fs.realpathSync(discovery) !== fs.realpathSync(source)) {
    errors.push("source skill discovery must link to src/auto-coding-skill");
  }
  const sources = listFiles(source);
  const assets = exists(packaged) ? listFiles(packaged) : [];
  if (JSON.stringify(sources) !== JSON.stringify(assets)
      || sources.some(relative => !exists(path.join(packaged, relative)) || sha256(path.join(source, relative)) !== sha256(path.join(packaged, relative)))) {
    errors.push("packaged skill differs from source; run npm run sync-assets");
  }
  let version = "";
  try {
    version = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).version;
    const assetManifest = JSON.parse(fs.readFileSync(path.join(root, "cli/assets/managed-install.json"), "utf8"));
    const expected = sources.map(relative => ({ path: relative, sha256: sha256(path.join(source, relative)) }));
    if (assetManifest.schema_version !== 2 || assetManifest.skill_version !== version
        || JSON.stringify(assetManifest.asset_files) !== JSON.stringify(expected)) {
      errors.push("packaged asset manifest differs from source; run npm run sync-assets");
    }
  } catch { errors.push("source package or asset manifest is missing or invalid"); }
  const legacy = legacyFiles(root, null);
  errors.push(...legacy.map(file => `legacy workflow file requires review: ${file}`));
  return { project: root, mode: "source", version, ok: errors.length === 0, errors, legacy_files: legacy };
}

function status(project) {
  const root = path.resolve(project);
  if (sourceRepository(root)) return sourceStatus(root);
  const manifest = readManifest(root);
  const integrityErrors = [];
  const currentErrors = [];
  if (!manifest) integrityErrors.push("managed install manifest is missing or invalid");
  const entries = Array.isArray(manifest?.entries) ? manifest.entries : [];
  if (!entries.length) integrityErrors.push("managed install manifest has no entries");
  const seen = new Set();
  for (const entry of entries) {
    const target = managedTarget(root, entry?.path);
    if (!target || !/^[a-f0-9]{64}$/.test(entry?.sha256) || seen.has(entry.path)) {
      integrityErrors.push("invalid, duplicate, or unsafe managed manifest entry");
      continue;
    }
    seen.add(entry.path);
    if (!exists(target) || !fs.statSync(target).isFile()) integrityErrors.push(`missing managed file: ${entry.path}`);
    else if (sha256(target) !== entry.sha256) integrityErrors.push(`modified managed file: ${entry.path}`);
  }
  if (manifest?.skill_version !== pkg.version) currentErrors.push(`installed version ${manifest?.skill_version || "unknown"} differs from CLI ${pkg.version}`);
  if (manifest?.schema_version !== 3) currentErrors.push("managed manifest schema needs refresh");
  const expected = expectedEntries();
  const expectedPaths = new Set(expected.map(entry => entry.path));
  for (const entry of expected) {
    const recorded = entries.find(item => item?.path === entry.path);
    if (!recorded || recorded.sha256 !== entry.sha256 || recorded.ownership !== "managed") currentErrors.push(`manifest differs from current asset: ${entry.path}`);
    const target = managedTarget(root, entry.path);
    if (!target || !exists(target) || !fs.statSync(target).isFile() || sha256(target) !== entry.sha256) currentErrors.push(`installed file differs from current asset: ${entry.path}`);
  }
  for (const entry of entries) {
    if (safeRelativePath(entry?.path) && !expectedPaths.has(entry.path)) currentErrors.push(`obsolete managed entry: ${entry.path}`);
  }
  const skill = managedTarget(root, ".agents/skills/auto-coding-skill");
  const extra = skill && exists(skill) && fs.statSync(skill).isDirectory()
    ? listFiles(skill).map(file => `.agents/skills/auto-coding-skill/${file}`).filter(file => !expectedPaths.has(file)) : [];
  currentErrors.push(...extra.map(file => `unexpected installed skill file: ${file}`));
  const legacy = legacyFiles(root, manifest);
  currentErrors.push(...legacy.map(file => `legacy workflow file requires review: ${file}`));
  const errors = [...integrityErrors, ...currentErrors];
  const documents = Object.fromEntries(bootstrapDocs.map(([, target]) => [target, exists(path.join(root, target))]));
  return { project: root, version: manifest?.skill_version || "", expected_version: pkg.version,
    integrity: integrityErrors.length === 0, current: currentErrors.length === 0, ok: errors.length === 0,
    errors, legacy_files: legacy, unexpected_files: extra, documents };
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
