import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const srcSkill = path.join(repoRoot, "src", "auto-coding-skill");
const dstSkill = path.join(repoRoot, "cli", "assets", "skill");

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

rmrf(dstSkill);
copyDir(srcSkill, dstSkill);
console.log("[sync-assets] updated cli/assets/skill from src/auto-coding-skill");
