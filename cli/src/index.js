#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
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
  const args = { cmd: null, ai: null, mode: "project", dest: null, force: false, dryRun: false, json: false, projects: [] };
  const [,, cmd, ...rest] = argv;
  args.cmd = (!cmd || cmd === "-h" || cmd === "--help") ? "help" : cmd;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--ai") {
      args.ai = takeValue(rest, i, a);
      i += 1;
    }
    else if (a === "--mode") {
      args.mode = takeValue(rest, i, a);
      i += 1;
    }
    else if (a === "--dest") {
      args.dest = takeValue(rest, i, a);
      i += 1;
    }
    else if (a === "--projects") {
      args.projects.push(...takeValue(rest, i, a).split(",").map(x => x.trim()).filter(Boolean));
      i += 1;
    }
    else if (a === "--dry-run") args.dryRun = true;
    else if (a === "--json") args.json = true;
    else if (a === "--force") args.force = true;
    else if (a === "-h" || a === "--help") args.cmd = "help";
    else if (!a.startsWith("--")) args.projects.push(a);
    else die(`unknown argument: ${a}`);
  }
  return args;
}

function exists(p){ try { fs.accessSync(p); return true; } catch { return false; } }
function rmrf(p){ fs.rmSync(p, { recursive: true, force: true }); }
function shouldSkip(name){
  return name === "__pycache__" || name === ".DS_Store" || name.endsWith(".pyc");
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

function listFiles(root, base = root){
  if (!exists(root)) return [];
  const out = [];
  for (const ent of fs.readdirSync(root, { withFileTypes: true })) {
    if (shouldSkip(ent.name)) continue;
    const p = path.join(root, ent.name);
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

function copyMissingDocs(assetSkill, project){
  const srcDocs = path.join(assetSkill, "data", "templates", "docs");
  const dstDocs = path.join(project, "docs");
  const copied = [];
  for (const rel of listFiles(srcDocs)) {
    const src = path.join(srcDocs, rel);
    const dst = path.join(dstDocs, rel);
    if (!exists(dst)) {
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(src, dst);
      copied.push(path.join("docs", rel));
    }
  }
  return copied;
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

function extractFrontmatter(text){
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  return match ? match[1] : "";
}

function frontmatterHasPath(text, keyPath){
  const frontmatter = extractFrontmatter(text);
  if (!frontmatter) return false;

  const stack = [];
  for (const rawLine of frontmatter.split(/\r?\n/)) {
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;
    const match = rawLine.match(/^(\s*)(["']?[^:"']+["']?)\s*:/);
    if (!match) continue;

    const indent = match[1].replace(/\t/g, "  ").length;
    const key = match[2].replace(/^["']|["']$/g, "").trim();
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const currentPath = [...stack.map(item => item.key), key];
    if (currentPath.length === keyPath.length && currentPath.every((part, index) => part === keyPath[index])) {
      return true;
    }
    stack.push({ indent, key });
  }
  return false;
}

function projectStatus(project, assetSkill, assetAgents){
  const root = path.resolve(project);
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const engineering = path.join(root, "docs", "ENGINEERING.md");
  const engineeringMissing = !exists(engineering);
  const requiredConfigPaths = [
    { label: "structure", path: ["structure"] },
    { label: "optimization", path: ["optimization"] },
    { label: "verification.target_env_required", path: ["verification", "target_env_required"] },
    { label: "verification.jenkins_required", path: ["verification", "jenkins_required"] },
    { label: "docs.evidence_log", path: ["docs", "evidence_log"] },
    { label: "docs.task_archive_dir", path: ["docs", "task_archive_dir"] },
    { label: "docs.design_archive_dir", path: ["docs", "design_archive_dir"] },
    { label: "docs.archive_index", path: ["docs", "archive_index"] },
    { label: "docs.active_taskbook_max_lines", path: ["docs", "active_taskbook_max_lines"] },
    { label: "docs.active_closure_log_max_lines", path: ["docs", "active_closure_log_max_lines"] },
    { label: "docs.active_design_max_files", path: ["docs", "active_design_max_files"] },
    { label: "docs.health_baseline", path: ["docs", "health_baseline"] },
    { label: "docs.optimization_backlog", path: ["docs", "optimization_backlog"] },
    { label: "docs.structure_standard", path: ["docs", "structure_standard"] },
  ];
  let missingConfigTokens = requiredConfigPaths.map(item => item.label);
  if (!engineeringMissing) {
    const text = fs.readFileSync(engineering, "utf8");
    missingConfigTokens = requiredConfigPaths
      .filter(item => !frontmatterHasPath(text, item.path))
      .map(item => item.label);
  }
  const scriptDiffs = [];
  for (const name of ["ap.py", "core.py", "http_checks.py"]) {
    const src = path.join(assetSkill, "scripts", name);
    const dst = path.join(toolDir, name);
    if (!exists(dst)) scriptDiffs.push({ path: path.join("docs/tools/autopipeline", name), status: "missing" });
    else if (!fs.readFileSync(src).equals(fs.readFileSync(dst))) scriptDiffs.push({ path: path.join("docs/tools/autopipeline", name), status: "stale" });
  }
  const missingDocs = [];
  const srcDocs = path.join(assetSkill, "data", "templates", "docs");
  for (const rel of listFiles(srcDocs)) {
    if (!exists(path.join(root, "docs", rel))) missingDocs.push(path.join("docs", rel));
  }
  const skillDiffs = exists(skillDir) ? compareDirs(assetSkill, skillDir) : [{ path: ".agents/skills/auto-coding-skill", status: "missing" }];
  const agentDiffs = exists(agentsDir) ? compareDirs(assetAgents, agentsDir, { includeExtra: false }) : [{ path: ".agents/agents", status: "missing" }];
  const ok = skillDiffs.length === 0 && agentDiffs.length === 0 && scriptDiffs.length === 0 && missingDocs.length === 0 && missingConfigTokens.length === 0;
  let next = "";
  if (!exists(skillDir) || !exists(agentsDir)) {
    next = "run autocoding init --force";
  } else if (skillDiffs.length || agentDiffs.length) {
    next = "run autocoding sync --projects <repo>";
  } else if (engineeringMissing || scriptDiffs.length || missingDocs.length) {
    next = "run autocoding sync --projects <repo> or python3 .agents/skills/auto-coding-skill/scripts/ap.py --repo . install";
  } else if (missingConfigTokens.length) {
    next = "run project-local ap.py upgrade --write to merge docs/ENGINEERING.md safely";
  }
  return {
    project: root,
    ok,
    skillDiffs,
    agentDiffs,
    scriptDiffs,
    missingDocs,
    missingConfigTokens,
    next,
  };
}

function printProjectStatus(result){
  console.log(`[autocoding] project=${result.project}`);
  console.log(`[autocoding] ok=${result.ok}`);
  for (const [label, items] of [["skill", result.skillDiffs], ["agents", result.agentDiffs], ["scripts", result.scriptDiffs]]) {
    for (const item of items) console.log(`[autocoding] ${label} ${item.status}: ${item.path}`);
  }
  for (const item of result.missingDocs) console.log(`[autocoding] doc missing: ${item}`);
  for (const item of result.missingConfigTokens) console.log(`[autocoding] config missing path: ${item}`);
  if (result.next) console.log(`[autocoding] next: ${result.next}`);
}

function syncProject(project, assetSkill, assetAgents, dryRun){
  const root = path.resolve(project);
  const actions = [];
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const engineering = path.join(root, "docs", "ENGINEERING.md");
  const engineeringWasMissing = !exists(engineering);
  const templateEngineering = path.join(assetSkill, "data", "templates", "ENGINEERING.md");
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, skillDir) });
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, agentsDir) });
  for (const name of ["ap.py", "core.py", "http_checks.py"]) {
    actions.push({ action: dryRun ? "would-sync" : "sync", path: path.join("docs/tools/autopipeline", name) });
  }
  if (!dryRun) {
    rmrf(skillDir);
    copyDir(assetSkill, skillDir);
    copyDir(assetAgents, agentsDir);
    fs.mkdirSync(toolDir, { recursive: true });
    for (const name of ["ap.py", "core.py", "http_checks.py"]) {
      fs.copyFileSync(path.join(assetSkill, "scripts", name), path.join(toolDir, name));
    }
    for (const copied of copyMissingDocs(assetSkill, root)) actions.push({ action: "create", path: copied });
    if (engineeringWasMissing) {
      fs.mkdirSync(path.dirname(engineering), { recursive: true });
      fs.copyFileSync(templateEngineering, engineering);
      actions.push({ action: "create", path: path.join("docs", "ENGINEERING.md") });
    }
  } else {
    const srcDocs = path.join(assetSkill, "data", "templates", "docs");
    for (const rel of listFiles(srcDocs)) {
      if (!exists(path.join(root, "docs", rel))) actions.push({ action: "would-create", path: path.join("docs", rel) });
    }
    if (engineeringWasMissing) actions.push({ action: "would-create", path: path.join("docs", "ENGINEERING.md") });
  }
  if (!engineeringWasMissing) {
    actions.push({ action: "manual", path: "docs/ENGINEERING.md", detail: "merge existing files with ap.py upgrade --write" });
  }
  return { project: root, dryRun, actions };
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
      };
    }
    if (path.basename(dest) === "skills" && path.basename(parent) === ".agents") {
      return {
        skillDir: path.join(dest, "auto-coding-skill"),
        agentsDir: path.join(parent, "agents"),
      };
    }
    if (path.basename(dest) === "agents" && path.basename(parent) === ".agents") {
      return {
        skillDir: path.join(parent, "skills", "auto-coding-skill"),
        agentsDir: dest,
      };
    }
    if (path.basename(dest) === ".agents") {
      return {
        skillDir: path.join(dest, "skills", "auto-coding-skill"),
        agentsDir: path.join(dest, "agents"),
      };
    }
    return {
      skillDir: path.join(dest, ".agents", "skills", "auto-coding-skill"),
      agentsDir: path.join(dest, ".agents", "agents"),
    };
  }

  const root = mode === "project" ? projectRoot() : os.homedir();
  return {
    skillDir: path.join(root, ".agents", "skills", "auto-coding-skill"),
    agentsDir: path.join(root, ".agents", "agents"),
  };
}

function main(){
  const args = parseArgs(process.argv);

  if (args.cmd === "help" || !args.cmd) {
    console.log(`
autocoding - install auto-coding-skill into generic .agents paths

Usage:
  autocoding init [--mode project|global] [--dest <repo-root|.agents-dir|skill-dir>] [--force]
  autocoding status --projects <path[,path...]> [--json]
  autocoding sync --projects <path[,path...]> [--dry-run] [--json]

Examples:
  autocoding init
  autocoding status --projects /Users/elvis/Product/xjmate,/Users/elvis/Product/geesight
  autocoding sync --projects /Users/elvis/Product/xjmate --dry-run

Compatibility:
  --ai <value> is accepted for old scripts and ignored.
`);
    process.exit(0);
  }

  const here = path.dirname(fileURLToPath(import.meta.url));
  const assetSkill = path.resolve(here, "..", "assets", "skill");
  const assetAgents = path.resolve(here, "..", "assets", "agents");
  if (!exists(assetSkill)) die(`missing assets at ${assetSkill}`);
  if (!exists(assetAgents)) die(`missing assets at ${assetAgents}`);

  if (args.cmd === "status") {
    const projects = args.projects.length ? args.projects : [projectRoot()];
    const results = projects.map(project => projectStatus(project, assetSkill, assetAgents));
    if (args.json) console.log(JSON.stringify({ version: readPackageVersion(), results }, null, 2));
    else {
      console.log(`[autocoding] version=${readPackageVersion()}`);
      for (const result of results) printProjectStatus(result);
    }
    process.exit(results.every(result => result.ok) ? 0 : 2);
  }

  if (args.cmd === "sync") {
    const projects = args.projects.length ? args.projects : [projectRoot()];
    const results = projects.map(project => syncProject(project, assetSkill, assetAgents, args.dryRun));
    if (args.json) console.log(JSON.stringify({ version: readPackageVersion(), results }, null, 2));
    else {
      console.log(`[autocoding] version=${readPackageVersion()}`);
      for (const result of results) {
        console.log(`[autocoding] project=${result.project}`);
        console.log(`[autocoding] dryRun=${result.dryRun}`);
        for (const item of result.actions) {
          const detail = item.detail ? ` - ${item.detail}` : "";
          console.log(`[autocoding] ${item.action}: ${item.path}${detail}`);
        }
      }
    }
    process.exit(0);
  }

  if (args.cmd !== "init") die(`unknown command: ${args.cmd}`);

  if (args.ai) console.warn("[autocoding] --ai is deprecated and ignored; installing generic .agents.");

  const { skillDir, agentsDir } = resolveInstallDirs(args.mode, args.dest);
  const existingTargets = [skillDir, agentsDir].filter(target => exists(target));
  if (existingTargets.length && !args.force) {
    die(`target exists: ${existingTargets.join(", ")}\nRe-run with --force to overwrite managed templates.`);
  }
  if (exists(skillDir)) {
    rmrf(skillDir);
  }
  copyDir(assetSkill, skillDir);
  console.log(`[autocoding] installed skill to: ${skillDir}`);

  copyDir(assetAgents, agentsDir);
  console.log(`[autocoding] installed agents to: ${agentsDir}`);

  console.log("[autocoding] done.");
}

main();
