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

function runEngineeringConvergence(project, skillRoot, write){
  const script = path.join(skillRoot, "scripts", "ap.py");
  const command = [script, "--repo", project, "project-converge", "--json"];
  if (write) command.push("--write");
  const result = spawnSync(runtimePython(), command, { encoding: "utf8", stdio: "pipe" });
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
  fs.mkdirSync(agentsDir, { recursive: true });
  const bindings = [];
  const managedFiles = new Set(listFiles(assetAgents));
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
    return typeof scripts["test:changed"] === "string" && scripts["test:changed"].trim()
      ? { project_fast: "npm run test:changed" }
      : {};
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
    "docs/ENGINEERING.md project-fact sections or docs/project/.",
    "",
    "---",
    "",
  ].join("\n");
  const archiveOutput = `${archiveHeader}${current}`;
  const archiveDir = path.join(root, "docs", "archive", "workflow");
  let archiveDocument = path.join(archiveDir, `ENGINEERING.pre-${version}.md`);
  if (exists(archiveDocument) && fs.readFileSync(archiveDocument, "utf8") !== archiveOutput) {
    archiveDocument = path.join(
      archiveDir,
      `ENGINEERING.pre-${version}-${engineeringBodyHash(current).slice(0, 12)}.md`,
    );
  }
  return {
    archiveDocument,
    archiveOutput,
    archiveRequired: !exists(archiveDocument),
  };
}

function planAgentsDocumentSync(project, assetSkill, policy = loadWorkflowMigrationPolicy(assetSkill)){
  const root = path.resolve(project);
  const agentsDocument = path.join(root, "AGENTS.md");
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
    "Move any still-current project facts into docs/ENGINEERING.md or docs/project/",
    "without copying workflow rules back into the root AGENTS.md.",
    "",
    "---",
    "",
  ].join("\n");
  const archiveOutput = `${archiveHeader}${current}`;
  const archiveDir = path.join(root, "docs", "archive", "workflow");
  let archiveDocument = path.join(archiveDir, `AGENTS.pre-${templateRegion.version}.md`);
  if (exists(archiveDocument) && fs.readFileSync(archiveDocument, "utf8") !== archiveOutput) {
    archiveDocument = path.join(
      archiveDir,
      `AGENTS.pre-${templateRegion.version}-${engineeringBodyHash(current).slice(0, 12)}.md`,
    );
  }
  const currentRegion = inspectManagedAgentsDocument(current);
  return {
    state: currentRegion.state === "present" ? "stale" : "legacy-custom",
    version: templateRegion.version,
    ...(currentRegion.state === "present" ? { previousVersion: currentRegion.version } : {}),
    output: template,
    agentsDocument,
    archiveDocument,
    archiveOutput,
    archiveRequired: !exists(archiveDocument),
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
  return {
    state: plan.state,
    version: plan.version || "unknown",
    ...(plan.previousVersion ? { previousVersion: plan.previousVersion } : {}),
    ...(plan.previousBodyHash ? { previousBodyHash: plan.previousBodyHash } : {}),
    ...(plan.preservedCustom ? { preservedCustom: true } : {}),
    ...(plan.archiveDocument ? { archive: plan.archiveDocument } : {}),
    ...(plan.migrations?.length ? { migrations: plan.migrations } : {}),
    ...(plan.conflicts?.length ? { conflicts: plan.conflicts } : {}),
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

function extractFrontmatter(text){
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  return match ? match[1] : "";
}

function frontmatterPathState(text, keyPath){
  const frontmatter = extractFrontmatter(text);
  if (!frontmatter) return { present: false, value: "" };

  const stack = [];
  for (const rawLine of frontmatter.split(/\r?\n/)) {
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;
    const match = rawLine.match(/^(\s*)(["']?[^:"']+["']?)\s*:(.*)$/);
    if (!match) continue;

    const indent = match[1].replace(/\t/g, "  ").length;
    const key = match[2].replace(/^["']|["']$/g, "").trim();
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const currentPath = [...stack.map(item => item.key), key];
    if (currentPath.length === keyPath.length && currentPath.every((part, index) => part === keyPath[index])) {
      return { present: true, value: match[3].trim() };
    }
    stack.push({ indent, key });
  }
  return { present: false, value: "" };
}

function frontmatterSequenceHasItems(text, keyPath){
  const frontmatter = extractFrontmatter(text);
  if (!frontmatter) return false;
  const lines = frontmatter.split(/\r?\n/);
  const stack = [];
  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;
    const match = rawLine.match(/^(\s*)(["']?[^:"']+["']?)\s*:(.*)$/);
    if (!match) continue;
    const indent = match[1].replace(/\t/g, "  ").length;
    const key = match[2].replace(/^["']|["']$/g, "").trim();
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const currentPath = [...stack.map(item => item.key), key];
    if (currentPath.length === keyPath.length && currentPath.every((part, pathIndex) => part === keyPath[pathIndex])) {
      const inline = match[3].trim();
      if (/^\[(?:\s*[^\]])/.test(inline)) return true;
      for (let child = index + 1; child < lines.length; child += 1) {
        if (!lines[child].trim() || lines[child].trim().startsWith("#")) continue;
        const childIndent = lines[child].match(/^\s*/)[0].replace(/\t/g, "  ").length;
        if (/^\s*-\s+\S/.test(lines[child]) && childIndent >= indent) return true;
        if (childIndent <= indent) return false;
      }
      return false;
    }
    stack.push({ indent, key });
  }
  return false;
}

function legacyGateEscalationTokens(text){
  const frontmatter = extractFrontmatter(text);
  if (!frontmatter) return [];
  const tokens = [];
  let gateIndent = null;
  let rulesIndent = null;
  for (const rawLine of frontmatter.split(/\r?\n/)) {
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;
    const indent = rawLine.match(/^\s*/)[0].replace(/\t/g, "  ").length;
    const match = rawLine.trim().match(/^(?:-\s*)?([A-Za-z0-9_-]+)\s*:(.*)$/);
    if (gateIndent === null) {
      if (match?.[1] === "gate") gateIndent = indent;
      continue;
    }
    if (indent <= gateIndent) break;
    if (rulesIndent !== null && indent <= rulesIndent) rulesIndent = null;
    const key = match?.[1] || "";
    const value = match?.[2]?.trim() || "";
    if (key === "full_on") tokens.push("gate.full_on (legacy automatic full escalation)");
    if (key === "full_on_unknown" && /^(?:true|yes|on|1)$/i.test(frontmatterScalarValue(value))) {
      tokens.push("gate.full_on_unknown=true (legacy automatic full escalation)");
    }
    if (key === "rules") {
      if (value && value !== "[]") tokens.push("gate.rules inline value (run upgrade to migrate safely)");
      rulesIndent = indent;
      continue;
    }
    if (rulesIndent !== null && indent > rulesIndent && (key === "scope" || key === "commands")) {
      tokens.push(`gate.rules[].${key} (legacy automatic gate escalation)`);
    }
  }
  return [...new Set(tokens)];
}

function frontmatterValueIsFilled(raw){
  const source = String(raw || "");
  let quote = "";
  let escaped = false;
  let commentAt = -1;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quote === '"' && char === "\\" && !escaped) {
      escaped = true;
      continue;
    }
    if ((char === '"' || char === "'") && !escaped) {
      quote = quote === char ? "" : (quote || char);
    } else if (char === "#" && !quote && (index === 0 || /\s/.test(source[index - 1]))) {
      commentAt = index;
      break;
    }
    escaped = false;
  }
  const value = (commentAt >= 0 ? source.slice(0, commentAt) : source).trim();
  if (!value || value.startsWith("#")) return false;
  const quoted = (
    (value.startsWith('"') && value.endsWith('"'))
    || (value.startsWith("'") && value.endsWith("'"))
  );
  const unquoted = quoted ? value.slice(1, -1).trim() : value;
  let semanticValue = unquoted;
  if (value.startsWith('"') && value.endsWith('"')) {
    try {
      semanticValue = JSON.parse(value).trim();
    } catch {
      // Be conservative for YAML-only escape sequences that this fast parser
      // cannot decode consistently with PyYAML. Single quotes remain available
      // for literal backslashes.
      return false;
    }
  } else if (value.startsWith("'") && value.endsWith("'")) {
    semanticValue = unquoted.replace(/''/g, "'").trim();
  }
  if (!semanticValue) return false;
  if (!quoted && (
    /^(?:null|true|false|yes|no|on|off|~)$/i.test(semanticValue)
    || /^(?:\[|\{|\||>|&|\*|!)/.test(semanticValue)
    || /^[+-]?(?:0b[01_]+|0o[0-7_]+|0x[\da-f_]+|\d[\d_]*(?:\.\d*)?(?:e[+-]?\d+)?|\.\d+(?:e[+-]?\d+)?|\.inf|\.nan)$/i.test(semanticValue)
    || /^\d{4}-\d{1,2}-\d{1,2}(?:[Tt ]|$)/.test(semanticValue)
    || /^\d+(?::\d+)+(?:\.\d+)?$/.test(semanticValue)
  )) return false;
  const upper = semanticValue.toUpperCase();
  return ![
    "N/A", "TODO", "TBD", "CHANGEME", "CHANGE_ME", "FILL_ME", "FILL-ME",
    "PLACEHOLDER", "XXX", "NULL", "~",
  ].includes(upper)
    && !(semanticValue.startsWith("<") && semanticValue.endsWith(">"))
    && !upper.startsWith("REPLACE_")
    && !upper.startsWith("YOUR_");
}

function frontmatterScalarValue(raw){
  const source = String(raw || "");
  let quote = "";
  let escaped = false;
  let commentAt = -1;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quote === '"' && char === "\\" && !escaped) {
      escaped = true;
      continue;
    }
    if ((char === '"' || char === "'") && !escaped) {
      quote = quote === char ? "" : (quote || char);
    } else if (char === "#" && !quote && (index === 0 || /\s/.test(source[index - 1]))) {
      commentAt = index;
      break;
    }
    escaped = false;
  }
  const value = (commentAt >= 0 ? source.slice(0, commentAt) : source).trim();
  if (value.startsWith('"') && value.endsWith('"')) {
    try { return JSON.parse(value).trim(); } catch { return ""; }
  }
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1).replace(/''/g, "'").trim();
  }
  return value;
}

function projectStatus(project, assetSkill, assetAgents){
  const root = path.resolve(project);
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
  if (!engineeringMissing) {
    const text = fs.readFileSync(engineering, "utf8");
    const states = requiredConfigPaths.map(item => ({ item, state: frontmatterPathState(text, item.path) }));
    missingConfigPaths = states.filter(({ state }) => !state.present).map(({ item }) => item.label);
    unfilledConfigTokens = states
      .filter(({ item, state }) => state.present && (
        (item.filled === true && !frontmatterValueIsFilled(state.value))
        || (item.sequence === true && !frontmatterSequenceHasItems(text, item.path))
      ))
      .map(({ item }) => item.label);
    const isolationState = frontmatterPathState(text, ["concurrency", "isolation"]);
    if (isolationState.present && !["adaptive", "worktree"].includes(frontmatterScalarValue(isolationState.value).toLowerCase())) {
      invalidConfigTokens.push("concurrency.isolation (must be adaptive or worktree)");
    }
    for (const pathParts of [
      ["validation", "max_command_seconds"],
      ["validation", "max_total_seconds"],
    ]) {
      const state = frontmatterPathState(text, pathParts);
      if (!state.present) continue;
      const value = Number(frontmatterScalarValue(state.value));
      if (!Number.isFinite(value) || value <= 0) {
        invalidConfigTokens.push(`${pathParts.join(".")} (must be > 0)`);
      }
    }
    const commandState = frontmatterPathState(text, ["validation", "max_command_seconds"]);
    const totalState = frontmatterPathState(text, ["validation", "max_total_seconds"]);
    const commandBudget = Number(frontmatterScalarValue(commandState.value));
    const totalBudget = Number(frontmatterScalarValue(totalState.value));
    if (commandState.present && totalState.present && Number.isFinite(commandBudget) && Number.isFinite(totalBudget) && commandBudget > totalBudget) {
      invalidConfigTokens.push("validation.max_command_seconds (cannot exceed max_total_seconds)");
    }
    invalidConfigTokens.push(...legacyGateEscalationTokens(text));
  }
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
  const ok = skillDiffs.length === 0 && agentDiffs.length === 0 && scriptDiffs.length === 0 && missingDocs.length === 0 && docsDiffs.length === 0 && missingConfigTokens.length === 0 && managedWorkflow.state === "current" && managedAgentsDocument.state === "current";
  let next = "";
  if (!exists(skillDir) || !exists(agentsDir)) {
    next = "run autocoding init";
  } else if (skillDiffs.length || agentDiffs.length) {
    next = "run autocoding init";
  } else if (engineeringMissing || managedWorkflow.state !== "current" || managedAgentsDocument.state !== "current" || scriptDiffs.length || missingDocs.length || docsDiffs.length) {
    next = "run autocoding init";
  } else if (missingConfigPaths.length) {
    next = "run autocoding init, fill every required value in docs/ENGINEERING.md, then run doctor";
  } else if (invalidConfigTokens.length) {
    next = "run autocoding init, then run doctor";
  } else if (unfilledConfigTokens.length) {
    next = "fill every required value in docs/ENGINEERING.md, then run project-local ap.py doctor";
  }
  return {
    project: root,
    ok,
    skillDiffs,
    agentDiffs,
    agentBindings: agentStatus.bindings,
    scriptDiffs,
    docsDiffs,
    missingDocs,
    missingConfigTokens,
    missingConfigPaths,
    unfilledConfigTokens,
    invalidConfigTokens,
    managedWorkflow,
    managedAgentsDocument,
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
  if (result.next) console.log(`[autocoding] next: ${result.next}`);
}

function engineeringPlanDetail(plan){
  if (plan.state === "legacy-custom") return `managed workflow preserved-custom -> ${plan.version}`;
  if (plan.state === "legacy-official") return `managed workflow official-legacy -> ${plan.version}`;
  return `managed workflow ${plan.state} -> ${plan.version}`;
}

function syncProject(project, assetSkill, assetAgents, dryRun, resetAgentModels = false, components = "all", controlledPlans = null){
  const root = path.resolve(project);
  const actions = [];
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const skillOnly = components === "skill";
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, skillDir) });
  if (!dryRun) {
    rmrf(skillDir);
    copyDir(assetSkill, skillDir);
  }
  if (skillOnly) return { project: root, dryRun, components, actions };

  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const plans = controlledPlans || planControlledDocuments(root, assetSkill);
  const plan = plans.engineering;
  const agentsDocumentPlan = plans.agents;
  actions.push({ action: dryRun ? "would-sync" : "sync", path: path.relative(root, agentsDir) });
  actions.push({ action: dryRun ? "would-sync" : "sync", path: "docs/tools/autopipeline/ap.py" });
  if (!dryRun) {
    syncManagedAgents(assetAgents, agentsDir, { resetModel: resetAgentModels });
    fs.mkdirSync(toolDir, { recursive: true });
    fs.copyFileSync(path.join(assetSkill, "data", "templates", "tools", "ap.py"), path.join(toolDir, "ap.py"));
    for (const copied of copyMissingDocs(assetSkill, root)) actions.push({ action: "create", path: copied });
    if (plan.state !== "current") {
      if (plan.archiveRequired) {
        fs.mkdirSync(path.dirname(plan.archiveDocument), { recursive: true });
        fs.writeFileSync(plan.archiveDocument, plan.archiveOutput);
        actions.push({
          action: "archive",
          path: path.relative(root, plan.archiveDocument),
          detail: "previous ENGINEERING.md before duplicate workflow cleanup",
        });
      }
      fs.mkdirSync(path.dirname(plan.engineering), { recursive: true });
      fs.writeFileSync(plan.engineering, plan.output);
      actions.push({
        action: plan.state === "missing" ? "create" : "update",
        path: path.join("docs", "ENGINEERING.md"),
        detail: engineeringPlanDetail(plan),
      });
    }
    if (agentsDocumentPlan.state !== "current") {
      if (agentsDocumentPlan.archiveRequired) {
        fs.mkdirSync(path.dirname(agentsDocumentPlan.archiveDocument), { recursive: true });
        fs.writeFileSync(agentsDocumentPlan.archiveDocument, agentsDocumentPlan.archiveOutput);
        actions.push({
          action: "archive",
          path: path.relative(root, agentsDocumentPlan.archiveDocument),
          detail: "previous root AGENTS.md; historical and non-authoritative",
        });
      }
      fs.writeFileSync(agentsDocumentPlan.agentsDocument, agentsDocumentPlan.output);
      actions.push({
        action: agentsDocumentPlan.state === "missing" ? "create" : "update",
        path: "AGENTS.md",
        detail: `managed agents ${agentsDocumentPlan.state} -> ${agentsDocumentPlan.version}`,
      });
    }
  } else {
    for (const rel of CORE_DOCS) {
      if (!exists(path.join(root, "docs", rel))) actions.push({ action: "would-create", path: path.join("docs", rel) });
    }
    if (plan.state !== "current") {
      if (plan.archiveRequired) {
        actions.push({
          action: "would-archive",
          path: path.relative(root, plan.archiveDocument),
          detail: "previous ENGINEERING.md before duplicate workflow cleanup",
        });
      }
      actions.push({
        action: plan.state === "missing" ? "would-create" : "would-update",
        path: path.join("docs", "ENGINEERING.md"),
        detail: engineeringPlanDetail(plan),
      });
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
  return {
    project: root,
    dryRun,
    components,
    managedWorkflow: publicEngineeringPlan(plan),
    managedAgentsDocument: publicEngineeringPlan(agentsDocumentPlan),
    actions,
  };
}

function convergeProjectInstall(project, assetSkill, assetAgents, resetAgentModels){
  const root = path.resolve(project);
  const skillDir = path.join(root, ".agents", "skills", "auto-coding-skill");
  const agentsDir = path.join(root, ".agents", "agents");
  const toolDir = path.join(root, "docs", "tools", "autopipeline");
  const actions = [];

  // Validate the authoritative template and legacy input before the first write.
  runEngineeringConvergence(root, assetSkill, false);

  rmrf(skillDir);
  copyDir(assetSkill, skillDir);
  actions.push({ action: "replace", path: path.relative(root, skillDir) });

  syncManagedAgents(assetAgents, agentsDir, { resetModel: resetAgentModels, removeExtra: true });
  actions.push({ action: "sync", path: path.relative(root, agentsDir) });

  fs.mkdirSync(toolDir, { recursive: true });
  fs.copyFileSync(
    path.join(assetSkill, "data", "templates", "tools", "ap.py"),
    path.join(toolDir, "ap.py"),
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
      let archive = path.join(
        root,
        ".agents",
        "archive",
        "auto-coding-skill",
        readPackageVersion(),
        "AGENTS.md",
      );
      if (exists(archive) && fs.readFileSync(archive, "utf8") !== currentAgents) {
        archive = path.join(
          path.dirname(archive),
          `AGENTS-${crypto.createHash("sha256").update(currentAgents).digest("hex").slice(0, 12)}.md`,
        );
      }
      if (!exists(archive)) {
        fs.mkdirSync(path.dirname(archive), { recursive: true });
        fs.writeFileSync(archive, currentAgents);
        actions.push({
          action: "archive",
          path: path.relative(root, archive),
          detail: "historical and non-authoritative",
        });
      }
    }
    fs.writeFileSync(agentsDocument, canonicalAgents);
    actions.push({ action: "replace", path: "AGENTS.md" });
  }

  const engineering = runEngineeringConvergence(root, skillDir, true);
  actions.push(...engineering.actions);
  return { project: root, actions };
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

Examples:
  autocoding init
  autocoding status --projects /Users/elvis/Product/xjmate,/Users/elvis/Product/geesight
  autocoding sync --projects /Users/elvis/Product/xjmate --dry-run

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
  const sourceAssetSkill = path.resolve(here, "..", "..", "src", "auto-coding-skill");
  const sourceAssetAgents = path.resolve(here, "..", "..", "src", "agents");
  const useSourceAssets = exists(sourceAssetSkill) && exists(sourceAssetAgents);
  const assetSkill = useSourceAssets ? sourceAssetSkill : packagedAssetSkill;
  const assetAgents = useSourceAssets ? sourceAssetAgents : packagedAssetAgents;
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
    assertNoRegisteredTasks(projects);
    const controlledPlans = new Map();
    for (const project of projects) {
      const root = path.resolve(project);
      const plans = planControlledDocuments(root, assetSkill);
      for (const [document, plan] of Object.entries(plans)) {
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
      }
    }
    process.exit(0);
  }

  if (args.cmd !== "init") die(`unknown command: ${args.cmd}`);

  if (args.ai) console.warn("[autocoding] --ai is deprecated and ignored; installing generic .agents.");

  requireRuntimeDependencies(assetSkill);

  const { skillDir, agentsDir, projectDir } = resolveInstallDirs(args.mode, args.dest);
  if (args.mode === "project") {
    assertNoRegisteredTasks([projectDir]);
    const result = convergeProjectInstall(projectDir, assetSkill, assetAgents, args.resetAgentModels);
    console.log(`[autocoding] project=${result.project}`);
    for (const item of result.actions) {
      const detail = item.detail ? ` - ${item.detail}` : "";
      console.log(`[autocoding] ${item.action}: ${item.path}${detail}`);
    }
    console.log("[autocoding] next: fill any blank access.* values and validation.routes in docs/ENGINEERING.md, then run doctor.");
  } else {
    rmrf(skillDir);
    copyDir(assetSkill, skillDir);
    syncManagedAgents(assetAgents, agentsDir, { resetModel: args.resetAgentModels });
    console.log(`[autocoding] installed skill to: ${skillDir}`);
    console.log(`[autocoding] installed agents to: ${agentsDir}`);
  }
  console.log("[autocoding] done.");
}

main();
