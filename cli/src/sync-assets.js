import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const srcSkill = path.join(repoRoot, "src", "auto-coding-skill");
const dstSkill = path.join(repoRoot, "cli", "assets", "skill");
const srcAgents = path.join(repoRoot, "src", "agents");
const dstAgents = path.join(repoRoot, "cli", "assets", "agents");
const checkOnly = process.argv.includes("--check");

function exists(p){ try { fs.accessSync(p); return true; } catch { return false; } }
function rmrf(p){ fs.rmSync(p, { recursive:true, force:true }); }
function shouldSkip(name){
  return name === "__pycache__" || name === ".DS_Store" || name.endsWith(".pyc");
}
function copyDir(src, dst){
  fs.mkdirSync(dst, { recursive:true });
  for (const ent of fs.readdirSync(src, { withFileTypes:true })) {
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
  for (const ent of fs.readdirSync(root, { withFileTypes:true })) {
    if (shouldSkip(ent.name)) continue;
    const p = path.join(root, ent.name);
    if (ent.isDirectory()) out.push(...listFiles(p, base));
    else out.push(path.relative(base, p));
  }
  return out.sort();
}

function compareDirs(src, dst, label){
  const diffs = [];
  const srcFiles = listFiles(src);
  const dstFiles = listFiles(dst);
  const srcSet = new Set(srcFiles);
  const dstSet = new Set(dstFiles);

  for (const rel of srcFiles) {
    if (!dstSet.has(rel)) {
      diffs.push(`${label}: missing asset ${rel}`);
      continue;
    }
    const srcBuf = fs.readFileSync(path.join(src, rel));
    const dstBuf = fs.readFileSync(path.join(dst, rel));
    if (!srcBuf.equals(dstBuf)) diffs.push(`${label}: stale asset ${rel}`);
  }
  for (const rel of dstFiles) {
    if (!srcSet.has(rel)) diffs.push(`${label}: extra asset ${rel}`);
  }
  return diffs;
}

if (checkOnly) {
  const diffs = [
    ...compareDirs(srcSkill, dstSkill, "skill"),
    ...compareDirs(srcAgents, dstAgents, "agents"),
  ];
  if (diffs.length > 0) {
    console.error("[sync-assets] assets are out of sync:");
    for (const diff of diffs) console.error(`- ${diff}`);
    console.error("[sync-assets] run: npm run sync-assets");
    process.exit(1);
  }
  console.log("[sync-assets] OK: cli assets match src");
  process.exit(0);
}

rmrf(dstSkill);
copyDir(srcSkill, dstSkill);
rmrf(dstAgents);
copyDir(srcAgents, dstAgents);
console.log("[sync-assets] updated cli/assets/skill from src/auto-coding-skill");
console.log("[sync-assets] updated cli/assets/agents from src/agents");
