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
  const args = {
    cmd: null,
    ai: null,
    mode: "project",
    dest: null,
    force: false,
    dryRun: false,
    json: false,
    resetAgentModels: false,
    projects: [],
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
  projects: "--projects/positional project",
};

const COMMAND_ARGS = {
  init: new Set(["ai", "mode", "dest", "force", "resetAgentModels"]),
  status: new Set(["projects", "json"]),
  sync: new Set(["projects", "dryRun", "json", "resetAgentModels"]),
};

function validateCommandArgs(args){
  const allowed = COMMAND_ARGS[args.cmd];
  if (!allowed) return;
  const invalid = [...args.provided].filter(name => !allowed.has(name));
  if (invalid.length) {
    die(`${invalid.map(name => ARG_FLAGS[name] || name).join(", ")} not valid for '${args.cmd}'`);
  }
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

const CORE_DOCS = ["tasks/taskbook.md", "tasks/closure-log.md"];

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
  fs.mkdirSync(agentsDir, { recursive: true });
  const bindings = [];
  for (const rel of listFiles(assetAgents)) {
    const src = path.join(assetAgents, rel);
    const dst = path.join(agentsDir, rel);
    const templateText = fs.readFileSync(src, "utf8");
    const existingText = exists(dst) ? fs.readFileSync(dst, "utf8") : "";
    const rendered = renderManagedAgent(templateText, existingText, options.resetModel === true);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.writeFileSync(dst, rendered);
    const model = inspectTopLevelModel(rendered);
    bindings.push({ agent: rel, model: model.present ? model.value : "inherit" });
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
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(src, dst);
      copied.push(path.join("docs", rel));
    }
  }
  return copied;
}

function inferredGateCommands(project){
  const pkg = path.join(project, "package.json");
  if (!exists(pkg)) return {};
  try {
    const parsed = JSON.parse(fs.readFileSync(pkg, "utf8"));
    const scripts = parsed?.scripts;
    if (!scripts || typeof scripts !== "object") return {};
    const inferred = {};
    if (typeof scripts.test === "string" && scripts.test.trim()) {
      inferred.gate_changed = typeof scripts["test:changed"] === "string" && scripts["test:changed"].trim()
        ? "npm run test:changed"
        : "npm test";
      inferred.gate_standard = typeof scripts["test:standard"] === "string" && scripts["test:standard"].trim()
        ? "npm run test:standard"
        : "npm test";
    }
    if (typeof scripts["test:full"] === "string" && scripts["test:full"].trim()) {
      inferred.gate_full = "npm run test:full";
    }
    return inferred;
  } catch {
    return {};
  }
}

function renderEngineeringTemplate(templateText, project){
  let rendered = templateText.replace(
    'project:\n  name: ""',
    `project:\n  name: ${JSON.stringify(path.basename(path.resolve(project)))}`,
  );
  for (const [key, gate] of Object.entries(inferredGateCommands(project))) {
    rendered = rendered.replace(`  ${key}: ""`, `  ${key}: ${JSON.stringify(gate)}`);
  }
  return rendered;
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
    { label: "workflow.mode", path: ["workflow", "mode"] },
    { label: "project.name", path: ["project", "name"] },
    { label: "verification.target_env_required", path: ["verification", "target_env_required"] },
    { label: "verification.jenkins_required", path: ["verification", "jenkins_required"] },
    { label: "docs.taskbook", path: ["docs", "taskbook"] },
    { label: "docs.closure_log", path: ["docs", "closure_log"] },
  ];
  let missingConfigTokens = requiredConfigPaths.map(item => item.label);
  if (!engineeringMissing) {
    const text = fs.readFileSync(engineering, "utf8");
    missingConfigTokens = requiredConfigPaths
      .filter(item => !frontmatterHasPath(text, item.path))
      .map(item => item.label);
  }
  const scriptDiffs = [];
  const launcherSrc = path.join(assetSkill, "data", "templates", "tools", "ap.py");
  const launcherDst = path.join(toolDir, "ap.py");
  if (!exists(launcherDst)) scriptDiffs.push({ path: "docs/tools/autopipeline/ap.py", status: "missing" });
  else if (!fs.readFileSync(launcherSrc).equals(fs.readFileSync(launcherDst))) {
    scriptDiffs.push({ path: "docs/tools/autopipeline/ap.py", status: "stale" });
  }
  const missingDocs = [];
  const srcDocs = path.join(assetSkill, "data", "templates", "docs");
  for (const rel of CORE_DOCS) {
    if (!exists(path.join(root, "docs", rel))) missingDocs.push(path.join("docs", rel));
  }
  const skillDiffs = exists(skillDir) ? compareDirs(assetSkill, skillDir, { includeExtra: false }) : [{ path: ".agents/skills/auto-coding-skill", status: "missing" }];
  const agentStatus = exists(agentsDir)
    ? compareManagedAgents(assetAgents, agentsDir)
    : { diffs: [{ path: ".agents/agents", status: "missing" }], bindings: [] };
  const agentDiffs = agentStatus.diffs;
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
    agentBindings: agentStatus.bindings,
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
    for (const item of items) {
      const detail = item.detail ? ` - ${item.detail}` : "";
      console.log(`[autocoding] ${label} ${item.status}: ${item.path}${detail}`);
    }
  }
  for (const item of result.missingDocs) console.log(`[autocoding] doc missing: ${item}`);
  for (const item of result.missingConfigTokens) console.log(`[autocoding] config missing path: ${item}`);
  for (const item of result.agentBindings || []) console.log(`[autocoding] agent model: ${item.agent} -> ${item.model}`);
  if (result.next) console.log(`[autocoding] next: ${result.next}`);
}

function syncProject(project, assetSkill, assetAgents, dryRun, resetAgentModels = false){
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
  actions.push({ action: dryRun ? "would-sync" : "sync", path: "docs/tools/autopipeline/ap.py" });
  if (!dryRun) {
    rmrf(skillDir);
    copyDir(assetSkill, skillDir);
    syncManagedAgents(assetAgents, agentsDir, { resetModel: resetAgentModels });
    fs.mkdirSync(toolDir, { recursive: true });
    fs.copyFileSync(path.join(assetSkill, "data", "templates", "tools", "ap.py"), path.join(toolDir, "ap.py"));
    for (const copied of copyMissingDocs(assetSkill, root)) actions.push({ action: "create", path: copied });
    if (engineeringWasMissing) {
      fs.mkdirSync(path.dirname(engineering), { recursive: true });
      fs.writeFileSync(engineering, renderEngineeringTemplate(fs.readFileSync(templateEngineering, "utf8"), root));
      actions.push({ action: "create", path: path.join("docs", "ENGINEERING.md") });
    }
  } else {
    for (const rel of CORE_DOCS) {
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
  autocoding init [--mode project|global] [--dest <repo-root|.agents-dir|skill-dir>] [--force] [--reset-agent-models]
  autocoding status --projects <path[,path...]> [--json]
  autocoding sync --projects <path[,path...]> [--dry-run] [--json] [--reset-agent-models]

Examples:
  autocoding init
  autocoding status --projects /Users/elvis/Product/xjmate,/Users/elvis/Product/geesight
  autocoding sync --projects /Users/elvis/Product/xjmate --dry-run

Compatibility:
  --ai <value> is accepted for old scripts and ignored.
  Existing managed-agent model lines are preserved unless --reset-agent-models is used.
`);
    process.exit(0);
  }

  validateCommandArgs(args);

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
    const results = projects.map(project => syncProject(project, assetSkill, assetAgents, args.dryRun, args.resetAgentModels));
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

  syncManagedAgents(assetAgents, agentsDir, { resetModel: args.resetAgentModels });
  console.log(`[autocoding] installed agents to: ${agentsDir}`);

  console.log("[autocoding] done.");
}

main();
