#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

function die(msg){
  console.error(`\n[autocoding] ERROR: ${msg}\n`);
  process.exit(1);
}

function takeValue(rest, index, flag){
  const value = rest[index + 1];
  if (!value || value.startsWith("--")) die(`${flag} requires a value`);
  return value;
}

function parseArgs(argv){
  const args = {
    cmd: null,
    ai: null,
    mode: "project",
    dest: null,
    force: false,
    dryRun: false,
    json: false,
    resetAgentModels: false,
    components: "all",
    projects: [],
    projectsFlagProvided: false,
    provided: new Set(),
  };
  const [,, cmd, ...rest] = argv;
  args.cmd = (!cmd || cmd === "-h" || cmd === "--help") ? "help" : cmd;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--ai") {
      args.ai = takeValue(rest, i, a);
      args.provided.add("ai");
      i += 1;
    }
    else if (a === "--mode") {
      args.mode = takeValue(rest, i, a);
      args.provided.add("mode");
      i += 1;
    }
    else if (a === "--dest") {
      args.dest = takeValue(rest, i, a);
      args.provided.add("dest");
      i += 1;
    }
    else if (a === "--projects") {
      args.projects.push(...takeValue(rest, i, a).split(",").map(x => x.trim()).filter(Boolean));
      args.projectsFlagProvided = true;
      args.provided.add("projects");
      i += 1;
    }
    else if (a === "--dry-run") {
      args.dryRun = true;
      args.provided.add("dryRun");
    }
    else if (a === "--json") {
      args.json = true;
      args.provided.add("json");
    }
    else if (a === "--reset-agent-models") {
      args.resetAgentModels = true;
      args.provided.add("resetAgentModels");
    }
    else if (a === "--components") {
      args.components = takeValue(rest, i, a).trim().toLowerCase();
      args.provided.add("components");
      i += 1;
    }
    else if (a === "--force") {
      args.force = true;
      args.provided.add("force");
    }
    else if (a === "-h" || a === "--help") args.cmd = "help";
    else if (!a.startsWith("--")) {
      args.projects.push(a);
      args.provided.add("projects");
    }
    else die(`unknown argument: ${a}`);
  }
  return args;
}

const ARG_FLAGS = {
  ai: "--ai",
  mode: "--mode",
  dest: "--dest",
  force: "--force",
  dryRun: "--dry-run",
  json: "--json",
  resetAgentModels: "--reset-agent-models",
  components: "--components",
  projects: "--projects/positional project",
};

const COMMAND_ARGS = {
  init: new Set(["ai", "mode", "dest", "force", "resetAgentModels"]),
  status: new Set(["projects", "json"]),
  sync: new Set(["projects", "dryRun", "json", "resetAgentModels", "components"]),
  feedback: new Set(["projects", "json"]),
};

function validateCommandArgs(args){
  const allowed = COMMAND_ARGS[args.cmd];
  if (!allowed) return;
  const invalid = [...args.provided].filter(name => !allowed.has(name));
  if (invalid.length) {
    die(`${invalid.map(name => ARG_FLAGS[name] || name).join(", ")} not valid for '${args.cmd}'`);
  }
  if (args.cmd === "sync" && args.components !== "all") {
    die("partial Skill sync was removed in 4.1; use --components all so Skill, AGENTS.md, ENGINEERING.md, agents, and runtime converge together");
  }
  if (args.cmd === "feedback" && (!args.projectsFlagProvided || args.projects.length === 0)) {
    die("'feedback' requires explicit --projects <path[,path...]>");
  }
}

function exists(p){ try { fs.accessSync(p); return true; } catch { return false; } }
function rmrf(p){ fs.rmSync(p, { recursive: true, force: true }); }
function quoted(value){ return JSON.stringify(String(value)); }

function requireRuntimeDependencies(assetSkill){
  const defaultPython = process.platform === "win32" ? "python" : "python3";
  const python = String(process.env.AUTOCODING_PYTHON || defaultPython).trim() || defaultPython;
  const requirements = path.join(assetSkill, "requirements.txt");
  if (!exists(requirements)) die(`missing runtime dependency definition: ${requirements}`);
  const check = spawnSync(
    python,
    ["-c", "import yaml"],
    { encoding: "utf8", stdio: "pipe" },
  );
  if (check.status === 0) return;
  const detail = String(check.stderr || check.error?.message || "PyYAML import failed").trim().split(/\r?\n/).slice(-1)[0];
  const install = `${quoted(python)} -m pip install --requirement ${quoted(requirements)}`;
  die(
    `Python runtime dependency check failed${detail ? `: ${detail}` : ""}\n`
    + `Run: ${install}\nThen rerun autocoding init.`,
  );
}

function runtimePython(){
  const fallback = process.platform === "win32" ? "python" : "python3";
  return String(process.env.AUTOCODING_PYTHON || fallback).trim() || fallback;
}

function readInstallManifest(file){
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    die(`invalid managed install manifest ${file}: ${error.message}`);
  }
  if (manifest?.schema_version !== 1 || !/^\d+\.\d+\.\d+$/.test(String(manifest?.skill_version || ""))) {
    die(`invalid managed install manifest schema/version: ${file}`);
  }
  if (!Array.isArray(manifest.entries) || !Array.isArray(manifest.managed_namespaces)) {
    die(`invalid managed install manifest entries/namespaces: ${file}`);
  }
  return manifest;
}

function installManifestTarget(root){
  return path.join(root, ".agents", "managed-install.json");
}

function copyInstallManifest(assetManifest, root){
  const target = installManifestTarget(root);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(assetManifest, target);
  return target;
}

function applyManifestExecutableBits(root, manifest, mode){
  if (process.platform === "win32") return;
  const scopes = new Set(mode === "project" ? ["shared", "project"] : ["shared"]);
  if (safeProjectMutationRequired) {
    const mutations = [];
    for (const entry of manifest.entries) {
      if (!scopes.has(entry.scope) || typeof entry.path !== "string" || typeof entry.executable !== "boolean") continue;
      const target = path.join(root, ...entry.path.split("/"));
      const { relative } = projectRelativePath(root, target);
      mutations.push({
        path: relative.split(path.sep).join("/"),
        mode: entry.executable ? "755" : "644",
      });
    }
    runSafeProjectChmodBatch(root, mutations);
    return;
  }
  for (const entry of manifest.entries) {
    if (!scopes.has(entry.scope) || typeof entry.path !== "string" || typeof entry.executable !== "boolean") continue;
    const target = path.join(root, ...entry.path.split("/"));
    if (!exists(target) || fs.lstatSync(target).isSymbolicLink()) continue;
    const current = fs.statSync(target).mode & 0o777;
    const desired = entry.executable ? (current | 0o111) : (current & ~0o111);
    if (desired !== current) fs.chmodSync(target, desired);
  }
}

function installIntegrityStatus(root, mode, expectedVersion){
  const script = path.join(root, ".agents", "skills", "auto-coding-skill", "scripts", "install_integrity.py");
  if (!exists(script)) {
    return { ok: false, version: "", checked: 0, errors: ["managed integrity verifier is missing"] };
  }
  const result = spawnSync(
    runtimePython(),
    [script, "verify", "--repo", root, "--mode", mode, "--expected-version", expectedVersion, "--json"],
    { encoding: "utf8", stdio: "pipe" },
  );
  try {
    const parsed = JSON.parse(result.stdout || "{}");
    if (typeof parsed.ok === "boolean" && Array.isArray(parsed.errors)) return parsed;
  } catch {
    // Fall through to a deterministic diagnostic below.
  }
  const detail = String(result.stderr || result.stdout || result.error?.message || "integrity verifier failed").trim();
  return { ok: false, version: "", checked: 0, errors: [detail || "integrity verifier returned invalid output"] };
}

function requireInstallIntegrity(root, mode, expectedVersion){
  const result = installIntegrityStatus(root, mode, expectedVersion);
  if (!result.ok) die(`managed install integrity verification failed:\n- ${result.errors.join("\n- ")}`);
  return result;
}

function runEngineeringConvergence(project, skillRoot, write, installToken = "", transaction = null){
  if (transaction) requireInstalledTransactionIntegrity(project, transaction);
  const script = path.join(skillRoot, "scripts", "ap.py");
  const command = [script, "--repo", project, "project-converge", "--json"];
  if (write) command.push("--write");
  const result = spawnSync(runtimePython(), command, {
    encoding: "utf8",
    stdio: "pipe",
    env: installToken
      ? { ...process.env, AUTOCODING_INSTALL_TRANSACTION_TOKEN: installToken }
      : process.env,
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "project convergence failed").trim();
    die(`unable to converge docs/ENGINEERING.md: ${detail}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    die("project convergence returned invalid JSON");
  }
}

function runProjectConfigPrepare(project, skillRoot, write){
  const script = path.join(skillRoot, "scripts", "ap.py");
  const command = [script, "--repo", project, "project-config-prepare", "--json"];
  if (write) command.push("--write");
  const result = spawnSync(runtimePython(), command, { encoding: "utf8", stdio: "pipe" });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "project configuration prepare failed").trim();
    die(`unable to prepare project configuration: ${detail}`);
  }
  try {
    const parsed = JSON.parse(result.stdout);
    if (
      typeof parsed?.finalize_required !== "boolean"
      || !/^[0-9a-f]{64}$/.test(String(parsed?.engineering_before_sha256 || ""))
      || !/^[0-9a-f]{64}$/.test(String(parsed?.overlay_sha256 || ""))
      || !/^[0-9a-f]{64}$/.test(String(parsed?.template_sha256 || ""))
      || !Array.isArray(parsed?.actions)
    ) throw new Error("unexpected prepare contract");
    return parsed;
  } catch {
    die("project configuration prepare returned invalid JSON");
  }
}

function runProjectConfigFinalize(project, skillRoot, prepared, write, installToken = "", transaction = null){
  if (transaction) requireInstalledTransactionIntegrity(project, transaction);
  const script = path.join(skillRoot, "scripts", "ap.py");
  const command = [
    script,
    "--repo", project,
    "project-config-finalize",
    "--engineering-sha256", prepared.engineering_before_sha256,
    "--overlay-sha256", prepared.overlay_sha256,
    "--template-sha256", prepared.template_sha256,
    "--json",
  ];
  if (write) command.push("--write");
  const result = spawnSync(runtimePython(), command, {
    encoding: "utf8",
    stdio: "pipe",
    env: installToken
      ? { ...process.env, AUTOCODING_INSTALL_TRANSACTION_TOKEN: installToken }
      : process.env,
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "project configuration finalize failed").trim();
    die(`unable to finalize project configuration: ${detail}`);
  }
  try {
    const parsed = JSON.parse(result.stdout);
    if (!Array.isArray(parsed?.actions)) throw new Error("unexpected finalize contract");
    return parsed;
  } catch {
    die("project configuration finalize returned invalid JSON");
  }
}

function readEffectiveConfigStatus(project, skillRoot){
  const script = path.join(skillRoot, "scripts", "ap.py");
  const result = spawnSync(
    runtimePython(),
    [script, "--repo", project, "config-effective", "--json"],
    { encoding: "utf8", stdio: "pipe" },
  );
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "effective config check failed").trim();
    return { ok: false, error: detail || "effective config check failed", fields: {}, policy_issues: [] };
  }
  try {
    const parsed = JSON.parse(result.stdout);
    if (parsed?.schema !== "auto-coding-skill/effective-config-status/v1" || typeof parsed.fields !== "object") {
      throw new Error("unexpected schema");
    }
    return { ...parsed, ok: true };
  } catch {
    return { ok: false, error: "effective config check returned invalid JSON", fields: {}, policy_issues: [] };
  }
}

function runManagedScaffoldConvergence(project, skillRoot, group, write){
  const script = path.join(skillRoot, "scripts", "ap.py");
  const command = [script, "--repo", project, "managed-scaffold-converge", group, "--json"];
  if (write) command.push("--write");
  const result = spawnSync(runtimePython(), command, { encoding: "utf8", stdio: "pipe" });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "managed scaffold convergence failed").trim();
    die(`unable to converge managed ${group} scaffold: ${detail}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    die(`managed ${group} scaffold convergence returned invalid JSON`);
  }
}
function shouldSkip(name){
  return name === "__pycache__" || name === ".DS_Store" || /\.py[cod]$/i.test(name);
}

function copyDir(src, dst){
  fs.mkdirSync(dst, { recursive: true });
  for (const ent of fs.readdirSync(src, { withFileTypes: true })) {
    if (shouldSkip(ent.name)) continue;
    const s = path.join(src, ent.name);
    const d = path.join(dst, ent.name);
    if (ent.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

const INSTALL_TRANSACTION_NAME = ".auto-coding-skill-install-transaction";
const INSTALL_TRANSACTION_SCHEMA = 1;
const INSTALL_TRANSACTION_OWNER_SCHEMA = 1;
let trustedProjectFileHelper = "";
let activeInstallTransactionToken = "";
let safeProjectMutationRequired = false;

function sha256File(file){
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function realDirectory(directory, label){
  let metadata;
  try {
    metadata = fs.lstatSync(directory);
  } catch (error) {
    die(`${label} is unavailable: ${error.code || "read-error"}`);
  }
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) die(`${label} must be a real directory`);
}

function regularFile(file, label){
  let metadata;
  try {
    metadata = fs.lstatSync(file);
  } catch (error) {
    die(`${label} is unavailable: ${error.code || "read-error"}`);
  }
  if (!metadata.isFile() || metadata.isSymbolicLink()) die(`${label} must be a regular non-symlink file`);
}

function canonicalProjectRoot(root){
  try {
    return fs.realpathSync(path.resolve(root));
  } catch (error) {
    die(`project root is unavailable: ${error.code || "realpath-error"}`);
  }
}

function projectDirectoryChain(root, relative, create = false){
  const canonicalRoot = canonicalProjectRoot(root);
  const parts = String(relative || "").split(/[\\/]+/).filter(Boolean);
  let current = canonicalRoot;
  realDirectory(current, "project root");
  for (const part of parts) {
    if (part === "." || part === "..") die(`unsafe project directory path: ${relative}`);
    current = path.join(current, part);
    let metadata;
    try {
      metadata = fs.lstatSync(current);
    } catch (error) {
      if (error.code !== "ENOENT" || !create) return null;
      fs.mkdirSync(current);
      metadata = fs.lstatSync(current);
    }
    if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
      die(`project directory chain contains a symlink, junction, or non-directory: ${relative}`);
    }
    let resolved;
    try {
      resolved = fs.realpathSync(current);
    } catch (error) {
      die(`project directory chain could not be verified: ${error.code || "realpath-error"}`);
    }
    const normalize = value => process.platform === "win32"
      ? path.normalize(value).toLowerCase()
      : path.normalize(value);
    if (normalize(resolved) !== normalize(current)) {
      die(`project directory chain contains a symlink or junction: ${relative}`);
    }
  }
  return current;
}

function lstatIfPresent(candidate){
  try {
    return fs.lstatSync(candidate);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    die(`install transaction input is unavailable: ${error.code || "lstat-error"}`);
  }
}

function validateInstallTransactionInputs(root, assetSkill, assetManifest){
  root = canonicalProjectRoot(root);
  projectDirectoryChain(root, ".agents", false);
  projectDirectoryChain(root, path.join(".agents", "skills"), false);
  projectDirectoryChain(root, "docs", false);
  directorySha256(assetSkill);
  regularFile(assetManifest, "managed install source manifest");

  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const skillMetadata = lstatIfPresent(skillDir);
  if (skillMetadata) {
    if (!skillMetadata.isDirectory() || skillMetadata.isSymbolicLink()) {
      die(`installed Skill must be a real directory before convergence: ${root}`);
    }
    directorySha256(skillDir);
  }
  const manifest = installManifestTarget(root);
  if (lstatIfPresent(manifest)) regularFile(manifest, "installed managed manifest");
  const engineering = path.join(root, "docs", "ENGINEERING.md");
  if (lstatIfPresent(engineering)) regularFile(engineering, "managed ENGINEERING document");
}

function projectRelativePath(root, candidate){
  const lexicalRoot = path.resolve(root);
  const canonicalRoot = canonicalProjectRoot(root);
  const absolute = path.resolve(candidate);
  const relative = path.relative(lexicalRoot, absolute);
  if (!relative || relative === "." || relative.startsWith("..") || path.isAbsolute(relative)) {
    die(`unsafe project file target: ${candidate}`);
  }
  return { canonicalRoot, relative };
}

function validateProjectFileTarget(root, candidate, label){
  const { canonicalRoot, relative } = projectRelativePath(root, candidate);
  const parent = path.dirname(relative);
  if (parent !== "." && !projectDirectoryChain(canonicalRoot, parent, false)) return;
  const target = path.join(canonicalRoot, relative);
  const metadata = lstatIfPresent(target);
  if (metadata && (!metadata.isFile() || metadata.isSymbolicLink())) {
    die(`${label} must be a regular non-symlink file: ${relative}`);
  }
}

const ARCHIVE_TARGET_ATTEMPTS = 64;

function selectProjectArchiveTarget(root, preferred, payload, options = {}){
  const lexicalRoot = path.resolve(root);
  const { relative } = projectRelativePath(lexicalRoot, preferred);
  const intended = Buffer.isBuffer(payload) ? payload : Buffer.from(String(payload), "utf8");
  const legacyPayload = options.legacyDigestPayload === undefined
    ? intended
    : (Buffer.isBuffer(options.legacyDigestPayload)
      ? options.legacyDigestPayload
      : Buffer.from(String(options.legacyDigestPayload), "utf8"));
  const payloadDigest = crypto.createHash("sha256").update(intended).digest("hex");
  const legacyDigest = crypto.createHash("sha256").update(legacyPayload).digest("hex").slice(0, 12);
  const normalizedRelative = relative.split(path.sep).join("/");
  const pathDigest = crypto.createHash("sha256").update(normalizedRelative).digest("hex").slice(0, 12);
  const absolutePreferred = path.join(lexicalRoot, relative);
  const parsed = path.parse(absolutePreferred);
  const legacyCandidate = path.join(parsed.dir, `${parsed.name}-${legacyDigest}${parsed.ext}`);
  const compactStem = `.autocoding-archive-${pathDigest}-${payloadDigest}`;
  const candidates = [absolutePreferred];
  if (Buffer.byteLength(path.basename(legacyCandidate), "utf8") <= 240) candidates.push(legacyCandidate);
  candidates.push(path.join(parsed.dir, `${compactStem}${parsed.ext}`));
  for (let attempt = 2; attempt <= ARCHIVE_TARGET_ATTEMPTS; attempt += 1) {
    candidates.push(path.join(parsed.dir, `${compactStem}-${attempt}${parsed.ext}`));
  }

  const seen = new Set();
  for (const candidate of candidates) {
    const key = process.platform === "win32" ? path.normalize(candidate).toLowerCase() : path.normalize(candidate);
    if (seen.has(key)) continue;
    seen.add(key);
    validateProjectFileTarget(lexicalRoot, candidate, "project archive target");
    const metadata = lstatIfPresent(candidate);
    if (!metadata) return { path: candidate, archiveRequired: true };
    const existing = fs.readFileSync(candidate);
    if (existing.equals(intended)) return { path: candidate, archiveRequired: false };
  }
  die(
    "cannot allocate a collision-free project archive target without overwriting different content: "
    + normalizedRelative,
  );
}

function runSafeProjectFileMutation(root, candidate, operation, payload = null, mode = null){
  if (!safeProjectMutationRequired) return false;
  if (!trustedProjectFileHelper || !activeInstallTransactionToken) {
    die("project mutation requires the trusted source helper and active install transaction");
  }
  const { canonicalRoot, relative } = projectRelativePath(root, candidate);
  const command = [
    trustedProjectFileHelper,
    "--repo", canonicalRoot,
    "project-file-safe", operation,
    "--path", relative.split(path.sep).join("/"),
    "--json",
  ];
  if (mode !== null) command.push("--mode", mode.toString(8));
  const result = spawnSync(runtimePython(), command, {
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    input: payload === null ? undefined : (Buffer.isBuffer(payload) ? payload : Buffer.from(String(payload))),
    maxBuffer: 34 * 1024 * 1024,
    env: {
      ...process.env,
      AUTOCODING_INSTALL_TRANSACTION_TOKEN: activeInstallTransactionToken,
    },
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "safe project mutation failed").trim();
    die(`trusted project mutation failed: ${detail}`);
  }
  return true;
}

function runSafeProjectChmodBatch(root, mutations){
  if (!safeProjectMutationRequired) return false;
  if (!trustedProjectFileHelper || !activeInstallTransactionToken) {
    die("project chmod batch requires the trusted source helper and active install transaction");
  }
  const canonicalRoot = canonicalProjectRoot(root);
  const result = spawnSync(runtimePython(), [
    trustedProjectFileHelper,
    "--repo", canonicalRoot,
    "project-file-safe", "chmod-batch",
    "--json",
  ], {
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    input: Buffer.from(JSON.stringify(mutations), "utf8"),
    maxBuffer: 2 * 1024 * 1024,
    env: {
      ...process.env,
      AUTOCODING_INSTALL_TRANSACTION_TOKEN: activeInstallTransactionToken,
    },
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "safe project chmod batch failed").trim();
    die(`trusted project chmod batch failed: ${detail}`);
  }
  return true;
}

function runInstallIoPhase(root, operation, transaction, state = null){
  if (!trustedProjectFileHelper) die("install I/O requires the trusted source helper");
  const command = [
    trustedProjectFileHelper,
    "--repo", canonicalProjectRoot(root),
    "install-io", operation,
    "--json",
  ];
  if (operation === "recover") {
    if (state?.old_skill_present) command.push("--old-skill-present");
    if (state?.old_manifest_present) command.push("--old-manifest-present");
    if (state?.old_engineering_present) command.push("--old-engineering-present");
  }
  const token = transaction?.token || "";
  const result = spawnSync(runtimePython(), command, {
    encoding: "utf8",
    stdio: "pipe",
    env: token
      ? { ...process.env, AUTOCODING_INSTALL_TRANSACTION_TOKEN: token }
      : process.env,
  });
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || result.error?.message || "install I/O phase failed").trim();
    die(`trusted install I/O ${operation} failed: ${detail}`);
  }
}

function atomicWriteProjectFile(root, candidate, payload, mode = null){
  if (runSafeProjectFileMutation(root, candidate, "write", payload, mode)) return;
  const { canonicalRoot, relative } = projectRelativePath(root, candidate);
  const parentRelative = path.dirname(relative);
  const parent = parentRelative === "."
    ? canonicalRoot
    : projectDirectoryChain(canonicalRoot, parentRelative, true);
  validateProjectFileTarget(canonicalRoot, path.join(canonicalRoot, relative), "managed project target");
  const target = path.join(canonicalRoot, relative);
  const temporary = path.join(parent, `.autocoding-${process.pid}-${crypto.randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, payload, mode === null ? undefined : { mode });
    if (mode !== null && process.platform !== "win32") fs.chmodSync(temporary, mode);
    try {
      fs.renameSync(temporary, target);
    } catch (error) {
      if (
        process.platform !== "win32"
        || !["EEXIST", "EPERM", "EACCES"].includes(String(error.code || ""))
      ) throw error;
      validateProjectFileTarget(canonicalRoot, target, "managed project target");
      fs.rmSync(target, { force: true });
      fs.renameSync(temporary, target);
    }
  } finally {
    try { fs.rmSync(temporary, { force: true }); } catch {}
  }
}

function atomicCreateProjectFile(root, candidate, payload, mode = null){
  if (runSafeProjectFileMutation(root, candidate, "create", payload, mode)) return;
  const { canonicalRoot, relative } = projectRelativePath(root, candidate);
  const parentRelative = path.dirname(relative);
  const parent = parentRelative === "."
    ? canonicalRoot
    : projectDirectoryChain(canonicalRoot, parentRelative, true);
  validateProjectFileTarget(canonicalRoot, path.join(canonicalRoot, relative), "create-only project target");
  const target = path.join(canonicalRoot, relative);
  if (lstatIfPresent(target)) die(`project file appeared before create-only publish: ${relative}`);
  const temporary = path.join(parent, `.autocoding-${process.pid}-${crypto.randomUUID()}.tmp`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", mode === null ? 0o644 : mode);
    fs.writeFileSync(descriptor, payload);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    const temporaryMetadata = fs.lstatSync(temporary);
    if (!temporaryMetadata.isFile() || temporaryMetadata.isSymbolicLink()) {
      die(`temporary create-only project file is unsafe: ${relative}`);
    }
    try {
      fs.linkSync(temporary, target);
    } catch (error) {
      if (error.code === "EEXIST") die(`project file appeared before create-only publish: ${relative}`);
      throw error;
    }
    const published = fs.lstatSync(target);
    if (
      !published.isFile()
      || published.isSymbolicLink()
      || published.dev !== temporaryMetadata.dev
      || published.ino !== temporaryMetadata.ino
    ) die(`project file changed during create-only publish: ${relative}`);
    if (mode !== null && process.platform !== "win32") fs.chmodSync(target, mode);
  } finally {
    if (descriptor !== undefined) {
      try { fs.closeSync(descriptor); } catch {}
    }
    try { fs.unlinkSync(temporary); } catch {}
  }
}

function validateProjectManagedTargets(root, assetAgents){
  root = canonicalProjectRoot(root);
  for (const directory of [
    path.join(".agents", "agents"),
    path.join("docs", "tools", "autopipeline"),
    path.join("docs", "archive", "workflow"),
  ]) projectDirectoryChain(root, directory, false);
  validateProjectFileTarget(root, path.join(root, "AGENTS.md"), "root AGENTS.md");
  validateProjectFileTarget(
    root,
    path.join(root, "docs", "tools", "autopipeline", "ap.py"),
    "project launcher",
  );
  for (const relative of listFiles(assetAgents)) {
    validateProjectFileTarget(
      root,
      path.join(root, ".agents", "agents", relative),
      "managed agent",
    );
  }
}

function copyDirStrict(src, dst){
  realDirectory(src, "install transaction source directory");
  fs.mkdirSync(dst, { recursive: true });
  realDirectory(dst, "install transaction destination directory");
  for (const ent of fs.readdirSync(src, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (shouldSkip(ent.name)) continue;
    if (ent.isSymbolicLink() || (!ent.isDirectory() && !ent.isFile())) {
      die(`install transaction refuses a non-regular entry: ${path.join(src, ent.name)}`);
    }
    const source = path.join(src, ent.name);
    const target = path.join(dst, ent.name);
    if (ent.isDirectory()) copyDirStrict(source, target);
    else fs.copyFileSync(source, target);
  }
}

function directorySha256(root){
  realDirectory(root, "install transaction directory");
  const digest = crypto.createHash("sha256");
  const addRecord = record => {
    const payload = Buffer.from(JSON.stringify(record), "utf8");
    const length = Buffer.alloc(8);
    length.writeBigUInt64BE(BigInt(payload.length));
    digest.update(length);
    digest.update(payload);
  };
  const visit = (directory, prefix = "") => {
    for (const ent of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (shouldSkip(ent.name)) continue;
      const relative = prefix ? `${prefix}/${ent.name}` : ent.name;
      const candidate = path.join(directory, ent.name);
      if (ent.isSymbolicLink() || (!ent.isDirectory() && !ent.isFile())) {
        die(`install transaction refuses a non-regular entry: ${candidate}`);
      }
      if (ent.isDirectory()) {
        addRecord({ type: "directory", path: relative });
        visit(candidate, relative);
      } else {
        const payload = fs.readFileSync(candidate);
        const mode = fs.statSync(candidate).mode;
        addRecord({
          type: "file",
          path: relative,
          size: payload.length,
          sha256: crypto.createHash("sha256").update(payload).digest("hex"),
          executable: process.platform === "win32" ? false : Boolean(mode & 0o111),
        });
      }
    }
  };
  visit(root);
  return digest.digest("hex");
}

function atomicCopyFile(source, target){
  regularFile(source, "install transaction source file");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temporary = `${target}.autocoding-${process.pid}-${crypto.randomUUID()}.tmp`;
  try {
    fs.copyFileSync(source, temporary);
    if (process.platform !== "win32") fs.chmodSync(temporary, fs.statSync(source).mode & 0o777);
    fs.renameSync(temporary, target);
  } catch (error) {
    try { fs.rmSync(temporary, { force: true }); } catch {}
    if (
      process.platform === "win32"
      && ["EEXIST", "EPERM", "EACCES"].includes(String(error.code || ""))
      && exists(target)
    ) {
      fs.rmSync(target, { force: true });
      fs.copyFileSync(source, target);
      return;
    }
    throw error;
  }
}

function installTransactionPaths(root){
  root = canonicalProjectRoot(root);
  const agentsRoot = path.join(root, ".agents");
  const directory = path.join(agentsRoot, INSTALL_TRANSACTION_NAME);
  return {
    root,
    agentsRoot,
    directory,
    owner: path.join(directory, "owner.json"),
    state: path.join(directory, "state.json"),
    newSkill: path.join(directory, "new-skill"),
    newManifest: path.join(directory, "new-manifest.json"),
    oldSkill: path.join(directory, "old-skill"),
    oldManifest: path.join(directory, "old-manifest.json"),
    oldEngineering: path.join(directory, "old-ENGINEERING.md"),
  };
}

function writeInstallTransactionOwner(transaction){
  const tokenSha256 = crypto.createHash("sha256").update(transaction.token).digest("hex");
  const owner = {
    schema: INSTALL_TRANSACTION_OWNER_SCHEMA,
    pid: process.pid,
    started_at: new Date().toISOString(),
    token_sha256: tokenSha256,
  };
  const descriptor = fs.openSync(transaction.owner, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(owner)}\n`, "utf8");
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  transaction.ownerPid = owner.pid;
  transaction.ownerTokenSha256 = owner.token_sha256;
  return owner;
}

function publishInstallTransactionOwner(transaction){
  const claimDirectory = path.join(
    transaction.agentsRoot,
    `${INSTALL_TRANSACTION_NAME}.claim-${process.pid}-${crypto.randomUUID()}`,
  );
  fs.mkdirSync(claimDirectory);
  const claim = {
    ...transaction,
    directory: claimDirectory,
    owner: path.join(claimDirectory, "owner.json"),
  };
  try {
    const owner = writeInstallTransactionOwner(claim);
    fs.renameSync(claimDirectory, transaction.directory);
    transaction.ownerPid = owner.pid;
    transaction.ownerTokenSha256 = owner.token_sha256;
    return owner;
  } catch (error) {
    rmrf(claimDirectory);
    if (lstatIfPresent(transaction.directory)) {
      die("another auto-coding-skill installer claimed this project; no install writes were made");
    }
    throw error;
  }
}

function readInstallTransactionOwner(transaction){
  regularFile(transaction.owner, "install transaction owner lease");
  let owner;
  try {
    const payload = fs.readFileSync(transaction.owner);
    if (payload.length > 4096) throw new Error("oversized owner lease");
    owner = JSON.parse(payload.toString("utf8"));
  } catch {
    die("install transaction has an invalid owner lease; no recovery writes were made");
  }
  if (
    owner?.schema !== INSTALL_TRANSACTION_OWNER_SCHEMA
    || !Number.isSafeInteger(owner.pid)
    || owner.pid <= 0
    || typeof owner.started_at !== "string"
    || !/^[0-9a-f]{64}$/.test(String(owner.token_sha256 || ""))
  ) die("install transaction has an unsupported owner lease; no recovery writes were made");
  return owner;
}

function installTransactionOwnerIsAlive(owner){
  try {
    process.kill(owner.pid, 0);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return false;
    if (error?.code === "EPERM") return true;
    die(`cannot verify install transaction owner liveness: ${error?.code || "process-error"}`);
  }
}

function requireInstallTransactionOwnerStopped(transaction){
  const owner = readInstallTransactionOwner(transaction);
  if (installTransactionOwnerIsAlive(owner)) {
    die(
      `auto-coding-skill install transaction is active under owner pid ${owner.pid}; `
      + "no recovery writes were made",
    );
  }
  return owner;
}

function installTransactionPending(root){
  const transaction = installTransactionPaths(root);
  if (!projectDirectoryChain(transaction.root, ".agents", false)) return false;
  const metadata = lstatIfPresent(transaction.directory);
  if (!metadata) return false;
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
    die("auto-coding-skill install transaction path must be a real directory");
  }
  return true;
}

function readInstallTransactionState(transaction){
  const owner = readInstallTransactionOwner(transaction);
  regularFile(transaction.state, "install transaction state");
  let state;
  try {
    const payload = fs.readFileSync(transaction.state);
    if (payload.length > 64 * 1024) throw new Error("oversized state");
    state = JSON.parse(payload.toString("utf8"));
  } catch {
    die("interrupted install transaction has an invalid state file; no recovery writes were made");
  }
  const validHash = value => /^[0-9a-f]{64}$/.test(String(value || ""));
  if (
    state?.schema !== INSTALL_TRANSACTION_SCHEMA
    || typeof state.old_skill_present !== "boolean"
    || typeof state.old_manifest_present !== "boolean"
    || typeof state.old_engineering_present !== "boolean"
    || state.owner_pid !== owner.pid
    || state.owner_token_sha256 !== owner.token_sha256
    || (state.old_skill_present && !validHash(state.old_skill_sha256))
    || (state.old_manifest_present && !validHash(state.old_manifest_sha256))
    || (state.old_engineering_present && !validHash(state.old_engineering_sha256))
    || !validHash(state.staged_skill_sha256)
    || !validHash(state.staged_manifest_sha256)
    || !validHash(state.internal_token_sha256)
  ) die("interrupted install transaction has an unsupported state contract; no recovery writes were made");
  return state;
}

function requireActiveInstallTransactionBinding(transaction, state){
  const expectedTokenSha256 = crypto.createHash("sha256").update(transaction.token || "").digest("hex");
  if (
    transaction.ownerPid !== process.pid
    || state.owner_pid !== process.pid
    || transaction.ownerTokenSha256 !== expectedTokenSha256
    || state.owner_token_sha256 !== expectedTokenSha256
    || state.internal_token_sha256 !== expectedTokenSha256
    || state.staged_skill_sha256 !== transaction.stagedSkillSha256
    || state.staged_manifest_sha256 !== transaction.stagedManifestSha256
  ) die("active install transaction binding changed before managed runtime execution");
}

function requireStagedInstallIntegrity(transaction){
  const state = readInstallTransactionState(transaction);
  requireActiveInstallTransactionBinding(transaction, state);
  realDirectory(transaction.newSkill, "staged install Skill");
  regularFile(transaction.newManifest, "staged install manifest");
  if (directorySha256(transaction.newSkill) !== state.staged_skill_sha256) {
    die("staged Skill failed its transaction identity check before install");
  }
  if (sha256File(transaction.newManifest) !== state.staged_manifest_sha256) {
    die("staged manifest failed its transaction identity check before install");
  }
  return state;
}

function requireInstalledTransactionIntegrity(root, transaction){
  const state = readInstallTransactionState(transaction);
  requireActiveInstallTransactionBinding(transaction, state);
  const canonicalRoot = transaction.root || canonicalProjectRoot(root);
  const skillDir = path.join(canonicalRoot, ".agents", "skills", "auto-coding-skill");
  const manifest = installManifestTarget(canonicalRoot);
  realDirectory(skillDir, "installed transaction Skill");
  regularFile(manifest, "installed transaction manifest");
  if (directorySha256(skillDir) !== state.staged_skill_sha256) {
    die("installed Skill changed before the transaction runtime could execute");
  }
  if (sha256File(manifest) !== state.staged_manifest_sha256) {
    die("installed manifest changed before the transaction runtime could execute");
  }
  return state;
}

function completeInstallTransaction(root, transaction){
  if (!exists(transaction.directory)) return;
  runInstallIoPhase(transaction.root || root, "complete", transaction);
  if (transaction.token && activeInstallTransactionToken === transaction.token) {
    activeInstallTransactionToken = "";
  }
}

function recoverInstallTransaction(root, write = true){
  const transaction = installTransactionPaths(root);
  if (!projectDirectoryChain(transaction.root, ".agents", false)) return false;
  if (!exists(transaction.directory)) return false;
  realDirectory(transaction.directory, "auto-coding-skill install transaction");
  requireInstallTransactionOwnerStopped(transaction);
  if (!exists(transaction.state)) {
    // Canonical paths are never changed before state.json is durable.
    if (!write) return true;
    completeInstallTransaction(root, transaction);
    return true;
  }
  const state = readInstallTransactionState(transaction);

  // Validate every backup before touching any canonical path. The backups are
  // copied, never moved, so recovery itself can be safely retried.
  if (state.old_skill_present) {
    realDirectory(transaction.oldSkill, "install transaction old Skill backup");
    if (directorySha256(transaction.oldSkill) !== state.old_skill_sha256) {
      die("interrupted install transaction old Skill backup failed its identity check");
    }
  }
  if (state.old_manifest_present) {
    regularFile(transaction.oldManifest, "install transaction old manifest backup");
    if (sha256File(transaction.oldManifest) !== state.old_manifest_sha256) {
      die("interrupted install transaction old manifest backup failed its identity check");
    }
  }
  if (state.old_engineering_present) {
    regularFile(transaction.oldEngineering, "install transaction old ENGINEERING backup");
    if (sha256File(transaction.oldEngineering) !== state.old_engineering_sha256) {
      die("interrupted install transaction old ENGINEERING backup failed its identity check");
    }
  }

  if (!write) return true;

  runInstallIoPhase(transaction.root, "recover", transaction, state);
  const skillDir = path.join(transaction.root, ".agents", "skills", "auto-coding-skill");
  if (state.old_skill_present && directorySha256(skillDir) !== state.old_skill_sha256) {
    die("restored Skill backup failed verification");
  }
  const manifest = installManifestTarget(transaction.root);
  if (state.old_manifest_present && sha256File(manifest) !== state.old_manifest_sha256) {
    die("restored manifest backup failed verification");
  }
  const engineering = path.join(transaction.root, "docs", "ENGINEERING.md");
  if (state.old_engineering_present && sha256File(engineering) !== state.old_engineering_sha256) {
    die("restored ENGINEERING backup failed verification");
  }
  completeInstallTransaction(root, transaction);
  return true;
}

function beginInstallTransaction(root, assetSkill, assetManifest, prepared){
  recoverInstallTransaction(root, true);
  const transaction = installTransactionPaths(root);
  transaction.token = crypto.randomBytes(32).toString("hex");
  activeInstallTransactionToken = transaction.token;
  projectDirectoryChain(transaction.root, ".agents", true);
  projectDirectoryChain(transaction.root, path.join(".agents", "skills"), false);
  projectDirectoryChain(transaction.root, "docs", false);
  publishInstallTransactionOwner(transaction);
  copyDirStrict(assetSkill, transaction.newSkill);
  const stagedSkillSha256 = directorySha256(transaction.newSkill);
  if (stagedSkillSha256 !== directorySha256(assetSkill)) {
    die("staged Skill copy failed its identity check before install");
  }
  fs.copyFileSync(assetManifest, transaction.newManifest);
  const stagedManifestSha256 = sha256File(transaction.newManifest);
  if (stagedManifestSha256 !== sha256File(assetManifest)) {
    die("staged manifest copy failed its identity check before install");
  }
  transaction.stagedSkillSha256 = stagedSkillSha256;
  transaction.stagedManifestSha256 = stagedManifestSha256;

  const skillDir = path.join(transaction.root, ".agents", "skills", "auto-coding-skill");
  const manifest = installManifestTarget(transaction.root);
  const engineering = path.join(transaction.root, "docs", "ENGINEERING.md");
  const state = {
    schema: INSTALL_TRANSACTION_SCHEMA,
    old_skill_present: exists(skillDir),
    old_manifest_present: exists(manifest),
    old_engineering_present: exists(engineering),
    owner_pid: transaction.ownerPid,
    owner_token_sha256: transaction.ownerTokenSha256,
    old_skill_sha256: "",
    old_manifest_sha256: "",
    old_engineering_sha256: "",
    staged_skill_sha256: stagedSkillSha256,
    staged_manifest_sha256: stagedManifestSha256,
    prepared_engineering_sha256: prepared.engineering_before_sha256,
    prepared_overlay_sha256: prepared.overlay_sha256,
    target_template_sha256: prepared.template_sha256,
    internal_token_sha256: crypto.createHash("sha256").update(transaction.token).digest("hex"),
  };
  if (state.old_skill_present) {
    copyDirStrict(skillDir, transaction.oldSkill);
    state.old_skill_sha256 = directorySha256(transaction.oldSkill);
  }
  if (state.old_manifest_present) {
    regularFile(manifest, "installed managed manifest");
    fs.copyFileSync(manifest, transaction.oldManifest);
    state.old_manifest_sha256 = sha256File(transaction.oldManifest);
  }
  if (state.old_engineering_present) {
    regularFile(engineering, "managed ENGINEERING document");
    fs.copyFileSync(engineering, transaction.oldEngineering);
    state.old_engineering_sha256 = sha256File(transaction.oldEngineering);
    if (process.platform !== "win32") fs.chmodSync(transaction.oldEngineering, 0o600);
  }
  const stateDescriptor = fs.openSync(transaction.state, "wx", 0o600);
  try {
    fs.writeFileSync(stateDescriptor, `${JSON.stringify(state)}\n`, "utf8");
    fs.fsyncSync(stateDescriptor);
  } finally {
    fs.closeSync(stateDescriptor);
  }
  return transaction;
}

function switchInstallTransaction(root, transaction){
  requireStagedInstallIntegrity(transaction);
  runInstallIoPhase(transaction.root || root, "switch", transaction);
  requireInstalledTransactionIntegrity(root, transaction);
}

function injectInstallFault(phase){
  if (process.env.AUTOCODING_TEST_HOLD_PHASE === phase) {
    const requested = Number(process.env.AUTOCODING_TEST_HOLD_MILLISECONDS || "0");
    if (!Number.isFinite(requested) || requested <= 0 || requested > 15000) {
      throw new Error("AUTOCODING_TEST_HOLD_MILLISECONDS must be between 1 and 15000");
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, requested);
  }
  if (process.env.AUTOCODING_TEST_FAIL_PHASE === phase) {
    throw new Error(`injected auto-coding-skill install fault: ${phase}`);
  }
}

function listFiles(root, base = root){
  if (!exists(root)) return [];
  const out = [];
  for (const ent of fs.readdirSync(root, { withFileTypes: true })) {
    if (shouldSkip(ent.name)) continue;
    const p = path.join(root, ent.name);
    if (ent.isSymbolicLink() || (!ent.isDirectory() && !ent.isFile())) {
      die(`refusing a symlink, junction, or non-regular managed path: ${p}`);
    }
    if (ent.isDirectory()) out.push(...listFiles(p, base));
    else out.push(path.relative(base, p));
  }
  return out.sort();
}

function compareDirs(src, dst, options = {}){
  const includeExtra = options.includeExtra ?? true;
  const diffs = [];
  const srcFiles = listFiles(src);
  const dstFiles = listFiles(dst);
  const srcSet = new Set(srcFiles);
  const dstSet = new Set(dstFiles);
  for (const rel of srcFiles) {
    if (!dstSet.has(rel)) {
      diffs.push({ path: rel, status: "missing" });
      continue;
    }
    const srcBuf = fs.readFileSync(path.join(src, rel));
    const dstBuf = fs.readFileSync(path.join(dst, rel));
    if (!srcBuf.equals(dstBuf)) diffs.push({ path: rel, status: "stale" });
  }
  if (includeExtra) {
    for (const rel of dstFiles) {
      if (!srcSet.has(rel)) diffs.push({ path: rel, status: "extra" });
    }
  }
  return diffs;
}

const CORE_DOCS = [];

function isEscapedAt(text, index){
  let slashes = 0;
  for (let i = index - 1; i >= 0 && text[i] === "\\"; i -= 1) slashes += 1;
  return slashes % 2 === 1;
}

function nextMultilineState(line, initialState){
  let state = initialState;
  let quote = "";
  for (let i = 0; i < line.length;) {
    if (state) {
      const close = line.indexOf(state, i);
      if (close < 0) return state;
      if (state === '"""' && isEscapedAt(line, close)) {
        i = close + state.length;
        continue;
      }
      state = "";
      i = close + 3;
      continue;
    }
    if (quote) {
      if (line[i] === quote && (quote === "'" || !isEscapedAt(line, i))) quote = "";
      i += 1;
      continue;
    }
    if (line[i] === "#") return state;
    if (line.startsWith('"""', i) || line.startsWith("'''", i)) {
      state = line.slice(i, i + 3);
      i += 3;
      continue;
    }
    if (line[i] === '"' || line[i] === "'") quote = line[i];
    i += 1;
  }
  return state;
}

function parseTomlStringValue(raw){
  const value = raw.trimStart();
  if (!value || (value[0] !== '"' && value[0] !== "'")) {
    return { valid: false, error: "model must be a TOML string" };
  }
  const quote = value[0];
  let decoded = "";
  let end = -1;
  for (let i = 1; i < value.length; i += 1) {
    const ch = value[i];
    if (ch === quote) {
      end = i;
      break;
    }
    if (quote === "'" || ch !== "\\") {
      if (ch.charCodeAt(0) < 0x20) return { valid: false, error: "model contains a control character" };
      decoded += ch;
      continue;
    }
    i += 1;
    if (i >= value.length) return { valid: false, error: "model has an incomplete escape" };
    const escaped = value[i];
    const simpleEscapes = { b: "\b", t: "\t", n: "\n", f: "\f", r: "\r", '"': '"', "\\": "\\" };
    if (Object.hasOwn(simpleEscapes, escaped)) {
      decoded += simpleEscapes[escaped];
      continue;
    }
    if (escaped === "u" || escaped === "U") {
      const length = escaped === "u" ? 4 : 8;
      const hex = value.slice(i + 1, i + 1 + length);
      if (hex.length !== length || !/^[0-9A-Fa-f]+$/.test(hex)) {
        return { valid: false, error: `model has an invalid \\${escaped} escape` };
      }
      const codepoint = Number.parseInt(hex, 16);
      if (codepoint > 0x10ffff || (codepoint >= 0xd800 && codepoint <= 0xdfff)) {
        return { valid: false, error: "model has an invalid Unicode codepoint" };
      }
      decoded += String.fromCodePoint(codepoint);
      i += length;
      continue;
    }
    return { valid: false, error: `model has an unsupported escape \\${escaped}` };
  }
  if (end < 0) return { valid: false, error: "model string is not terminated" };
  const trailing = value.slice(end + 1).trimStart();
  if (trailing && !trailing.startsWith("#")) {
    return { valid: false, error: "model must contain only one TOML string value" };
  }
  if (!decoded.trim()) return { valid: false, error: "model must be a non-empty string" };
  return { valid: true, value: decoded };
}

function inspectTopLevelModel(text){
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const matches = [];
  let multiline = "";
  let inTable = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!multiline) {
      const trimmed = line.trimStart();
      if (trimmed.startsWith("[") && !trimmed.startsWith("[#")) inTable = true;
      if (!inTable) {
        const match = line.match(/^\s*(?:model|"model"|'model')\s*=\s*(.*)$/);
        if (match) {
          const parsed = parseTomlStringValue(match[1]);
          matches.push({ lineIndex: index, rawLine: line, ...parsed });
        }
      }
    }
    multiline = nextMultilineState(line, multiline);
  }
  if (matches.length > 1) {
    return { valid: false, error: "model is defined more than once", matches };
  }
  if (!matches.length) return { valid: true, present: false, matches };
  const model = matches[0];
  if (!model.valid) return { valid: false, error: model.error, matches };
  return { valid: true, present: true, value: model.value, rawLine: model.rawLine, lineIndex: model.lineIndex, matches };
}

function normalizeManagedAgent(text, modelInfo = inspectTopLevelModel(text)){
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (modelInfo.valid && modelInfo.present) lines.splice(modelInfo.lineIndex, 1);
  return lines.join("\n");
}

function renderManagedAgent(templateText, existingText, resetModel){
  const existingModel = inspectTopLevelModel(existingText || "");
  const modelLine = !resetModel && existingModel.valid && existingModel.present ? existingModel.rawLine : "";
  let rendered = normalizeManagedAgent(templateText);
  if (!modelLine) return rendered;
  const lines = rendered.split("\n");
  const descriptionIndex = lines.findIndex(line => line.startsWith("description = "));
  lines.splice(descriptionIndex >= 0 ? descriptionIndex + 1 : 0, 0, modelLine);
  return lines.join("\n");
}

function compareManagedAgents(assetAgents, agentsDir){
  const diffs = [];
  const bindings = [];
  for (const rel of listFiles(assetAgents)) {
    const src = path.join(assetAgents, rel);
    const dst = path.join(agentsDir, rel);
    if (!exists(dst)) {
      diffs.push({ path: rel, status: "missing" });
      bindings.push({ agent: rel, model: "inherit" });
      continue;
    }
    const srcText = fs.readFileSync(src, "utf8");
    const dstText = fs.readFileSync(dst, "utf8");
    const srcModel = inspectTopLevelModel(srcText);
    const dstModel = inspectTopLevelModel(dstText);
    if (!srcModel.valid) throw new Error(`invalid managed agent template ${rel}: ${srcModel.error}`);
    if (!dstModel.valid) {
      diffs.push({ path: rel, status: "invalid-model", detail: dstModel.error });
    } else if (normalizeManagedAgent(srcText, srcModel) !== normalizeManagedAgent(dstText, dstModel)) {
      diffs.push({ path: rel, status: "stale" });
    }
    bindings.push({
      agent: rel,
      model: !dstModel.valid ? "invalid" : (dstModel.present ? dstModel.value : "inherit"),
    });
  }
  return { diffs, bindings };
}

function syncManagedAgents(assetAgents, agentsDir, options = {}){
  const managedRoot = options.projectRoot || path.dirname(path.dirname(agentsDir));
  projectDirectoryChain(managedRoot, path.relative(path.resolve(managedRoot), path.resolve(agentsDir)), true);
  const bindings = [];
  const managedFiles = new Set(listFiles(assetAgents));
  for (const rel of listFiles(assetAgents)) {
    const src = path.join(assetAgents, rel);
    const dst = path.join(agentsDir, rel);
    const templateText = fs.readFileSync(src, "utf8");
    const existingText = exists(dst) ? fs.readFileSync(dst, "utf8") : "";
    const rendered = renderManagedAgent(templateText, existingText, options.resetModel === true);
    atomicWriteProjectFile(managedRoot, dst, rendered);
    const model = inspectTopLevelModel(rendered);
    bindings.push({ agent: rel, model: model.present ? model.value : "inherit" });
  }
  if (options.removeExtra === true) {
    for (const rel of listFiles(agentsDir)) {
      if (!managedFiles.has(rel)) fs.rmSync(path.join(agentsDir, rel), { force: true });
    }
  }
  return bindings;
}

function copyMissingDocs(assetSkill, project){
  const srcDocs = path.join(assetSkill, "data", "templates", "docs");
  const dstDocs = path.join(project, "docs");
  const copied = [];
  for (const rel of CORE_DOCS) {
    const src = path.join(srcDocs, rel);
    const dst = path.join(dstDocs, rel);
    if (!exists(dst)) {
      atomicCreateProjectFile(project, dst, fs.readFileSync(src));
      copied.push(path.join("docs", rel));
    }
  }
  return copied;
}

function renderEngineeringTemplate(templateText, project){
  void project;
  return templateText;
}

const MANAGED_WORKFLOW_START_TOKEN = "auto-coding-skill:managed-workflow:start";
const MANAGED_WORKFLOW_END_TOKEN = "auto-coding-skill:managed-workflow:end";
const MANAGED_WORKFLOW_START_RE = /<!--\s*auto-coding-skill:managed-workflow:start\s+version=([0-9]+\.[0-9]+\.[0-9]+)\s*-->/g;
const MANAGED_WORKFLOW_END_RE = /<!--\s*auto-coding-skill:managed-workflow:end\s*-->/g;
const MANAGED_AGENTS_START_TOKEN = "auto-coding-skill:managed-agents:start";
const MANAGED_AGENTS_END_TOKEN = "auto-coding-skill:managed-agents:end";
const MANAGED_AGENTS_START_RE = /<!--\s*auto-coding-skill:managed-agents:start\s+version=([0-9]+\.[0-9]+\.[0-9]+)\s*-->/g;
const MANAGED_AGENTS_END_RE = /<!--\s*auto-coding-skill:managed-agents:end\s*-->/g;

function tokenCount(text, token){
  return text.split(token).length - 1;
}

function inspectManagedRegion(text, startToken, endToken, startPattern, endPattern, label){
  const rawStarts = tokenCount(text, startToken);
  const rawEnds = tokenCount(text, endToken);
  if (rawStarts === 0 && rawEnds === 0) return { state: "absent" };

  const starts = [...text.matchAll(startPattern)];
  const ends = [...text.matchAll(endPattern)];
  if (rawStarts !== starts.length || rawEnds !== ends.length) {
    return { state: "invalid", detail: `managed ${label} marker is malformed` };
  }
  if (starts.length !== 1 || ends.length !== 1) {
    return { state: "invalid", detail: `managed ${label} markers must contain exactly one start/end pair` };
  }
  const start = starts[0].index;
  const end = ends[0].index;
  if (start >= end) {
    return { state: "invalid", detail: "managed workflow markers are out of order or nested" };
  }
  const endExclusive = end + ends[0][0].length;
  return {
    state: "present",
    version: starts[0][1],
    start,
    endExclusive,
    block: text.slice(start, endExclusive),
  };
}

function inspectManagedWorkflow(text){
  return inspectManagedRegion(
    text,
    MANAGED_WORKFLOW_START_TOKEN,
    MANAGED_WORKFLOW_END_TOKEN,
    MANAGED_WORKFLOW_START_RE,
    MANAGED_WORKFLOW_END_RE,
    "workflow",
  );
}

function inspectManagedAgentsDocument(text){
  return inspectManagedRegion(
    text,
    MANAGED_AGENTS_START_TOKEN,
    MANAGED_AGENTS_END_TOKEN,
    MANAGED_AGENTS_START_RE,
    MANAGED_AGENTS_END_RE,
    "agents",
  );
}

function loadWorkflowMigrationPolicy(assetSkill){
  const policyPath = path.join(assetSkill, "data", "policies", "workflow-migrations-v1.json");
  let policy;
  try {
    policy = JSON.parse(fs.readFileSync(policyPath, "utf8"));
  } catch (error) {
    throw new Error(`invalid workflow migration policy ${policyPath}: ${error.message}`);
  }
  if (
    policy?.schema_version !== 1
    || !policy.managed_versions?.agents
    || !policy.managed_versions?.engineering
    || !Array.isArray(policy.known_official_agents_sha256)
    || !Array.isArray(policy.known_official_engineering_body_sha256)
    || !Array.isArray(policy.known_official_fragments)
    || !Array.isArray(policy.conflict_rules)
  ) {
    throw new Error(`invalid workflow migration policy schema: ${policyPath}`);
  }
  return policy;
}

function escapeRegExp(text){
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function applyKnownOfficialFragments(text, documentPath, policy){
  let output = text;
  const migrations = [];
  for (const fragment of policy.known_official_fragments) {
    if (!fragment.paths?.includes(documentPath) || !fragment.text) continue;
    let pattern;
    if (fragment.match === "heading-section") {
      const lines = output.match(/.*(?:\r?\n|$)/g).filter(Boolean);
      const offsets = [];
      let cursor = 0;
      for (const line of lines) {
        offsets.push(cursor);
        cursor += line.length;
      }
      const spans = [];
      for (let index = 0; index < lines.length; index += 1) {
        const heading = lines[index].replace(/\r?\n$/, "").match(/^(\s*)(#{1,6})\s+(.+?)\s*#*\s*$/);
        if (!heading || heading[3].trim() !== fragment.text.trim()) continue;
        const level = heading[2].length;
        let end = index + 1;
        while (end < lines.length) {
          const next = lines[end].replace(/\r?\n$/, "").match(/^\s*(#{1,6})\s+/);
          if (next && next[1].length <= level) break;
          end += 1;
        }
        spans.push([offsets[index], end < lines.length ? offsets[end] : output.length]);
      }
      if (spans.length) {
        for (const [start, end] of spans.reverse()) output = output.slice(0, start) + output.slice(end);
        migrations.push(fragment.id);
      }
      continue;
    } else if (fragment.match === "exact-line") {
      pattern = new RegExp(`^[\\t ]*${escapeRegExp(fragment.text.trim())}[\\t ]*(?:\\r?\\n|$)`, "gm");
    } else if (fragment.match === "exact-block") {
      const source = fragment.text.split("\n").map(escapeRegExp).join("\\r?\\n");
      pattern = new RegExp(source, "g");
    } else {
      throw new Error(`unsupported workflow migration match '${fragment.match}' for ${fragment.id}`);
    }
    const replacement = typeof fragment.replacement === "string" ? fragment.replacement : "";
    const updated = output.replace(pattern, matched => {
      if (!replacement) return "";
      if (fragment.match !== "exact-line") return replacement;
      const eol = matched.endsWith("\r\n") ? "\r\n" : (matched.endsWith("\n") ? "\n" : "");
      return `${replacement}${eol}`;
    });
    if (updated !== output) {
      migrations.push(fragment.id);
      output = updated;
    }
  }
  return { output, migrations };
}

function scanWorkflowConflicts(text, documentPath, policy){
  const conflicts = [];
  const seen = new Set();
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const candidates = lines.map((line, index) => ({ text: line, line: index + 1 }));
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) continue;
    if (/^\s*(?:[-+*]|\d+\.)\s+/.test(line)) {
      let end = index + 1;
      while (end < lines.length && /^\s{2,}\S/.test(lines[end]) && !/^\s*(?:[-+*]|\d+\.)\s+/.test(lines[end])) end += 1;
      if (end > index + 1) candidates.push({ text: lines.slice(index, end).join(" "), line: index + 1 });
      continue;
    }
    if (/^\s*(?:#|\||```|~~~)/.test(line)) continue;
    let end = index + 1;
    while (end < lines.length && lines[end].trim() && !/^\s*(?:#|\||```|~~~|[-+*]|\d+\.)\s*/.test(lines[end])) end += 1;
    if (end > index + 1) candidates.push({ text: lines.slice(index, end).join(" "), line: index + 1 });
  }
  for (const rule of policy.conflict_rules) {
    if (!rule.paths?.includes(documentPath)) continue;
    let pattern;
    try {
      pattern = new RegExp(rule.pattern, String(rule.flags || "").replaceAll("g", ""));
    } catch (error) {
      throw new Error(`invalid workflow conflict rule ${rule.id}: ${error.message}`);
    }
    for (const candidate of candidates) {
      if (!pattern.test(candidate.text)) continue;
      const key = `${rule.id}:${candidate.line}`;
      if (seen.has(key)) continue;
      seen.add(key);
      conflicts.push({
        file: documentPath,
        line: candidate.line,
        ruleId: rule.id,
        message: rule.message,
        excerpt: candidate.text.trim().slice(0, 240),
      });
    }
  }
  return conflicts;
}

function migrateDocumentText(text, documentPath, policy){
  const migrated = applyKnownOfficialFragments(text, documentPath, policy);
  return {
    output: migrated.output,
    migrations: migrated.migrations,
    conflicts: scanWorkflowConflicts(migrated.output, documentPath, policy),
  };
}

function replaceManagedBlock(text, region, block){
  let before = text.slice(0, region.start);
  let after = text.slice(region.endExclusive);
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  if (before && !/(?:\r?\n)$/.test(before)) before += eol;
  if (after && !/^(?:\r?\n)/.test(after)) after = `${eol}${after}`;
  return `${before}${block}${after}`;
}

function splitEngineeringDocument(text){
  const frontmatter = text.match(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/);
  const bodyStart = frontmatter ? frontmatter[0].length : 0;
  return { frontmatter: text.slice(0, bodyStart), body: text.slice(bodyStart) };
}

function engineeringBodyHash(body){
  return crypto.createHash("sha256").update(body.replace(/\r\n/g, "\n")).digest("hex");
}

function insertManagedWorkflow(text, block){
  const { frontmatter } = splitEngineeringDocument(text);
  const bodyStart = frontmatter.length;
  const body = text.slice(bodyStart);
  const heading = /^# Engineering Workflow[^\r\n]*(?:\r?\n|$)/m.exec(body);
  const insertion = heading ? bodyStart + heading.index + heading[0].length : bodyStart;
  const before = text.slice(0, insertion);
  const after = text.slice(insertion);
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  const left = before && !/(?:\r?\n)$/.test(before) ? `${before}${eol}` : before;
  const right = after && !/^(?:\r?\n)/.test(after) ? `${eol}${after}` : after;
  return `${left}${block}${right}`;
}

function lineCount(text){
  return text ? text.replace(/\r\n/g, "\n").split("\n").length - 1 : 0;
}

function offsetConflicts(conflicts, offset){
  return conflicts.map(conflict => ({ ...conflict, line: conflict.line + offset }));
}

function planEngineeringSync(project, assetSkill, policy = loadWorkflowMigrationPolicy(assetSkill)){
  const root = path.resolve(project);
  const engineering = path.join(root, "docs", "ENGINEERING.md");
  const templatePath = path.join(assetSkill, "data", "templates", "ENGINEERING.md");
  const renderedTemplate = renderEngineeringTemplate(fs.readFileSync(templatePath, "utf8"), root);
  const templateRegion = inspectManagedWorkflow(renderedTemplate);
  if (templateRegion.state !== "present") {
    return { state: "invalid", detail: `packaged ENGINEERING template: ${templateRegion.detail || "managed workflow markers are missing"}` };
  }
  if (templateRegion.version !== policy.managed_versions.engineering) {
    return { state: "invalid", detail: `packaged ENGINEERING version ${templateRegion.version} does not match migration policy ${policy.managed_versions.engineering}` };
  }
  if (!exists(engineering)) {
    return { state: "missing", version: templateRegion.version, output: renderedTemplate, engineering, migrations: [], conflicts: [] };
  }

  const current = fs.readFileSync(engineering, "utf8");
  const currentRegion = inspectManagedWorkflow(current);
  if (currentRegion.state === "invalid") return { ...currentRegion, engineering };
  if (currentRegion.state === "absent") {
    const currentParts = splitEngineeringDocument(current);
    const templateParts = splitEngineeringDocument(renderedTemplate);
    const legacyHash = engineeringBodyHash(currentParts.body);
    if (policy.known_official_engineering_body_sha256.includes(legacyHash)) {
      return {
        state: "legacy-official",
        version: templateRegion.version,
        previousBodyHash: legacyHash,
        output: `${currentParts.frontmatter}${templateParts.body}`,
        engineering,
        migrations: [`engineering-body-sha256:${legacyHash}`],
        conflicts: [],
      };
    }
    const migrated = migrateDocumentText(currentParts.body, "docs/ENGINEERING.md", policy);
    const conflicts = offsetConflicts(migrated.conflicts, lineCount(currentParts.frontmatter));
    if (conflicts.length) {
      return {
        state: "conflict",
        version: templateRegion.version,
        engineering,
        migrations: migrated.migrations,
        conflicts,
        detail: "unknown workflow directives conflict with the managed fast-gate policy",
      };
    }
    const sectionMigration = migrated.migrations.some(item => item.startsWith("engineering-section-"));
    const archive = sectionMigration ? engineeringArchivePlan(root, current, templateRegion.version) : {};
    return {
      state: "legacy-custom",
      version: templateRegion.version,
      preservedCustom: true,
      output: insertManagedWorkflow(`${currentParts.frontmatter}${migrated.output}`, templateRegion.block),
      engineering,
      migrations: migrated.migrations,
      conflicts: [],
      ...archive,
    };
  }
  const beforeParts = splitEngineeringDocument(current.slice(0, currentRegion.start));
  const migratedBefore = migrateDocumentText(beforeParts.body, "docs/ENGINEERING.md", policy);
  const migratedAfter = migrateDocumentText(current.slice(currentRegion.endExclusive), "docs/ENGINEERING.md", policy);
  const conflicts = [
    ...offsetConflicts(migratedBefore.conflicts, lineCount(beforeParts.frontmatter)),
    ...offsetConflicts(migratedAfter.conflicts, lineCount(current.slice(0, currentRegion.endExclusive))),
  ];
  const migrations = [...migratedBefore.migrations, ...migratedAfter.migrations];
  if (conflicts.length) {
    return {
      state: "conflict",
      version: templateRegion.version,
      previousVersion: currentRegion.version,
      engineering,
      migrations,
      conflicts,
      detail: "unknown workflow directives conflict with the managed fast-gate policy",
    };
  }
  const migratedCurrent = `${beforeParts.frontmatter}${migratedBefore.output}${currentRegion.block}${migratedAfter.output}`;
  const migratedRegion = inspectManagedWorkflow(migratedCurrent);
  const output = replaceManagedBlock(migratedCurrent, migratedRegion, templateRegion.block);
  if (current === output) return { state: "current", version: templateRegion.version, output, engineering, migrations: [], conflicts: [] };
  const sectionMigration = migrations.some(item => item.startsWith("engineering-section-"));
  const archive = sectionMigration ? engineeringArchivePlan(root, current, templateRegion.version) : {};
  return {
    state: "stale",
    version: templateRegion.version,
    previousVersion: currentRegion.version,
    output,
    engineering,
    migrations,
    conflicts: [],
    ...archive,
  };
}

function engineeringArchivePlan(root, current, version){
  const archiveHeader = [
    `# Archived ENGINEERING.md before auto-coding-skill ${version} docs convergence`,
    "",
    "This file is historical and non-authoritative. Known duplicate workflow sections",
    "were removed from docs/ENGINEERING.md. Move any still-current project facts into",
    "docs/project/ and configuration into docs/project/auto-coding-skill.yaml.",
    "",
    "---",
    "",
  ].join("\n");
  const archiveOutput = `${archiveHeader}${current}`;
  const archiveDir = path.join(root, "docs", "archive", "workflow");
  const selected = selectProjectArchiveTarget(
    root,
    path.join(archiveDir, `ENGINEERING.pre-${version}.md`),
    archiveOutput,
    { legacyDigestPayload: current },
  );
  return {
    archiveDocument: selected.path,
    archiveOutput,
    archiveRequired: selected.archiveRequired,
  };
}

function planAgentsDocumentSync(project, assetSkill, policy = loadWorkflowMigrationPolicy(assetSkill)){
  const root = path.resolve(project);
  const agentsDocument = path.join(root, "AGENTS.md");
  validateProjectFileTarget(root, agentsDocument, "root AGENTS.md");
  const templatePath = path.join(assetSkill, "data", "templates", "bridges", "AGENTS.md");
  const template = fs.readFileSync(templatePath, "utf8");
  const templateRegion = inspectManagedAgentsDocument(template);
  if (templateRegion.state !== "present" || templateRegion.version !== policy.managed_versions.agents) {
    return { state: "invalid", detail: "packaged AGENTS template markers/version do not match the migration policy", agentsDocument };
  }
  if (!exists(agentsDocument)) {
    return { state: "missing", version: templateRegion.version, output: template, agentsDocument, migrations: [], conflicts: [] };
  }
  const current = fs.readFileSync(agentsDocument, "utf8");
  if (current === template) {
    return { state: "current", version: templateRegion.version, output: template, agentsDocument, migrations: [], conflicts: [] };
  }
  const archiveHeader = [
    `# Archived AGENTS.md before auto-coding-skill ${templateRegion.version}`,
    "",
    "This file is historical and non-authoritative. The root AGENTS.md is fully managed.",
    "Move any still-current project facts into docs/project/",
    "without copying workflow rules back into the root AGENTS.md.",
    "",
    "---",
    "",
  ].join("\n");
  const archiveOutput = `${archiveHeader}${current}`;
  const archiveDir = path.join(root, "docs", "archive", "workflow");
  const selected = selectProjectArchiveTarget(
    root,
    path.join(archiveDir, `AGENTS.pre-${templateRegion.version}.md`),
    archiveOutput,
    { legacyDigestPayload: current },
  );
  const currentRegion = inspectManagedAgentsDocument(current);
  return {
    state: currentRegion.state === "present" ? "stale" : "legacy-custom",
    version: templateRegion.version,
    ...(currentRegion.state === "present" ? { previousVersion: currentRegion.version } : {}),
    output: template,
    agentsDocument,
    archiveDocument: selected.path,
    archiveOutput,
    archiveRequired: selected.archiveRequired,
    migrations: ["agents-whole-file-replacement"],
    conflicts: [],
  };
}

function planControlledDocuments(project, assetSkill){
  const policy = loadWorkflowMigrationPolicy(assetSkill);
  return {
    engineering: planEngineeringSync(project, assetSkill, policy),
    agents: planAgentsDocumentSync(project, assetSkill, policy),
  };
}

function publicEngineeringPlan(plan){
  const publicConflicts = (plan.conflicts || []).map(conflict => ({
    ...(conflict.file ? { file: conflict.file } : {}),
    ...(Number.isInteger(conflict.line) ? { line: conflict.line } : {}),
    ...(conflict.ruleId ? { ruleId: conflict.ruleId } : {}),
    ...(conflict.message ? { message: conflict.message } : {}),
  }));
  return {
    state: plan.state,
    version: plan.version || "unknown",
    ...(plan.previousVersion ? { previousVersion: plan.previousVersion } : {}),
    ...(plan.previousBodyHash ? { previousBodyHash: plan.previousBodyHash } : {}),
    ...(plan.preservedCustom ? { preservedCustom: true } : {}),
    ...(plan.archiveDocument ? { archive: plan.archiveDocument } : {}),
    ...(plan.migrations?.length ? { migrations: plan.migrations } : {}),
    ...(publicConflicts.length ? { conflicts: publicConflicts } : {}),
    ...(plan.detail ? { detail: plan.detail } : {}),
  };
}

function registeredTasks(project){
  const root = path.resolve(project);
  let commonDir;
  try {
    const raw = execFileSync("git", ["-C", root, "rev-parse", "--git-common-dir"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    commonDir = path.resolve(root, raw);
  } catch {
    return [];
  }
  const tasksDir = path.join(commonDir, "auto-coding-skill", "tasks");
  if (!exists(tasksDir)) return [];
  const registered = [];
  for (const entry of fs.readdirSync(tasksDir, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
    const manifestPath = path.join(tasksDir, entry.name);
    let manifest;
    try {
      manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    } catch {
      registered.push({ project: root, manifest: entry.name, schema: "invalid" });
      continue;
    }
    const schema = Number(manifest?.schema ?? 0);
    registered.push({ project: root, manifest: entry.name, schema: Number.isFinite(schema) ? schema : "invalid" });
  }
  return registered;
}

function assertNoRegisteredTasks(projects){
  const active = projects.flatMap(project => registeredTasks(project));
  if (!active.length) return;
  const locations = active.map(item => `${item.project}:${item.manifest}(schema=${item.schema})`).join(", ");
  die(
    "refusing the entire sync batch because registered auto-coding tasks are still active: "
    + `${locations}\nFinish, integrate, or clean these tasks with the currently installed runtime before upgrading. `
    + "sync will not change the lifecycle semantics of an in-flight task.",
  );
}

function readPackageVersion(){
  const here = path.dirname(fileURLToPath(import.meta.url));
  const pkgPath = path.resolve(here, "..", "..", "package.json");
  try {
    return JSON.parse(fs.readFileSync(pkgPath, "utf8")).version ?? "unknown";
  } catch {
    return "unknown";
  }
}

function feedbackLifecycleStatus(root, assetSkill){
  if (!exists(path.join(root, "docs", "skill-feedback", "reports"))) {
    return {
      available: true,
      skillVersion: "",
      reportCount: 0,
      activeReportCount: 0,
      closedReportCount: 0,
      actionRequiredCount: 0,
      lifecycleCounts: {},
      actionRequired: [],
    };
  }
  const result = spawnSync(
    runtimePython(),
    [path.join(assetSkill, "scripts", "ap.py"), "feedback-collect", "--project", root, "--json"],
    { encoding: "utf8", stdio: "pipe", maxBuffer: 2 * 1024 * 1024 },
  );
  if (result.error || result.signal || result.status !== 0) {
    return {
      available: false,
      advisory: "run autocoding feedback --projects . --json to inspect Skill feedback metadata",
    };
  }
  try {
    const parsed = JSON.parse(result.stdout);
    return {
      available: true,
      skillVersion: parsed.projects?.[0]?.skill_version || "",
      reportCount: parsed.report_count || 0,
      activeReportCount: parsed.active_report_count || 0,
      closedReportCount: parsed.closed_report_count || 0,
      actionRequiredCount: parsed.action_required_count || 0,
      lifecycleCounts: parsed.lifecycle_counts || {},
      actionRequired: parsed.action_required || [],
    };
  } catch {
    return {
      available: false,
      advisory: "run autocoding feedback --projects . --json to inspect Skill feedback metadata",
    };
  }
}

function projectStatus(project, assetSkill, assetAgents, assetManifest, releaseManifest){
  const root = path.resolve(project);
  validateInstallTransactionInputs(root, assetSkill, assetManifest);
  validateProjectManagedTargets(root, assetAgents);
  const transactionPending = installTransactionPending(root);
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const engineering = path.join(root, "docs", "ENGINEERING.md");
  const engineeringMissing = !exists(engineering);
  const controlledPlans = planControlledDocuments(root, assetSkill);
  const engineeringPlan = controlledPlans.engineering;
  const agentsDocumentPlan = controlledPlans.agents;
  const managedWorkflow = publicEngineeringPlan(engineeringPlan);
  const managedAgentsDocument = publicEngineeringPlan(agentsDocumentPlan);
  const requiredConfigPaths = [
    { label: "workflow.skill_version", path: ["workflow", "skill_version"] },
    { label: "workflow.mode", path: ["workflow", "mode"] },
    { label: "workflow.profile", path: ["workflow", "profile"] },
    { label: "workflow.completion", path: ["workflow", "completion"] },
    { label: "concurrency.isolation", path: ["concurrency", "isolation"] },
    { label: "concurrency.base_ref", path: ["concurrency", "base_ref"] },
    { label: "concurrency.target_branch", path: ["concurrency", "target_branch"] },
    { label: "concurrency.branch_prefix", path: ["concurrency", "branch_prefix"] },
    { label: "concurrency.worktree_root", path: ["concurrency", "worktree_root"] },
    { label: "concurrency.cleanup_merged", path: ["concurrency", "cleanup_merged"] },
    { label: "concurrency.delete_remote_branch", path: ["concurrency", "delete_remote_branch"] },
    { label: "concurrency.disposable_ignored", path: ["concurrency", "disposable_ignored"] },
    { label: "validation.on_unmapped", path: ["validation", "on_unmapped"] },
    { label: "validation.max_command_seconds", path: ["validation", "max_command_seconds"] },
    { label: "validation.max_total_seconds", path: ["validation", "max_total_seconds"] },
    { label: "validation.routes", path: ["validation", "routes"], sequence: true },
    { label: "risk.rules", path: ["risk", "rules"] },
    { label: "docs.framework", path: ["docs", "framework"], filled: true },
    { label: "project.name", path: ["project", "name"], filled: true },
    { label: "access.project.frontend.url", path: ["access", "project", "frontend", "url"], filled: true },
    { label: "access.project.frontend.username", path: ["access", "project", "frontend", "username"], filled: true },
    { label: "access.project.frontend.password", path: ["access", "project", "frontend", "password"], filled: true },
    { label: "access.project.backend.url", path: ["access", "project", "backend", "url"], filled: true },
    { label: "access.project.backend.username", path: ["access", "project", "backend", "username"], filled: true },
    { label: "access.project.backend.password", path: ["access", "project", "backend", "password"], filled: true },
    { label: "access.jenkins.frontend.url", path: ["access", "jenkins", "frontend", "url"], filled: true },
    { label: "access.jenkins.frontend.username", path: ["access", "jenkins", "frontend", "username"], filled: true },
    { label: "access.jenkins.frontend.password", path: ["access", "jenkins", "frontend", "password"], filled: true },
    { label: "access.jenkins.backend.url", path: ["access", "jenkins", "backend", "url"], filled: true },
    { label: "access.jenkins.backend.username", path: ["access", "jenkins", "backend", "username"], filled: true },
    { label: "access.jenkins.backend.password", path: ["access", "jenkins", "backend", "password"], filled: true },
    { label: "access.gitlab.url", path: ["access", "gitlab", "url"], filled: true },
    { label: "access.gitlab.username", path: ["access", "gitlab", "username"], filled: true },
    { label: "access.gitlab.password", path: ["access", "gitlab", "password"], filled: true },
    { label: "access.nexus.frontend.url", path: ["access", "nexus", "frontend", "url"], filled: true },
    { label: "access.nexus.frontend.username", path: ["access", "nexus", "frontend", "username"], filled: true },
    { label: "access.nexus.frontend.password", path: ["access", "nexus", "frontend", "password"], filled: true },
  ];
  let missingConfigPaths = requiredConfigPaths.map(item => item.label);
  let unfilledConfigTokens = [];
  let invalidConfigTokens = [];
  const effectiveConfig = readEffectiveConfigStatus(root, assetSkill);
  if (!engineeringMissing && effectiveConfig.ok) {
    const states = requiredConfigPaths.map(item => ({
      item,
      state: effectiveConfig.fields[item.label] || { present: false, configured: false, item_count: -1 },
    }));
    missingConfigPaths = states.filter(({ state }) => !state.present).map(({ item }) => item.label);
    unfilledConfigTokens = states
      .filter(({ item, state }) => state.present && (
        (item.filled === true && !state.configured)
        || (item.sequence === true && state.item_count <= 0)
      ))
      .map(({ item }) => item.label);
    const isolationState = effectiveConfig.fields["concurrency.isolation"] || {};
    if (isolationState.present && !["adaptive", "worktree"].includes(String(isolationState.value || "").toLowerCase())) {
      invalidConfigTokens.push("concurrency.isolation (must be adaptive or worktree)");
    }
    for (const label of [
      "validation.max_command_seconds",
      "validation.max_total_seconds",
    ]) {
      const state = effectiveConfig.fields[label] || {};
      if (!state.present) continue;
      const value = Number(state.value);
      if (!Number.isFinite(value) || value <= 0) {
        invalidConfigTokens.push(`${label} (must be > 0)`);
      }
    }
    const commandState = effectiveConfig.fields["validation.max_command_seconds"] || {};
    const totalState = effectiveConfig.fields["validation.max_total_seconds"] || {};
    const commandBudget = Number(commandState.value);
    const totalBudget = Number(totalState.value);
    if (commandState.present && totalState.present && Number.isFinite(commandBudget) && Number.isFinite(totalBudget) && commandBudget > totalBudget) {
      invalidConfigTokens.push("validation.max_command_seconds (cannot exceed max_total_seconds)");
    }
    invalidConfigTokens.push(...(effectiveConfig.policy_issues || []));
    invalidConfigTokens.push(...(effectiveConfig.contract_issues || []));
  } else if (!engineeringMissing) {
    invalidConfigTokens.push(`effective configuration (${effectiveConfig.error || "invalid"})`);
  }
  invalidConfigTokens = [...new Set(invalidConfigTokens)];
  const missingConfigTokens = [...missingConfigPaths, ...unfilledConfigTokens, ...invalidConfigTokens];
  const scriptDiffs = [];
  const launcherSrc = path.join(assetSkill, "data", "templates", "tools", "ap.py");
  const launcherDst = path.join(toolDir, "ap.py");
  if (!exists(launcherDst)) scriptDiffs.push({ path: "docs/tools/autopipeline/ap.py", status: "missing" });
  else if (!fs.readFileSync(launcherSrc).equals(fs.readFileSync(launcherDst))) {
    scriptDiffs.push({ path: "docs/tools/autopipeline/ap.py", status: "stale" });
  }
  const missingDocs = [];
  for (const rel of CORE_DOCS) {
    if (!exists(path.join(root, "docs", rel))) missingDocs.push(path.join("docs", rel));
  }
  let docsDiffs = [];
  const convergenceCheck = spawnSync(
    runtimePython(),
    [path.join(assetSkill, "scripts", "ap.py"), "--repo", root, "project-converge", "--json"],
    { encoding: "utf8", stdio: "pipe" },
  );
  if (convergenceCheck.status === 0) {
    try {
      docsDiffs = (JSON.parse(convergenceCheck.stdout).actions || []).filter(item =>
        item.path === "docs/ENGINEERING.md" || item.path.startsWith("docs/"),
      );
    } catch {
      docsDiffs = [{ action: "invalid", path: "docs", detail: "convergence check returned invalid JSON" }];
    }
  } else {
    docsDiffs = [{
      action: "invalid",
      path: "docs",
      detail: String(convergenceCheck.stderr || convergenceCheck.stdout || "convergence check failed").trim(),
    }];
  }
  const skillDiffs = exists(skillDir) ? compareDirs(assetSkill, skillDir, { includeExtra: true }) : [{ path: ".agents/skills/auto-coding-skill", status: "missing" }];
  const agentStatus = exists(agentsDir)
    ? compareManagedAgents(assetAgents, agentsDir)
    : { diffs: [{ path: ".agents/agents", status: "missing" }], bindings: [] };
  const agentDiffs = agentStatus.diffs;
  const installedManifest = installManifestTarget(root);
  const installManifestDiffs = [];
  if (!exists(installedManifest)) installManifestDiffs.push({ path: ".agents/managed-install.json", status: "missing" });
  else if (!fs.readFileSync(assetManifest).equals(fs.readFileSync(installedManifest))) {
    installManifestDiffs.push({ path: ".agents/managed-install.json", status: "stale" });
  }
  const installIntegrity = installIntegrityStatus(root, "project", releaseManifest.skill_version);
  const feedback = feedbackLifecycleStatus(root, assetSkill);
  const ok = !transactionPending
    && skillDiffs.length === 0
    && agentDiffs.length === 0
    && scriptDiffs.length === 0
    && installManifestDiffs.length === 0
    && installIntegrity.ok
    && missingDocs.length === 0
    && docsDiffs.length === 0
    && missingConfigTokens.length === 0
    && managedWorkflow.state === "current"
    && managedAgentsDocument.state === "current";
  let next = "";
  if (transactionPending) {
    next = "run autocoding init or a single-project autocoding sync to recover the interrupted install transaction";
  } else if (!exists(skillDir) || !exists(agentsDir)) {
    next = "run autocoding init";
  } else if (skillDiffs.length || agentDiffs.length || installManifestDiffs.length || !installIntegrity.ok) {
    next = "run autocoding init";
  } else if (engineeringMissing || managedWorkflow.state !== "current" || managedAgentsDocument.state !== "current" || scriptDiffs.length || missingDocs.length || docsDiffs.length) {
    next = "run autocoding init";
  } else if (missingConfigPaths.length) {
    next = "run autocoding init, fill every required value in docs/project/auto-coding-skill.yaml, then run doctor";
  } else if (invalidConfigTokens.length) {
    next = "run autocoding init, then run doctor";
  } else if (unfilledConfigTokens.length) {
    next = "fill every required value in docs/project/auto-coding-skill.yaml, then run project-local ap.py doctor";
  }
  return {
    project: root,
    ok,
    transactionPending,
    skillDiffs,
    agentDiffs,
    agentBindings: agentStatus.bindings,
    scriptDiffs,
    installManifestDiffs,
    installIntegrity,
    docsDiffs,
    missingDocs,
    missingConfigTokens,
    missingConfigPaths,
    unfilledConfigTokens,
    invalidConfigTokens,
    managedWorkflow,
    managedAgentsDocument,
    feedback,
    next,
  };
}

function printProjectStatus(result){
  console.log(`[autocoding] project=${result.project}`);
  console.log(`[autocoding] ok=${result.ok}`);
  if (result.transactionPending) console.log("[autocoding] install transaction: recovery required");
  for (const [label, items] of [["skill", result.skillDiffs], ["agents", result.agentDiffs], ["scripts", result.scriptDiffs]]) {
    for (const item of items) {
      const detail = item.detail ? ` - ${item.detail}` : "";
      console.log(`[autocoding] ${label} ${item.status}: ${item.path}${detail}`);
    }
  }
  for (const item of result.installManifestDiffs || []) {
    console.log(`[autocoding] manifest ${item.status}: ${item.path}`);
  }
  for (const issue of result.installIntegrity?.errors || []) {
    console.log(`[autocoding] install integrity: ${issue}`);
  }
  for (const item of result.missingDocs) console.log(`[autocoding] doc missing: ${item}`);
  for (const item of result.docsDiffs || []) {
    const detail = item.detail ? ` - ${item.detail}` : "";
    console.log(`[autocoding] docs ${item.action}: ${item.path}${detail}`);
  }
  for (const item of result.missingConfigTokens) console.log(`[autocoding] config missing path: ${item}`);
  if (result.managedWorkflow?.state !== "current") {
    const detail = result.managedWorkflow?.detail ? ` - ${result.managedWorkflow.detail}` : "";
    console.log(`[autocoding] engineering managed-workflow: ${result.managedWorkflow?.state || "unknown"} target=${result.managedWorkflow?.version || "unknown"}${detail}`);
  }
  if (result.managedAgentsDocument?.state !== "current") {
    const detail = result.managedAgentsDocument?.detail ? ` - ${result.managedAgentsDocument.detail}` : "";
    console.log(`[autocoding] agents managed-document: ${result.managedAgentsDocument?.state || "unknown"} target=${result.managedAgentsDocument?.version || "unknown"}${detail}`);
  }
  for (const item of result.agentBindings || []) console.log(`[autocoding] agent model: ${item.agent} -> ${item.model}`);
  if (result.feedback?.available && result.feedback.actionRequiredCount) {
    console.log(`[autocoding] feedback advisory: ${result.feedback.actionRequiredCount} report(s) need maintenance`);
    for (const item of result.feedback.actionRequired || []) {
      console.log(`[autocoding] feedback action: ${item.report_id} ${item.lifecycle} -> ${item.recommended_action}`);
    }
  } else if (result.feedback && !result.feedback.available) {
    console.log(`[autocoding] feedback advisory: ${result.feedback.advisory}`);
  }
  if (result.next) console.log(`[autocoding] next: ${result.next}`);
}

function engineeringPlanDetail(plan){
  if (plan.state === "legacy-custom") return `managed workflow preserved-custom -> ${plan.version}`;
  if (plan.state === "legacy-official") return `managed workflow official-legacy -> ${plan.version}`;
  return `managed workflow ${plan.state} -> ${plan.version}`;
}

function syncProject(project, assetSkill, assetAgents, assetManifest, releaseManifest, dryRun, resetAgentModels = false, components = "all", controlledPlans = null){
  const root = path.resolve(project);
  const actions = [];
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const plans = controlledPlans || planControlledDocuments(root, assetSkill);
  let prepared = null;
  let transaction = null;
  if (!dryRun) safeProjectMutationRequired = true;
  if (dryRun) {
    const engineeringConvergence = plans.engineeringConvergence || runEngineeringConvergence(root, assetSkill, false);
    for (const item of engineeringConvergence.actions || []) {
      actions.push({
        ...item,
        action: String(item.action).startsWith("would-") ? item.action : `would-${item.action}`,
      });
    }
  } else {
    // Write only the project-owned overlay first. Keep the legacy ENGINEERING
    // bytes in place until the effective-config-aware runtime has been copied.
    prepared = runProjectConfigPrepare(root, assetSkill, true);
    actions.push(...prepared.actions);
    injectInstallFault("after-prepare");
    transaction = beginInstallTransaction(root, assetSkill, assetManifest, prepared);
    injectInstallFault("after-stage-copy");
  }
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, skillDir) });
  actions.push({ action: dryRun ? "would-sync" : "sync", path: ".agents/managed-install.json" });
  if (!dryRun) {
    switchInstallTransaction(root, transaction);
    injectInstallFault("after-runtime-switch");
    if (prepared.finalize_required) {
      const finalized = runProjectConfigFinalize(
        root,
        skillDir,
        prepared,
        true,
        transaction.token,
        transaction,
      );
      actions.push(...finalized.actions);
    }
    injectInstallFault("after-config-finalize");
    // Complete exact managed-document convergence while the rollback backups
    // are still present, before unrelated managed files are touched.
    const convergence = runEngineeringConvergence(
      root,
      skillDir,
      true,
      transaction.token,
      transaction,
    );
    for (const item of convergence.actions || []) {
      if (actions.some(action => action.path === item.path && action.action === item.action)) continue;
      actions.push(item);
    }
  }

  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const agentsDocumentPlan = plans.agents;
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, agentsDir) });
  actions.push({ action: dryRun ? "would-sync" : "sync", path: "docs/tools/autopipeline/ap.py" });
  if (!dryRun) {
    syncManagedAgents(assetAgents, agentsDir, { resetModel: resetAgentModels, projectRoot: root });
    atomicWriteProjectFile(
      root,
      path.join(toolDir, "ap.py"),
      fs.readFileSync(path.join(assetSkill, "data", "templates", "tools", "ap.py")),
    );
    for (const copied of copyMissingDocs(assetSkill, root)) actions.push({ action: "create", path: copied });
    if (agentsDocumentPlan.state !== "current") {
      if (agentsDocumentPlan.archiveRequired) {
        atomicCreateProjectFile(root, agentsDocumentPlan.archiveDocument, agentsDocumentPlan.archiveOutput);
        actions.push({
          action: "archive",
          path: path.relative(root, agentsDocumentPlan.archiveDocument),
          detail: "previous root AGENTS.md; historical and non-authoritative",
        });
      }
      atomicWriteProjectFile(root, agentsDocumentPlan.agentsDocument, agentsDocumentPlan.output);
      actions.push({
        action: agentsDocumentPlan.state === "missing" ? "create" : "update",
        path: "AGENTS.md",
        detail: `managed agents ${agentsDocumentPlan.state} -> ${agentsDocumentPlan.version}`,
      });
    }
    applyManifestExecutableBits(root, releaseManifest, "project");
    const integrity = requireInstallIntegrity(root, "project", releaseManifest.skill_version);
    actions.push({ action: "verify", path: ".agents/managed-install.json", detail: `${integrity.checked} managed files` });
    completeInstallTransaction(root, transaction);
  } else {
    for (const rel of CORE_DOCS) {
      if (!exists(path.join(root, "docs", rel))) actions.push({ action: "would-create", path: path.join("docs", rel) });
    }
    if (agentsDocumentPlan.state !== "current") {
      if (agentsDocumentPlan.archiveRequired) {
        actions.push({
          action: "would-archive",
          path: path.relative(root, agentsDocumentPlan.archiveDocument),
          detail: "previous root AGENTS.md; historical and non-authoritative",
        });
      }
      actions.push({
        action: agentsDocumentPlan.state === "missing" ? "would-create" : "would-update",
        path: "AGENTS.md",
        detail: `managed agents ${agentsDocumentPlan.state} -> ${agentsDocumentPlan.version}`,
      });
    }
  }
  const reportedPlans = dryRun ? plans : planControlledDocuments(root, assetSkill);
  return {
    project: root,
    dryRun,
    components,
    managedWorkflow: publicEngineeringPlan(reportedPlans.engineering),
    managedAgentsDocument: publicEngineeringPlan(reportedPlans.agents),
    feedback: feedbackLifecycleStatus(root, assetSkill),
    actions,
  };
}

function convergeProjectInstall(project, assetSkill, assetAgents, assetManifest, releaseManifest, resetAgentModels){
  const root = path.resolve(project);
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const actions = [];
  safeProjectMutationRequired = true;

  recoverInstallTransaction(root, true);
  validateInstallTransactionInputs(root, assetSkill, assetManifest);
  validateProjectManagedTargets(root, assetAgents);
  // Validate the authoritative template and legacy input before the first write.
  runEngineeringConvergence(root, assetSkill, false);
  // Materialize only the project-owned overlay while the previous installed
  // template is still available as the semantic diff base. Replacing the
  // managed document is deferred until the new runtime is in place.
  const prepared = runProjectConfigPrepare(root, assetSkill, true);
  actions.push(...prepared.actions);
  injectInstallFault("after-prepare");
  const transaction = beginInstallTransaction(root, assetSkill, assetManifest, prepared);
  injectInstallFault("after-stage-copy");

  switchInstallTransaction(root, transaction);
  actions.push({ action: "replace", path: path.relative(root, skillDir) });
  actions.push({ action: "replace", path: ".agents/managed-install.json" });
  injectInstallFault("after-runtime-switch");

  if (prepared.finalize_required) {
    const finalized = runProjectConfigFinalize(
      root,
      skillDir,
      prepared,
      true,
      transaction.token,
      transaction,
    );
    actions.push(...finalized.actions);
  }
  injectInstallFault("after-config-finalize");
  const engineering = runEngineeringConvergence(
    root,
    skillDir,
    true,
    transaction.token,
    transaction,
  );
  for (const item of engineering.actions || []) {
    if (actions.some(action => action.path === item.path && action.action === item.action)) continue;
    actions.push(item);
  }

  syncManagedAgents(assetAgents, agentsDir, { resetModel: resetAgentModels, projectRoot: root });
  actions.push({ action: "sync", path: path.relative(root, agentsDir) });

  atomicWriteProjectFile(
    root,
    path.join(toolDir, "ap.py"),
    fs.readFileSync(path.join(assetSkill, "data", "templates", "tools", "ap.py")),
  );
  actions.push({ action: "replace", path: "docs/tools/autopipeline/ap.py" });

  const agentsDocument = path.join(root, "AGENTS.md");
  const canonicalAgents = fs.readFileSync(
    path.join(assetSkill, "data", "templates", "bridges", "AGENTS.md"),
    "utf8",
  );
  const currentAgents = exists(agentsDocument) ? fs.readFileSync(agentsDocument, "utf8") : "";
  if (currentAgents !== canonicalAgents) {
    if (currentAgents) {
      const preferredArchive = path.join(
        root,
        ".agents",
        "archive",
        "auto-coding-skill",
        readPackageVersion(),
        "AGENTS.md",
      );
      const selected = selectProjectArchiveTarget(root, preferredArchive, currentAgents, {
        legacyDigestPayload: currentAgents,
      });
      if (selected.archiveRequired) {
        atomicCreateProjectFile(root, selected.path, currentAgents);
        actions.push({
          action: "archive",
          path: path.relative(root, selected.path),
          detail: "historical and non-authoritative",
        });
      }
    }
    atomicWriteProjectFile(root, agentsDocument, canonicalAgents);
    actions.push({ action: "replace", path: "AGENTS.md" });
  }

  applyManifestExecutableBits(root, releaseManifest, "project");
  const integrity = requireInstallIntegrity(root, "project", releaseManifest.skill_version);
  actions.push({ action: "verify", path: ".agents/managed-install.json", detail: `${integrity.checked} managed files` });
  completeInstallTransaction(root, transaction);
  return { project: root, feedback: feedbackLifecycleStatus(root, assetSkill), actions };
}

function projectRoot(){ return process.cwd(); }

function resolveInstallDirs(mode, destOverride){
  if (mode !== "project" && mode !== "global") die(`--mode must be 'project' or 'global'`);

  if (destOverride) {
    const dest = path.resolve(destOverride);
    const parent = path.dirname(dest);
    const grandparent = path.dirname(parent);
    if (path.basename(dest) === "auto-coding-skill" && path.basename(parent) === "skills" && path.basename(grandparent) === ".agents") {
      return {
        skillDir: dest,
        agentsDir: path.join(grandparent, "agents"),
        projectDir: path.dirname(grandparent),
      };
    }
    if (path.basename(dest) === "skills" && path.basename(parent) === ".agents") {
      return {
        skillDir: path.join(dest, "auto-coding-skill"),
        agentsDir: path.join(parent, "agents"),
        projectDir: path.dirname(parent),
      };
    }
    if (path.basename(dest) === "agents" && path.basename(parent) === ".agents") {
      return {
        skillDir: path.join(parent, "skills", "auto-coding-skill"),
        agentsDir: dest,
        projectDir: path.dirname(parent),
      };
    }
    if (path.basename(dest) === ".agents") {
      return {
        skillDir: path.join(dest, "skills", "auto-coding-skill"),
        agentsDir: path.join(dest, "agents"),
        projectDir: path.dirname(dest),
      };
    }
    return {
      skillDir: path.join(dest, ".agents", "skills", "auto-coding-skill"),
      agentsDir: path.join(dest, ".agents", "agents"),
      projectDir: dest,
    };
  }

  const root = mode === "project" ? projectRoot() : os.homedir();
  return {
    skillDir: path.join(root, ".agents", "skills", "auto-coding-skill"),
    agentsDir: path.join(root, ".agents", "agents"),
    projectDir: root,
  };
}

function main(){
  const args = parseArgs(process.argv);

  if (args.cmd === "help" || !args.cmd) {
    console.log(`
autocoding - install auto-coding-skill into generic .agents paths

Usage:
  autocoding init [--mode project|global] [--dest <repo-root|.agents-dir|skill-dir>] [--reset-agent-models]
  autocoding status --projects <path[,path...]> [--json]
  autocoding sync --projects <path[,path...]> [--dry-run] [--json] [--reset-agent-models]
  autocoding feedback --projects <path[,path...]> [--json]

Examples:
  autocoding init
  autocoding status --projects /Users/elvis/Product/xjmate,/Users/elvis/Product/geesight
  autocoding sync --projects /Users/elvis/Product/xjmate --dry-run
  autocoding feedback --projects /Users/elvis/Product/xjmate,/Users/elvis/Product/geesight --json

Compatibility:
  --ai <value> is accepted for old scripts and ignored.
  --force is accepted for old scripts; project init is already an idempotent full convergence.
  Existing managed-agent model lines are preserved unless --reset-agent-models is used.
`);
    process.exit(0);
  }

  validateCommandArgs(args);

  const here = path.dirname(fileURLToPath(import.meta.url));
  const packagedAssetSkill = path.resolve(here, "..", "assets", "skill");
  const packagedAssetAgents = path.resolve(here, "..", "assets", "agents");
  const assetManifest = path.resolve(here, "..", "assets", "managed-install.json");
  const sourceAssetSkill = path.resolve(here, "..", "..", "src", "auto-coding-skill");
  const sourceAssetAgents = path.resolve(here, "..", "..", "src", "agents");
  const useSourceAssets = exists(sourceAssetSkill) && exists(sourceAssetAgents);
  const assetSkill = useSourceAssets ? sourceAssetSkill : packagedAssetSkill;
  const assetAgents = useSourceAssets ? sourceAssetAgents : packagedAssetAgents;
  if (!exists(assetSkill)) die(`missing assets at ${assetSkill}`);
  if (!exists(assetAgents)) die(`missing assets at ${assetAgents}`);
  if (!exists(assetManifest)) die(`missing managed install manifest at ${assetManifest}`);
  trustedProjectFileHelper = path.join(assetSkill, "scripts", "ap.py");
  const releaseManifest = readInstallManifest(assetManifest);
  if (releaseManifest.skill_version !== readPackageVersion()) {
    die(`managed install manifest version ${releaseManifest.skill_version} does not match package ${readPackageVersion()}`);
  }

  if (args.cmd === "feedback") {
    const script = path.join(assetSkill, "scripts", "ap.py");
    const command = [script, "feedback-collect"];
    for (const project of args.projects) command.push("--project", project);
    if (args.json) command.push("--json");
    const result = spawnSync(runtimePython(), command, {
      encoding: "utf8",
      stdio: "pipe",
      maxBuffer: 2 * 1024 * 1024,
    });
    if (result.error) {
      const code = String(result.error.code || "spawn-error");
      die(`feedback collector runtime failed: ${code}`);
    }
    if (result.signal) die(`feedback collector runtime stopped by signal: ${result.signal}`);
    if (result.status !== 0) {
      const detail = String(result.stderr || "feedback collection failed").trim();
      die(detail || "feedback collection failed");
    }
    process.stdout.write(String(result.stdout || ""));
    process.exit(0);
  }

  if (args.cmd === "status") {
    const projects = args.projects.length ? args.projects : [projectRoot()];
    const results = projects.map(project => projectStatus(project, assetSkill, assetAgents, assetManifest, releaseManifest));
    if (args.json) console.log(JSON.stringify({ version: readPackageVersion(), results }, null, 2));
    else {
      console.log(`[autocoding] version=${readPackageVersion()}`);
      for (const result of results) printProjectStatus(result);
    }
    process.exit(results.every(result => result.ok) ? 0 : 2);
  }

  if (args.cmd === "sync") {
    const projects = args.projects.length ? args.projects : [projectRoot()];
    const interrupted = projects
      .map(project => path.resolve(project))
      .filter(root => recoverInstallTransaction(root, false));
    if (interrupted.length) {
      if (args.dryRun) {
        die(`dry-run cannot recover an interrupted install transaction: ${interrupted.join(", ")}`);
      }
      if (projects.length !== 1) {
        die(
          "multi-project sync remains zero-write when an interrupted install is present; "
          + `recover it with a single-project sync first: ${interrupted.join(", ")}`,
        );
      }
      recoverInstallTransaction(interrupted[0], true);
    }
    assertNoRegisteredTasks(projects);
    const controlledPlans = new Map();
    for (const project of projects) {
      const root = path.resolve(project);
      validateInstallTransactionInputs(root, assetSkill, assetManifest);
      validateProjectManagedTargets(root, assetAgents);
      const plans = planControlledDocuments(root, assetSkill);
      plans.engineeringConvergence = runEngineeringConvergence(root, assetSkill, false);
      plans.feedbackConvergence = runManagedScaffoldConvergence(root, assetSkill, "feedback", false);
      for (const plan of [plans.engineering, plans.agents]) {
        if (plan.archiveDocument) {
          validateProjectFileTarget(root, plan.archiveDocument, "managed document archive");
        }
      }
      for (const [document, plan] of Object.entries(plans)) {
        if (document === "feedbackConvergence" || document === "engineeringConvergence") continue;
        if (plan.state === "invalid" || plan.state === "conflict") {
          const conflicts = (plan.conflicts || [])
            .map(item => `${item.file}:${item.line} [${item.ruleId}] ${item.message}`)
            .join("; ");
          die(`refusing the entire sync batch before writes: ${root} ${document}: ${plan.detail || "invalid managed document"}${conflicts ? `; ${conflicts}` : ""}`);
        }
      }
      controlledPlans.set(root, plans);
    }
    const results = projects.map(project => {
      const root = path.resolve(project);
      return syncProject(
        root,
        assetSkill,
        assetAgents,
        assetManifest,
        releaseManifest,
        args.dryRun,
        args.resetAgentModels,
        args.components,
        controlledPlans.get(root) || null,
      );
    });
    if (args.json) console.log(JSON.stringify({ version: readPackageVersion(), results }, null, 2));
    else {
      console.log(`[autocoding] version=${readPackageVersion()}`);
      for (const result of results) {
        console.log(`[autocoding] project=${result.project}`);
        console.log(`[autocoding] dryRun=${result.dryRun}`);
        console.log(`[autocoding] components=${result.components}`);
        for (const item of result.actions) {
          const detail = item.detail ? ` - ${item.detail}` : "";
          console.log(`[autocoding] ${item.action}: ${item.path}${detail}`);
        }
        if (result.feedback?.available && result.feedback.actionRequiredCount) {
          console.log(`[autocoding] feedback advisory: ${result.feedback.actionRequiredCount} report(s) need maintenance`);
        } else if (result.feedback && !result.feedback.available) {
          console.log(`[autocoding] feedback advisory: ${result.feedback.advisory}`);
        }
      }
    }
    process.exit(0);
  }

  if (args.cmd !== "init") die(`unknown command: ${args.cmd}`);

  if (args.ai) console.warn("[autocoding] --ai is deprecated and ignored; installing generic .agents.");

  requireRuntimeDependencies(assetSkill);

  const { skillDir, agentsDir, projectDir } = resolveInstallDirs(args.mode, args.dest);
  if (args.mode === "project") {
    recoverInstallTransaction(projectDir, true);
    assertNoRegisteredTasks([projectDir]);
    const result = convergeProjectInstall(
      projectDir,
      assetSkill,
      assetAgents,
      assetManifest,
      releaseManifest,
      args.resetAgentModels,
    );
    console.log(`[autocoding] project=${result.project}`);
    for (const item of result.actions) {
      const detail = item.detail ? ` - ${item.detail}` : "";
      console.log(`[autocoding] ${item.action}: ${item.path}${detail}`);
    }
    if (result.feedback?.available && result.feedback.actionRequiredCount) {
      console.log(`[autocoding] feedback advisory: ${result.feedback.actionRequiredCount} report(s) need maintenance`);
    } else if (result.feedback && !result.feedback.available) {
      console.log(`[autocoding] feedback advisory: ${result.feedback.advisory}`);
    }
    console.log("[autocoding] next: fill any blank access.* values and validation.routes in docs/project/auto-coding-skill.yaml, then run doctor.");
  } else {
    rmrf(skillDir);
    copyDir(assetSkill, skillDir);
    syncManagedAgents(assetAgents, agentsDir, { resetModel: args.resetAgentModels, projectRoot: projectDir });
    copyInstallManifest(assetManifest, projectDir);
    applyManifestExecutableBits(projectDir, releaseManifest, "global");
    const integrity = requireInstallIntegrity(projectDir, "global", releaseManifest.skill_version);
    console.log(`[autocoding] installed skill to: ${skillDir}`);
    console.log(`[autocoding] installed agents to: ${agentsDir}`);
    console.log(`[autocoding] installed manifest to: ${installManifestTarget(projectDir)}`);
    console.log(`[autocoding] verified managed install files: ${integrity.checked}`);
  }
  console.log("[autocoding] done.");
}

main();
