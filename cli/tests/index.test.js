import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(repoRoot, "cli", "src", "index.js");
const assetAp = path.join(repoRoot, "cli", "assets", "skill", "scripts", "ap.py");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function exists(p) {
  return fs.existsSync(p);
}

function tmpdir(name) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `autocoding-${name}.`));
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? repoRoot,
    encoding: "utf8",
    stdio: "pipe",
  });
  if (options.check !== false && result.status !== 0) {
    throw new Error([
      `command failed: ${command} ${args.join(" ")}`,
      `cwd=${options.cwd ?? repoRoot}`,
      `status=${result.status}`,
      result.stdout,
      result.stderr,
    ].join("\n"));
  }
  return result;
}

function writeFile(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
}

function assertStatusOk(repo) {
  const result = run("node", [cli, "status", "--projects", repo, "--json"]);
  const parsed = JSON.parse(result.stdout);
  assert(parsed.results[0].ok === true, `status should be ok: ${result.stdout}`);
}

function testPreflightAvoidsPartialInstall() {
  const repo = tmpdir("partial-init");
  writeFile(path.join(repo, ".agents", "agents", "custom.toml"), 'name = "custom"\n');
  const result = run("node", [cli, "init"], { cwd: repo, check: false });
  assert(result.status !== 0, "init should fail when agents target exists without --force");
  assert(!exists(path.join(repo, ".agents", "skills", "auto-coding-skill")), "failed init must not leave a partial skill copy");
  assert(exists(path.join(repo, ".agents", "agents", "custom.toml")), "existing custom agent should remain");
}

function testDestVariants() {
  const variants = [
    {
      name: "repo-root",
      dest(root) { return root; },
    },
    {
      name: "agents-root",
      dest(root) { return path.join(root, ".agents"); },
    },
    {
      name: "skills-dir",
      dest(root) { return path.join(root, ".agents", "skills"); },
    },
    {
      name: "agents-dir",
      dest(root) { return path.join(root, ".agents", "agents"); },
    },
    {
      name: "direct-skill",
      dest(root) { return path.join(root, ".agents", "skills", "auto-coding-skill"); },
    },
  ];

  for (const variant of variants) {
    const root = tmpdir(`dest-${variant.name}`);
    const dest = variant.dest(root);
    fs.mkdirSync(dest, { recursive: true });
    run("node", [cli, "init", "--dest", dest, "--force"]);
    assert(exists(path.join(root, ".agents", "skills", "auto-coding-skill", "SKILL.md")), `${variant.name}: missing skill`);
    assert(exists(path.join(root, ".agents", "agents", "explorer.toml")), `${variant.name}: missing agent`);
    assert(!exists(path.join(root, ".agents", ".agents")), `${variant.name}: nested .agents should not be created`);
  }
}

function testSyncCreatesScaffoldAndStatusConverges() {
  const repo = tmpdir("sync-converges");
  run("node", [cli, "init"], { cwd: repo });
  const before = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(before.status !== 0, "status should fail before docs/tooling scaffold exists");
  assert(before.stdout.includes("autocoding sync"), "status should point to sync for missing scaffold");
  run("node", [cli, "sync", "--projects", repo]);
  assert(exists(path.join(repo, "docs", "ENGINEERING.md")), "sync should create docs/ENGINEERING.md when missing");
  assertStatusOk(repo);
}

function testForcePreservesCustomAgents() {
  const repo = tmpdir("custom-agent");
  run("node", [cli, "init", "--force"], { cwd: repo });
  const custom = path.join(repo, ".agents", "agents", "custom-local.toml");
  writeFile(custom, 'name = "custom-local"\ndescription = "custom"\nmodel = "gpt-5.5"\n');
  run("node", [cli, "init", "--force"], { cwd: repo });
  assert(exists(custom), "custom agent should be preserved");
}

function testBridgeIsGeneric() {
  const repo = tmpdir("bridge");
  run("node", [cli, "init", "--force"], { cwd: repo });
  const ap = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  run("python3", [ap, "--repo", repo, "install", "--bridges"]);
  assert(exists(path.join(repo, "AGENTS.md")), "generic bridge should be created");
  for (const filename of [`CO${"DEX.md"}`, `CLA${"UDE.md"}`]) {
    assert(!exists(path.join(repo, filename)), "client-named bridge should not be created");
  }
}

function testUpgradeCleansManagedBridgeExtrasOnly() {
  const repo = tmpdir("upgrade-extra");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "data", "templates", "bridges", "OLD.md"), "old\n");
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "custom.txt"), "custom\n");
  run("python3", [assetAp, "--repo", repo, "upgrade", "--write"]);
  assert(!exists(path.join(repo, ".agents", "skills", "auto-coding-skill", "data", "templates", "bridges", "OLD.md")), "managed bridge extra should be removed");
  assert(exists(path.join(repo, ".agents", "skills", "auto-coding-skill", "custom.txt")), "non-managed extra should remain");
}

testPreflightAvoidsPartialInstall();
testDestVariants();
testSyncCreatesScaffoldAndStatusConverges();
testForcePreservesCustomAgents();
testBridgeIsGeneric();
testUpgradeCleansManagedBridgeExtrasOnly();

console.log("cli-installer-regression-ok");
