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
  fs.unlinkSync(path.join(a, "docs/design/.gitkeep"));
  fs.rmdirSync(path.join(a, "docs/design"));
  run(["init"], a);
  assert.ok(!present(a, "docs/design"), "upgrades must not recreate retired project-owned scaffolding");

  // Doctor distinguishes informational project overlays from managed integrity.
  // A primary checkout or a clone that never opted in is not a failed install.
  const audit = project("diagnostics");
  run(["init"], audit);
  write(audit, ".agents/agents/custom.toml", 'model = "project-choice"\nmodel_reasoning_effort = "custom"\n');
  const entry = "synthetic-sensitive-text";
  write(audit, "docs/PROJECT.md", entry);
  const auditBefore = read(audit, manifestPath);
  const report = run(["doctor", "--projects", audit, "--json"]);
  assert.ok(!report.includes(entry) && !report.includes("project-choice"));
  const findings = JSON.parse(report).results[0];
  assert.equal(findings.guard.status, "not-configured");
  assert.deepEqual([findings.ok, findings.managed.current, findings.context.legacy_profiles[0].pins_model], [true, true, true]);
  assert.equal(read(audit, manifestPath), auditBefore);
  assert.equal(read(audit, "docs/PROJECT.md"), entry);
  fs.appendFileSync(path.join(audit, "AGENTS.md"), "\nlocal rule\n");
  const drift = JSON.parse(run(["doctor", "--projects", audit, "--json"], root, 1)).results[0];
  assert.equal(drift.context.outside_managed_bridge, true);
  assert.equal(drift.managed.integrity, false);
  run(["guard-sync", "--dest", audit], root, 1);
  assert.ok(!present(audit, "config/git-workflow"));
  write(audit, "config/git-workflow/guard.py", "downstream changes\n");
  write(audit, "config/git-workflow/test_guard.py", "downstream tests\n");
  run(["guard-sync", "--dest", audit, "--dry-run"], root, 1);
  run(["guard-sync", "--dest", audit], root, 1);
  assert.equal(read(audit, "config/git-workflow/guard.py"), "downstream changes\n");

  // Project-owned content is byte-for-byte preserved, even under legacy headings.
  const projectText = "# Project\n\n## Migrated access configuration\n```yaml\naccess:\n  password: synthetic-value\n```\n\nProject-owned text.\n";
  write(a, "docs/PROJECT.md", projectText);
  write(a, "docs/design/custom.md", "durable design\n");
  write(a, "docs/ENVIRONMENT.md", "changed managed text\n");
  assert.equal(status(a, 1).integrity, false);
  const beforeBlocked = read(a, manifestPath);
  const blocked = JSON.parse(run(["init", "--json"], a, 1));
  assert.deepEqual(blocked.results[0].conflicts.map(entry => entry.path), ["docs/ENVIRONMENT.md"]);
  assert.equal(read(a, "docs/ENVIRONMENT.md"), "changed managed text\n");
  assert.equal(read(a, manifestPath), beforeBlocked, "blocked replacement must not alter the manifest");
  const replaced = JSON.parse(run(["init", "--replace-managed", "--backup-dir", path.join(tmp, "backups"), "--json"], a));
  const backup = JSON.parse(read(replaced.backup, "backup.json"));
  assert.equal(read(replaced.backup, backup.files[0].backup_path), "changed managed text\n");
  assert.equal(fs.statSync(replaced.backup).mode & 0o777, 0o700);
  assert.equal(fs.statSync(path.join(replaced.backup, backup.files[0].backup_path)).mode & 0o777, 0o600);
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
  run(["init"], a, 1);
  assert.equal(read(a, `${skillPath}/scripts/old.py`), "obsolete runtime\n");
  const repaired = JSON.parse(run(["init", "--replace-managed", "--backup-dir", path.join(tmp, "backups"), "--json"], a));
  assert.deepEqual(repaired.legacy_files, [".agents/agents/old-reviewer.toml"]);
  assert.ok(present(a, ".agents/agents/custom.toml"));
  assert.ok(present(a, ".agents/agents/old-reviewer.toml"), "unowned legacy candidates require review, not deletion");

  // Dry-run is read-only; custom AGENTS/environment/skill files are never silently lost.
  const guarded = project("guarded");
  const dry = JSON.parse(run(["init", "--dest", guarded, "--dry-run", "--json"]));
  assert.equal(dry.can_apply, true);
  assert.deepEqual(fs.readdirSync(guarded), [], "fresh dry-run must not create directories");
  run(["init"], guarded);
  const ownedProject = read(guarded, "docs/PROJECT.md");
  const custom = {
    "AGENTS.md": `${read(guarded, "AGENTS.md")}\nproject-only-no-device-dispatch\n`,
    "docs/ENVIRONMENT.md": "private-fixture-password-do-not-print\n",
    [`${skillPath}/SKILL.md`]: "project-custom-skill\n",
    [`${skillPath}/local-notes.md`]: "unowned-local-detail\n",
  };
  for (const [relative, content] of Object.entries(custom)) write(guarded, relative, content);
  const previewText = run(["init", "--dry-run", "--json"], guarded, 1);
  assert.ok(!previewText.includes("private-fixture-password"), "previews must not expose file contents");
  assert.equal(JSON.parse(previewText).results[0].conflicts.length, 4);
  run(["init", "--replace-managed"], guarded, 1);
  run(["init", "--backup-dir", path.join(tmp, "backups")], guarded, 1);
  run(["init", "--replace-managed", "--backup-dir", path.join(guarded, ".local/backup")], guarded, 1);
  const alias = path.join(tmp, "guarded-alias");
  fs.symlinkSync(guarded, alias);
  run(["init", "--replace-managed", "--backup-dir", path.join(alias, "nested/backup")], guarded, 1);
  for (const [relative, content] of Object.entries(custom)) assert.equal(read(guarded, relative), content);

  // A conflict in the last project must not partially refresh an earlier project.
  const batchFirst = project("batch-first");
  run(["sync", "--projects", `${batchFirst},${guarded}`, "--json"], root, 1);
  assert.deepEqual(fs.readdirSync(batchFirst), []);
  const noWriteBackup = path.join(tmp, "dry-backup");
  run(["init", "--replace-managed", "--backup-dir", noWriteBackup, "--dry-run", "--json"], guarded);
  assert.ok(!fs.existsSync(noWriteBackup));
  const done = JSON.parse(run(["sync", "--projects", `${batchFirst},${guarded}`, "--replace-managed", "--backup-dir", path.join(tmp, "backups"), "--json"]));
  const protectedFiles = JSON.parse(read(done.results[1].backup, "backup.json"));
  assert.equal(protectedFiles.files.length, 4);
  for (const entry of protectedFiles.files) assert.equal(read(done.results[1].backup, entry.backup_path), custom[entry.path]);
  assert.equal(read(guarded, "docs/PROJECT.md"), ownedProject);
  assert.equal(status(guarded).ok, true);
  assert.equal(status(batchFirst).ok, true);

  // Existing unowned guidance needs review, including when a project document already exists.
  const unowned = project("unowned");
  write(unowned, "AGENTS.md", "owner-authored instructions\n");
  write(unowned, "docs/PROJECT.md", "existing project\n");
  write(unowned, "docs/ENVIRONMENT.md", "owner-authored endpoint\n");
  run(["init"], unowned, 1);
  assert.equal(read(unowned, "AGENTS.md"), "owner-authored instructions\n");
  assert.ok(!present(unowned, manifestPath));

  // Symlinked extra content cannot be read, copied, or deleted as part of replacement.
  const nestedLink = project("nested-link");
  run(["init"], nestedLink);
  fs.symlinkSync(path.join(tmp, "backups"), path.join(nestedLink, skillPath, "external"));
  run(["init", "--replace-managed", "--backup-dir", path.join(tmp, "backups")], nestedLink, 1);
  assert.ok(fs.lstatSync(path.join(nestedLink, skillPath, "external")).isSymbolicLink());

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
  console.log("CLI regressions passed: install, conflict preflight, private backups, batch protection, dry-run, preservation, freshness, legacy migration, unsafe paths, source discovery");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
