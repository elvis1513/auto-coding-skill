import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(root, "cli", "src", "index.js");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "autocoding-docs-"));
const projectA = path.join(tmp, "a");
const projectB = path.join(tmp, "b");
fs.mkdirSync(projectA); fs.mkdirSync(projectB);

function run(args, cwd = root) {
  const result = spawnSync(process.execPath, [cli, ...args], { cwd, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout;
}

run(["init"], projectA);
for (const relative of [
  ".agents/skills/auto-coding-skill/SKILL.md",
  "AGENTS.md",
  "docs/ENVIRONMENT.md",
  "docs/PROJECT.md",
  "docs/architecture/.gitkeep",
  "docs/design/.gitkeep",
  "docs/interfaces/.gitkeep",
  "docs/deployment/.gitkeep",
  "docs/product/.gitkeep",
]) assert.ok(fs.existsSync(path.join(projectA, relative)), `missing ${relative}`);
assert.ok(!fs.existsSync(path.join(projectA, "docs/tools/autopipeline/ap.py")), "must not install a Gate runtime");
assert.ok(!fs.existsSync(path.join(projectA, ".agents/skills/auto-coding-skill/scripts/ap.py")), "must not install a Gate script");

const environment = path.join(projectA, "docs/ENVIRONMENT.md");
const projectConfig = path.join(projectA, "docs/PROJECT.md");
fs.writeFileSync(environment, "# Environment\n\nChanged managed text.\n");
fs.writeFileSync(projectConfig, "# Project Configuration\n\nProject-owned text.\n");
run(["init"], projectA);
assert.notEqual(fs.readFileSync(environment, "utf8"), "# Environment\n\nChanged managed text.\n", "init must refresh the managed environment document");
assert.equal(fs.readFileSync(projectConfig, "utf8"), "# Project Configuration\n\nProject-owned text.\n", "init must preserve project configuration");

const status = JSON.parse(run(["status", "--projects", projectA, "--json"]));
assert.equal(status.results[0].ok, true);
assert.equal(status.results[0].version, "5.0.3");

const legacyEnvironment = path.join(projectB, "docs/ENVIRONMENT.md");
fs.mkdirSync(path.dirname(legacyEnvironment), { recursive: true });
fs.writeFileSync(legacyEnvironment, "# Environment\n\nLegacy runtime detail.\n\n## Migrated access configuration\n```yaml\naccess:\n  password: \"\"\n```\n");

const legacyRuntime = path.join(projectB, "docs/tools/autopipeline/ap.py");
const legacyEngineering = path.join(projectB, "docs/ENGINEERING.md");
fs.mkdirSync(path.dirname(legacyRuntime), { recursive: true });
fs.writeFileSync(legacyRuntime, "legacy gate runtime\n");
fs.writeFileSync(legacyEngineering, "legacy managed gate policy\n");
fs.mkdirSync(path.join(projectB, ".agents"), { recursive: true });
fs.writeFileSync(path.join(projectB, ".agents/managed-install.json"), JSON.stringify({
  schema_version: 1,
  skill_version: "4.3.7",
  entries: [{
    path: "docs/tools/autopipeline/ap.py",
    sha256: crypto.createHash("sha256").update("legacy gate runtime\n").digest("hex"),
  }, {
    path: "docs/ENGINEERING.md",
    sha256: crypto.createHash("sha256").update("legacy managed gate policy\n").digest("hex"),
  }],
}));
run(["sync", "--projects", `${projectA},${projectB}`]);
assert.ok(fs.existsSync(path.join(projectB, "docs/ENVIRONMENT.md")));
assert.match(fs.readFileSync(path.join(projectB, "docs/PROJECT.md"), "utf8"), /Legacy runtime detail/, "legacy environment context must migrate to project configuration");
assert.doesNotMatch(fs.readFileSync(path.join(projectB, "docs/PROJECT.md"), "utf8"), /Migrated access configuration/, "legacy empty access configuration must not migrate to project configuration");
fs.appendFileSync(path.join(projectB, "docs/PROJECT.md"), "\n## Migrated access configuration\n```yaml\naccess:\n  password: \"\"\n```\n");
run(["init"], projectB);
assert.doesNotMatch(fs.readFileSync(path.join(projectB, "docs/PROJECT.md"), "utf8"), /Migrated access configuration/, "sync must clean the known legacy access block from existing project configuration");
fs.appendFileSync(path.join(projectB, "docs/PROJECT.md"), "\n| Host | Username | Password |\n| --- | --- | --- |\n| 192.168.20.10 | admin | local-value |\n");
run(["init"], projectB);
assert.doesNotMatch(fs.readFileSync(path.join(projectB, "docs/PROJECT.md"), "utf8"), /local-value/, "sync must remove legacy credential values from project configuration");
assert.ok(!fs.existsSync(legacyRuntime), "exact legacy Gate runtime must be retired during upgrade");
assert.ok(!fs.existsSync(legacyEngineering), "exact legacy Gate policy must be retired during upgrade");
assert.ok(fs.existsSync(path.join(projectB, ".agents/archive/auto-coding-skill/4.3.7/docs/ENGINEERING.md")), "legacy policy must remain in archive");
assert.match(run(["--help"]), /do not run or require Gates/i);
fs.rmSync(tmp, { recursive: true, force: true });
console.log("documentation-only CLI tests passed");
