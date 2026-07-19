import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const source = path.join(root, "src", "auto-coding-skill");
const destination = path.join(root, "cli", "assets", "skill");
const manifestFile = path.join(root, "cli", "assets", "managed-install.json");
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const checkOnly = process.argv.includes("--check");

function listFiles(directory, base = directory) {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === ".DS_Store" || entry.name === "__pycache__") continue;
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...listFiles(file, base));
    else files.push(path.relative(base, file).split(path.sep).join("/"));
  }
  return files.sort();
}
function hash(file) { return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex"); }
function copyTree(from, to) {
  for (const relative of listFiles(from)) {
    const target = path.join(to, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(from, relative), target);
  }
}
function manifestFor(directory) {
  return {
    schema_version: 2,
    skill_version: packageJson.version,
    asset_files: listFiles(directory).map(relative => ({ path: relative, sha256: hash(path.join(directory, relative)) })),
  };
}
function expected() { return `${JSON.stringify(manifestFor(source), null, 2)}\n`; }

if (checkOnly) {
  const sourceFiles = listFiles(source);
  const destinationFiles = fs.existsSync(destination) ? listFiles(destination) : [];
  const equal = sourceFiles.length === destinationFiles.length && sourceFiles.every((file, index) => file === destinationFiles[index] && fs.readFileSync(path.join(source, file)).equals(fs.readFileSync(path.join(destination, file))));
  if (!equal || !fs.existsSync(manifestFile) || fs.readFileSync(manifestFile, "utf8") !== expected()) {
    console.error("[sync-assets] assets are out of sync; run npm run sync-assets");
    process.exit(1);
  }
  console.log("[sync-assets] OK");
} else {
  fs.rmSync(destination, { recursive: true, force: true });
  copyTree(source, destination);
  fs.writeFileSync(manifestFile, expected());
  console.log("[sync-assets] updated documentation assets");
}
