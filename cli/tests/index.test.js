import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(root, "cli/src/index.js");
const version = JSON.parse(fs.readFileSync(path.join(root, "package.json"))).version;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "autocoding-docs-"));
const manifestPath = ".agents/managed-install.json";
const skillPath = ".agents/skills/auto-coding-skill";
const hash = text => crypto.createHash("sha256").update(text).digest("hex");
const read = (project, relative) => fs.readFileSync(path.join(project, relative), "utf8");
const present = (project, relative) => fs.existsSync(path.join(project, relative));
function write(project, relative, content) {
  const file = path.join(project, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}
function project(name) {
  const directory = path.join(tmp, name);
  fs.mkdirSync(directory);
  return directory;
}
function run(args, cwd = root, exitCode = 0) {
  const result = spawnSync(process.execPath, [cli, ...args], { cwd, encoding: "utf8" });
  assert.equal(result.status, exitCode, result.stderr || result.stdout);
  return result.stdout;
}
function status(directory, exitCode = 0) {
  return JSON.parse(run(["status", "--projects", directory, "--json"], root, exitCode)).results[0];
}
function manifest(directory, change) {
  const value = JSON.parse(read(directory, manifestPath));
  change(value);
  write(directory, manifestPath, JSON.stringify(value));
}

try {
  const a = project("current");
  run(["init"], a);
  for (const relative of [
    `${skillPath}/SKILL.md`, "AGENTS.md", "docs/ENVIRONMENT.md", "docs/PROJECT.md",
    "docs/architecture/.gitkeep", "docs/design/.gitkeep", "docs/interfaces/.gitkeep",
    "docs/deployment/.gitkeep", "docs/product/.gitkeep",
  ]) assert.ok(present(a, relative), `missing ${relative}`);
  assert.ok(!present(a, "docs/tools/autopipeline/ap.py"));
  assert.ok(!present(a, `${skillPath}/scripts/ap.py`));
  assert.ok(!present(a, ".agents/agents"), "must not install fixed agent profiles");
  assert.deepEqual([status(a).integrity, status(a).current, status(a).version], [true, true, version]);

  // Project-owned content is byte-for-byte preserved, even under legacy headings.
  const projectText = "# Project\n\n## Migrated access configuration\n```yaml\naccess:\n  password: synthetic-value\n```\n\nProject-owned text.\n";
  write(a, "docs/PROJECT.md", projectText);
  write(a, "docs/design/custom.md", "durable design\n");
  write(a, "docs/ENVIRONMENT.md", "changed managed text\n");
  assert.equal(status(a, 1).integrity, false);
  run(["init"], a);
  assert.notEqual(read(a, "docs/ENVIRONMENT.md"), "changed managed text\n");
  assert.equal(read(a, "docs/PROJECT.md"), projectText);
  assert.equal(read(a, "docs/design/custom.md"), "durable design\n");

  // An intact older install is not a current install.
  manifest(a, value => { value.skill_version = "5.0.4"; });
  assert.equal(status(a, 1).integrity, true);
  assert.equal(status(a, 1).current, false);
  run(["init"], a);

  // A self-consistent manifest cannot hide stale content, even at the same version.
  write(a, "AGENTS.md", "old instructions\n");
  manifest(a, value => { value.entries.find(entry => entry.path === "AGENTS.md").sha256 = hash("old instructions\n"); });
  assert.equal(status(a, 1).integrity, true);
  assert.equal(status(a, 1).current, false);
  run(["init"], a);
  manifest(a, value => { value.entries = value.entries.filter(entry => entry.path !== "AGENTS.md"); });
  assert.equal(status(a, 1).current, false, "must compare the expected asset set, not just recorded entries");
  run(["init"], a);

  for (const broken of ["not json", "null", '{"entries":[]}', '{"entries":[null]}']) {
    write(a, manifestPath, broken);
    assert.equal(status(a, 1).integrity, false);
    run(["init"], a);
  }
  manifest(a, value => { value.entries.push(value.entries[0]); });
  assert.equal(status(a, 1).integrity, false);
  run(["init"], a);

  write(a, `${skillPath}/scripts/old.py`, "obsolete runtime\n");
  write(a, ".agents/agents/old-reviewer.toml", 'instructions = "ap.py classify --scope auto"\n');
  write(a, ".agents/agents/custom.toml", 'instructions = "Review the requested change"\n');
  const stale = status(a, 1);
  assert.deepEqual(stale.unexpected_files, [`${skillPath}/scripts/old.py`]);
  assert.deepEqual(stale.legacy_files, [".agents/agents/old-reviewer.toml"]);
  const repaired = JSON.parse(run(["init", "--json"], a));
  assert.deepEqual(repaired.legacy_files, [".agents/agents/old-reviewer.toml"]);
  assert.ok(present(a, ".agents/agents/custom.toml"));
  assert.ok(present(a, ".agents/agents/old-reviewer.toml"), "unowned legacy candidates require review, not deletion");

  // Exact legacy files retire, with policy archived; legacy context migrates intact.
  const b = project("legacy");
  const legacyText = "# Environment\n\nLegacy runtime detail.\n\n## Migrated access configuration\n```yaml\naccess:\n  password: synthetic-value\n```\n";
  write(b, "docs/ENVIRONMENT.md", legacyText);
  const oldFiles = {
    "docs/tools/autopipeline/ap.py": "legacy runtime\n",
    "docs/ENGINEERING.md": "legacy policy\n",
    ".agents/agents/explorer.toml": 'instructions = "ap.py classify"\n',
  };
  for (const [relative, text] of Object.entries(oldFiles)) write(b, relative, text);
  write(b, manifestPath, JSON.stringify({
    schema_version: 1, skill_version: "4.3.7",
    entries: Object.entries(oldFiles).map(([relative, text]) => ({ path: relative, sha256: hash(text) })),
  }));
  run(["sync", "--projects", `${a},${b}`]);
  assert.equal(read(a, "docs/PROJECT.md"), projectText);
  assert.ok(read(b, "docs/PROJECT.md").includes(legacyText), "migration must preserve all original context");
  for (const relative of Object.keys(oldFiles)) assert.ok(!present(b, relative));
  assert.equal(read(b, ".agents/archive/auto-coding-skill/4.3.7/docs/ENGINEERING.md"), oldFiles["docs/ENGINEERING.md"]);
  assert.equal(status(b).ok, true);

  // Modified legacy files survive and remain visible across repeated upgrades.
  const c = project("modified-legacy");
  write(c, "docs/ENGINEERING.md", "project-owned additions\n");
  write(c, manifestPath, JSON.stringify({ schema_version: 1, skill_version: "4.3.7", entries: [
    { path: "docs/ENGINEERING.md", sha256: hash("original policy\n") },
  ] }));
  for (let attempt = 0; attempt < 2; attempt += 1) {
    run(["init"], c);
    assert.equal(read(c, "docs/ENGINEERING.md"), "project-owned additions\n");
    assert.deepEqual(status(c, 1).legacy_files, ["docs/ENGINEERING.md"]);
  }

  // Malformed manifests must never retire a path outside their project.
  const d = project("unsafe-manifest");
  write(tmp, "sentinel", "keep\n");
  write(d, manifestPath, JSON.stringify({ schema_version: 1, skill_version: "4.3.7", entries: [
    { path: ".agents/agents/../../../sentinel", sha256: hash("keep\n") },
  ] }));
  assert.equal(status(d, 1).integrity, false);
  run(["init"], d);
  assert.equal(read(tmp, "sentinel"), "keep\n");

  const e = project("symlink-target");
  fs.mkdirSync(path.join(e, "docs"));
  fs.symlinkSync(path.join(tmp, "sentinel"), path.join(e, "docs/PROJECT.md"));
  run(["init"], e, 1);
  assert.equal(read(tmp, "sentinel"), "keep\n");
  assert.ok(!present(e, "AGENTS.md"), "preflight must reject unsafe paths before installing anything");
  // Even a read-only status reports symlinked managed content as unsafe.
  fs.rmSync(path.join(b, "AGENTS.md"));
  fs.symlinkSync(path.join(tmp, "sentinel"), path.join(b, "AGENTS.md"));
  assert.equal(status(b, 1).integrity, false);

  // Source status detects stale discovery copies and stale packaged metadata.
  const sourceCopy = project("source-copy");
  write(sourceCopy, "cli/src/index.js", "// source repository fixture\n");
  write(sourceCopy, "package.json", JSON.stringify({ version }));
  fs.cpSync(path.join(root, "src"), path.join(sourceCopy, "src"), { recursive: true });
  fs.cpSync(path.join(root, "cli/assets"), path.join(sourceCopy, "cli/assets"), { recursive: true });
  fs.mkdirSync(path.join(sourceCopy, ".agents/skills"), { recursive: true });
  fs.symlinkSync("../../src/auto-coding-skill", path.join(sourceCopy, skillPath));
  assert.equal(status(sourceCopy).ok, true);
  const sourceManifest = read(sourceCopy, "cli/assets/managed-install.json");
  write(sourceCopy, "cli/assets/managed-install.json", sourceManifest.replace(version, "0.0.0"));
  assert.equal(status(sourceCopy, 1).ok, false);
  write(sourceCopy, "cli/assets/managed-install.json", sourceManifest);
  fs.unlinkSync(path.join(sourceCopy, skillPath));
  fs.cpSync(path.join(sourceCopy, "src/auto-coding-skill"), path.join(sourceCopy, skillPath), { recursive: true });
  assert.equal(status(sourceCopy, 1).ok, false, "a separate discovery copy must not silently diverge");

  const before = read(root, "AGENTS.md");
  run(["init", "--dest", root], root, 1);
  run(["sync", "--projects", root], root, 1);
  assert.equal(read(root, "AGENTS.md"), before, "source instructions must not be replaced by installed project guidance");
  const ownStatus = status(root);
  assert.equal(ownStatus.mode, "source");
  assert.equal(ownStatus.ok, true);
  run(["--help"]);
  console.log("CLI regressions passed: install, preservation, freshness, legacy migration, unsafe paths, source discovery");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
