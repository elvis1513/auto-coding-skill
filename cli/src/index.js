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
  const args = { cmd: null, ai: null, mode: "project", dest: null, force: false };
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
    else if (a === "--force") args.force = true;
    else if (a === "-h" || a === "--help") args.cmd = "help";
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

function projectRoot(){ return process.cwd(); }

function resolveTargetDir(ai, mode, destOverride){
  if (destOverride) return destOverride;
  if (mode !== "project" && mode !== "global") die(`--mode must be 'project' or 'global'`);

  if (ai === "claude") {
    return mode === "project"
      ? path.join(projectRoot(), ".claude", "skills", "auto-coding-skill")
      : path.join(os.homedir(), ".claude", "skills", "auto-coding-skill");
  }

  if (ai === "codex") {
    return mode === "project"
      ? path.join(projectRoot(), ".agents", "skills", "auto-coding-skill")
      : path.join(os.homedir(), ".agents", "skills", "auto-coding-skill");
  }

  die(`unknown ai: ${ai}`);
}

function resolveAgentsDir(mode, destOverride, multiTarget){
  if (destOverride) {
    return multiTarget
      ? path.join(destOverride, "agents")
      : path.join(destOverride, ".agents", "agents");
  }
  if (mode !== "project" && mode !== "global") die(`--mode must be 'project' or 'global'`);
  return mode === "project"
    ? path.join(projectRoot(), ".agents", "agents")
    : path.join(os.homedir(), ".agents", "agents");
}

function main(){
  const args = parseArgs(process.argv);

  if (args.cmd === "help" || !args.cmd) {
    console.log(`
autocoding - install auto-coding-skill (Claude Code + Codex CLI)

Usage:
  autocoding init --ai claude|codex|all [--mode project|global] [--dest <path>] [--force]

Examples:
  autocoding init --ai claude
  autocoding init --ai codex
  autocoding init --ai all --mode project
  autocoding init --ai all --dest /tmp/skills
`);
    process.exit(0);
  }

  if (args.cmd !== "init") die(`unknown command: ${args.cmd}`);

  const ai = (args.ai ?? "").toLowerCase();
  const targets = ai === "all" ? ["claude", "codex"] : [ai];
  if (!(["claude", "codex", "all"].includes(ai))) die(`--ai must be claude|codex|all`);

  const here = path.dirname(fileURLToPath(import.meta.url));
  const assetSkill = path.resolve(here, "..", "assets", "skill");
  const assetAgents = path.resolve(here, "..", "assets", "agents");
  if (!exists(assetSkill)) die(`missing assets at ${assetSkill}`);
  if (!exists(assetAgents)) die(`missing assets at ${assetAgents}`);

  for (const t of targets) {
    const dstOverride = args.dest
      ? (targets.length > 1 ? path.join(args.dest, t) : args.dest)
      : null;
    const dst = resolveTargetDir(t, args.mode, dstOverride);
    if (exists(dst)) {
      if (!args.force) die(`target exists: ${dst}\nRe-run with --force to overwrite.`);
      rmrf(dst);
    }
    copyDir(assetSkill, dst);
    console.log(`[autocoding] installed skill to: ${dst}`);

    if (t === "codex") {
      const agentsDst = resolveAgentsDir(args.mode, args.dest, targets.length > 1);
      if (exists(agentsDst)) {
        if (!args.force) die(`target exists: ${agentsDst}\nRe-run with --force to overwrite.`);
        rmrf(agentsDst);
      }
      copyDir(assetAgents, agentsDst);
      console.log(`[autocoding] installed Codex agents to: ${agentsDst}`);
    }
  }

  console.log("[autocoding] done.");
}

main();
