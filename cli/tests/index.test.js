import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(repoRoot, "cli", "src", "index.js");
const assetAp = path.join(repoRoot, "cli", "assets", "skill", "scripts", "ap.py");
const managedAgentEfforts = {
  "browser-debugger.toml": "xhigh",
  "docs-researcher.toml": "medium",
  "explorer.toml": "medium",
  "fixer.toml": "medium",
  "reviewer.toml": "xhigh",
};

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
    env: options.env ? { ...process.env, ...options.env } : process.env,
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

function pythonEnvWithHome(home) {
  const yamlSite = run(
    "python3",
    ["-c", "import pathlib, yaml; print(pathlib.Path(yaml.__file__).resolve().parent.parent)"],
  ).stdout.trim();
  return {
    HOME: home,
    PYTHONPATH: [yamlSite, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };
}

function writeFile(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
}

function readTomlString(text, key, file) {
  const match = text.match(new RegExp(`^${key}\\s*=\\s*"([^"]+)"\\s*$`, "m"));
  assert(match, `${file}: missing ${key}`);
  return match[1];
}

function managedAgentHeader(text) {
  return text.split(/^developer_instructions\s*=\s*(?:"""|''')/m, 1)[0];
}

function assertManagedAgents(agentsDir, expectedModel = null) {
  for (const [filename, effort] of Object.entries(managedAgentEfforts)) {
    const file = path.join(agentsDir, filename);
    assert(exists(file), `missing managed agent: ${filename}`);
    const text = fs.readFileSync(file, "utf8");
    assert(readTomlString(text, "model_reasoning_effort", file) === effort, `${filename}: unexpected effort`);
    const model = managedAgentHeader(text).match(/^model\s*=\s*"([^"]+)"\s*$/m)?.[1] ?? null;
    assert(model === expectedModel, `${filename}: expected model ${expectedModel ?? "inherit"}, got ${model}`);
  }
}

function listProjectFiles(root) {
  const out = [];
  function walk(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name === ".git" || entry.name === "__pycache__" || entry.name.endsWith(".pyc")) continue;
      const file = path.join(current, entry.name);
      if (entry.isDirectory()) walk(file);
      else out.push(file);
    }
  }
  walk(root);
  return out;
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
    { name: "repo-root", dest(root) { return root; } },
    { name: "agents-root", dest(root) { return path.join(root, ".agents"); } },
    { name: "skills-dir", dest(root) { return path.join(root, ".agents", "skills"); } },
    { name: "agents-dir", dest(root) { return path.join(root, ".agents", "agents"); } },
    { name: "direct-skill", dest(root) { return path.join(root, ".agents", "skills", "auto-coding-skill"); } },
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

function testLauncherFallsBackToGlobalRuntime() {
  const fakeHome = tmpdir("global-runtime-home");
  const project = tmpdir("global-runtime-project");
  const env = pythonEnvWithHome(fakeHome);
  run("node", [cli, "init", "--mode", "global", "--dest", fakeHome, "--force"]);
  const globalAp = path.join(fakeHome, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  run("python3", [globalAp, "--repo", project, "install"], { env });
  assert(!exists(path.join(project, ".agents", "skills", "auto-coding-skill")), "fixture should rely on the global runtime only");
  const launcher = path.join(project, "docs", "tools", "autopipeline", "ap.py");
  const help = run("python3", [launcher, "--help"], { env });
  assert(help.stdout.includes("autopipeline"), "project launcher should execute the global runtime when no project copy exists");
}

function testMinimalSyncConvergesWithinBudget() {
  const repo = tmpdir("minimal-sync");
  run("node", [cli, "init"], { cwd: repo });
  const before = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(before.status !== 0, "status should fail before core scaffold exists");
  run("node", [cli, "sync", "--projects", repo]);

  for (const rel of ["docs/ENGINEERING.md", "docs/tasks/taskbook.md", "docs/tasks/closure-log.md", "docs/tools/autopipeline/ap.py"]) {
    assert(exists(path.join(repo, rel)), `missing core scaffold file: ${rel}`);
  }
  for (const rel of ["docs/interfaces/api.md", "docs/design/_TEMPLATE-DD.md", "docs/testing/regression-matrix.md", "docs/tools/autopipeline/core.py", "docs/tools/autopipeline/http_checks.py"]) {
    assert(!exists(path.join(repo, rel)), `optional/duplicate file should not be installed: ${rel}`);
  }

  const files = listProjectFiles(repo);
  const lines = files.reduce((total, file) => total + fs.readFileSync(file, "utf8").split(/\r?\n/).length, 0);
  assert(files.length <= 20, `minimal scaffold file budget exceeded: ${files.length}`);
  assert(lines <= 8200, `minimal scaffold line budget exceeded: ${lines}`);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes("profile: \"auto\""), "engineering should enable adaptive profiles");
  assert(engineering.includes("isolation: \"worktree\""), "engineering should require task worktree isolation");
  assert(engineering.includes("target_env_required: false"), "target verification should be opt-in in generic scaffold");
  assert(engineering.includes(`name: "${path.basename(repo)}"`), "project name should be initialized automatically");
  assertStatusOk(repo);

  const doctor = run("python3", [path.join(repo, "docs", "tools", "autopipeline", "ap.py"), "--repo", repo, "doctor"], { check: false });
  const doctorOutput = `${doctor.stdout}\n${doctor.stderr}`;
  assert(doctor.status !== 0 && doctorOutput.includes("gate command"), "empty generic repo should require only a real gate command");
  for (const unexpected of ["target_env.name", "backend_root", "jenkins.base_url", "docs.api_doc"]) {
    assert(!doctorOutput.includes(unexpected), `default doctor should not require optional field: ${unexpected}`);
  }
}

function testOrdinaryNodeTestIsNotPromotedToFullGate() {
  const repo = tmpdir("node-gate-inference");
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes('gate_changed: "npm test"'), "ordinary test should seed the changed gate");
  assert(engineering.includes('gate_standard: "npm test"'), "ordinary test should seed the standard gate");
  assert(engineering.includes('gate_full: ""'), "ordinary test must not be promoted to the full gate");

  run("git", ["init", "-q"], { cwd: repo });
  run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
  run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
  run("git", ["add", "-A"], { cwd: repo });
  run("git", ["commit", "-qm", "baseline"], { cwd: repo });
  writeFile(path.join(repo, "migrations", "001.sql"), "-- migration\n");
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  const doctor = run("python3", [launcher, "--repo", repo, "doctor"], { check: false });
  assert(doctor.status !== 0 && `${doctor.stdout}\n${doctor.stderr}`.includes("full gate command"), "high-risk work should block until a dedicated full gate is configured");
}

function testManagedAgentModelsInheritAndOverridesSurvive() {
  const repo = tmpdir("agent-models");
  run("node", [cli, "init"], { cwd: repo });
  const agentsDir = path.join(repo, ".agents", "agents");
  assertManagedAgents(agentsDir);

  const custom = path.join(agentsDir, "custom-local.toml");
  const customText = 'name = "custom-local"\ndescription = "custom"\nmodel = "vendor/custom"\n';
  writeFile(custom, customText);
  for (const filename of Object.keys(managedAgentEfforts)) {
    const file = path.join(agentsDir, filename);
    const stale = fs.readFileSync(file, "utf8")
      .replace(/^description\s*=.*$/m, '$&\nmodel = "vendor/project-model"')
      .replace(/^model_reasoning_effort\s*=.*$/m, 'model_reasoning_effort = "low"');
    writeFile(file, stale);
  }

  run("node", [cli, "sync", "--projects", repo]);
  assertManagedAgents(agentsDir, "vendor/project-model");
  assert(fs.readFileSync(custom, "utf8") === customText, "sync should preserve custom agent contents");
  assertStatusOk(repo);

  run("node", [cli, "sync", "--projects", repo, "--reset-agent-models"]);
  assertManagedAgents(agentsDir);
  assert(fs.readFileSync(custom, "utf8") === customText, "model reset must not touch custom agents");
}

function testForcePreservesCustomAgentsAndModelOverrides() {
  const repo = tmpdir("force-agent");
  run("node", [cli, "init", "--force"], { cwd: repo });
  const agentsDir = path.join(repo, ".agents", "agents");
  const custom = path.join(agentsDir, "custom-local.toml");
  const customText = 'name = "custom-local"\ndescription = "custom"\n';
  writeFile(custom, customText);
  const explorer = path.join(agentsDir, "explorer.toml");
  writeFile(explorer, fs.readFileSync(explorer, "utf8").replace(/^description\s*=.*$/m, '$&\nmodel = "vendor/override"'));
  run("node", [cli, "init", "--force"], { cwd: repo });
  assert(fs.readFileSync(custom, "utf8") === customText, "init --force should preserve custom agents");
  assert(fs.readFileSync(explorer, "utf8").includes('model = "vendor/override"'), "init --force should preserve explicit managed-agent model overrides");
}

function testInvalidManagedAgentModelsFailStatusAndAreDroppedOnSync() {
  const repo = tmpdir("invalid-agent-model");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const explorer = path.join(repo, ".agents", "agents", "explorer.toml");

  for (const invalidLine of ["model = [", 'model = ""']) {
    const canonical = fs.readFileSync(explorer, "utf8").replace(/^model\s*=.*(?:\r?\n|$)/m, "");
    writeFile(explorer, canonical.replace(/^description\s*=.*$/m, `$&\n${invalidLine}`));

    const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
    assert(status.status !== 0, `status should fail for invalid managed model: ${invalidLine}`);
    const parsed = JSON.parse(status.stdout).results[0];
    const finding = parsed.agentDiffs.find(item => item.path === "explorer.toml");
    assert(finding?.status === "invalid-model", `status should report invalid-model: ${status.stdout}`);
    assert(finding.detail?.includes("model"), `invalid model should include a useful detail: ${status.stdout}`);
    assert(parsed.agentBindings.find(item => item.agent === "explorer.toml")?.model === "invalid", "invalid binding should be explicit in status JSON");

    run("node", [cli, "sync", "--projects", repo]);
    assert(!/^model\s*=/m.test(managedAgentHeader(fs.readFileSync(explorer, "utf8"))), "sync must not preserve an invalid model override");
    assertStatusOk(repo);
  }
}

function testModelTextInsideInstructionsIsNotPromotedToOverride() {
  const repo = tmpdir("model-in-instructions");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const explorer = path.join(repo, ".agents", "agents", "explorer.toml");
  const withExample = fs.readFileSync(explorer, "utf8").replace(
    'developer_instructions = """',
    'developer_instructions = """\nmodel = "example/in-docs"',
  );
  writeFile(explorer, withExample);

  run("node", [cli, "sync", "--projects", repo]);
  const synced = fs.readFileSync(explorer, "utf8");
  assert(!/^model\s*=/m.test(managedAgentHeader(synced)), "instruction text must not become a top-level model override");
  assert(!synced.includes('model = "example/in-docs"'), "sync should refresh stale managed instructions without promoting their example model");
  assertStatusOk(repo);
}

function testCommandSpecificArgumentsAreRejectedBeforeWrites() {
  const dryRunDest = tmpdir("invalid-init-dry-run");
  const invalidInit = run("node", [cli, "init", "--dest", dryRunDest, "--dry-run"], { check: false });
  assert(invalidInit.status !== 0 && invalidInit.stderr.includes("not valid for 'init'"), "init should reject --dry-run");
  assert(!exists(path.join(dryRunDest, ".agents")), "invalid init arguments must not write files");

  const positionalDest = tmpdir("invalid-init-positional");
  const invalidPositional = run("node", [cli, "init", "unexpected-project"], { cwd: positionalDest, check: false });
  assert(invalidPositional.status !== 0 && invalidPositional.stderr.includes("not valid for 'init'"), "init should reject positional project arguments");
  assert(!exists(path.join(positionalDest, ".agents")), "invalid positional init must not write files");

  const repo = tmpdir("invalid-command-options");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const explorer = path.join(repo, ".agents", "agents", "explorer.toml");
  writeFile(explorer, fs.readFileSync(explorer, "utf8").replace(/^description\s*=.*$/m, '$&\nmodel = "vendor/keep"'));

  const invalidStatus = run("node", [cli, "status", "--projects", repo, "--reset-agent-models"], { check: false });
  assert(invalidStatus.status !== 0 && invalidStatus.stderr.includes("not valid for 'status'"), "status should reject --reset-agent-models");
  assert(managedAgentHeader(fs.readFileSync(explorer, "utf8")).includes('model = "vendor/keep"'), "rejected status command must not reset models");

  const invalidSync = run("node", [cli, "sync", "--projects", repo, "--force"], { check: false });
  assert(invalidSync.status !== 0 && invalidSync.stderr.includes("not valid for 'sync'"), "sync should reject --force");
  const validDryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--reset-agent-models"]);
  assert(validDryRun.status === 0, "sync should accept its documented dry-run/reset options together");
  assert(managedAgentHeader(fs.readFileSync(explorer, "utf8")).includes('model = "vendor/keep"'), "dry-run must not reset models on disk");
}

function testBridgeIsGeneric() {
  const repo = tmpdir("bridge");
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("python3", [assetAp, "--repo", repo, "install", "--bridges"]);
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

function testOptionalDocsAndLegacyToolsDoNotCauseDrift() {
  const repo = tmpdir("legacy-extras");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  writeFile(path.join(repo, "docs", "interfaces", "api.md"), "# Existing API\n");
  writeFile(path.join(repo, "docs", "tools", "autopipeline", "core.py"), "# legacy copy\n");
  writeFile(path.join(repo, "docs", "tools", "autopipeline", "http_checks.py"), "# legacy copy\n");
  assertStatusOk(repo);
}

function testOptionalScaffoldIsOnDemandAndIdempotent() {
  const repo = tmpdir("optional-scaffold");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  run("python3", [launcher, "--repo", repo, "scaffold", "api", "--write"]);
  const api = path.join(repo, "docs", "interfaces", "api.md");
  assert(exists(api), "api scaffold should be created on demand");
  writeFile(api, "# User API\n");
  run("python3", [launcher, "--repo", repo, "scaffold", "api", "--write"]);
  assert(fs.readFileSync(api, "utf8") === "# User API\n", "scaffold should not overwrite existing docs without --force");
}

function testTestingScaffoldMatchesCheckMatrixSchema() {
  const repo = tmpdir("testing-scaffold");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  run("python3", [launcher, "--repo", repo, "scaffold", "testing", "--write"]);

  const matrix = path.join(repo, "docs", "testing", "regression-matrix.md");
  const initial = fs.readFileSync(matrix, "utf8");
  const row = initial.split(/\r?\n/).find(line => line.startsWith("| R-001 |"));
  assert(row, "testing scaffold should include R-001");
  const columns = row.split("|").slice(1, -1).map(value => value.trim());
  assert(columns.length === 8, `regression row should have 8 columns, got ${columns.length}`);

  const pending = run("python3", [launcher, "--repo", repo, "check-matrix"], { check: false });
  const pendingOutput = `${pending.stdout}\n${pending.stderr}`;
  assert(pending.status !== 0 && pendingOutput.includes("R-001: TODO"), `generated matrix should be parsed as pending: ${pendingOutput}`);
  assert(!pendingOutput.includes("No regression rows found"), "generated matrix must not be rejected as malformed");

  writeFile(matrix, initial.replace("| TODO | <evidence> |", "| PASS | logs/regression.txt |"));
  run("python3", [launcher, "--repo", repo, "check-matrix"]);
}

function testReviewScaffoldLeavesBaselineGenerationToBaselineCommand() {
  const repo = tmpdir("review-scaffold");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");

  run("python3", [launcher, "--repo", repo, "scaffold", "review", "--write"]);
  assert(exists(path.join(repo, "docs", "reviews", "_TEMPLATE-REVIEW.md")), "review scaffold should create its review template");
  for (const rel of ["docs/reviews/project-health-baseline.md", "docs/reviews/optimization-backlog.md"]) {
    assert(!exists(path.join(repo, rel)), `review scaffold must leave generated baseline output absent: ${rel}`);
  }

  run("git", ["init", "-q"], { cwd: repo });
  run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
  run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
  run("git", ["add", "-A"], { cwd: repo });
  run("git", ["commit", "-qm", "baseline"], { cwd: repo });
  run("python3", [launcher, "--repo", repo, "baseline", "init", "--write"]);
  assert(fs.readFileSync(path.join(repo, "docs", "reviews", "project-health-baseline.md"), "utf8").includes("Generated by `ap.py baseline init`"), "baseline command should generate the health baseline");
  assert(fs.readFileSync(path.join(repo, "docs", "reviews", "optimization-backlog.md"), "utf8").includes("Generated by `ap.py baseline init`"), "baseline command should generate the optimization backlog");
}

function testUpgradePrefersModernProjectAssetsAndIgnoresRetiredTemplates() {
  const repo = tmpdir("upgrade-modern-source");
  const fakeHome = tmpdir("upgrade-stale-home");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);

  const projectSkill = path.join(repo, ".agents", "skills", "auto-coding-skill");
  writeFile(path.join(projectSkill, "data", "templates", "docs", "interfaces", "api.md"), "# Retired project template\n");

  const staleGlobal = path.join(fakeHome, ".agents", "skills", "auto-coding-skill");
  writeFile(path.join(staleGlobal, "scripts", "ap.py"), "# legacy runtime\n");
  writeFile(path.join(staleGlobal, "data", "templates", "ENGINEERING.md"), "---\n---\n");
  writeFile(path.join(staleGlobal, "data", "templates", "docs", "interfaces", "api.md"), "# Retired global template\n");

  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  const result = run(
    "python3",
    [launcher, "--repo", repo, "upgrade", "--write", "--json"],
    { env: pythonEnvWithHome(fakeHome) },
  );
  const parsed = JSON.parse(result.stdout);
  assert(fs.realpathSync(parsed.source_root) === fs.realpathSync(projectSkill), `upgrade should prefer the modern project asset root: ${result.stdout}`);
  assert(!exists(path.join(repo, "docs", "interfaces", "api.md")), "upgrade must not materialize retired optional templates");
}

function testUpgradeInitializesNewEngineeringDefaults() {
  const repo = tmpdir("upgrade-engineering-defaults");
  const fakeHome = tmpdir("upgrade-engineering-home");
  run("git", ["init", "-q"], { cwd: repo });
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test", "test:full": "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });

  const projectAp = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  run("python3", [projectAp, "--repo", repo, "upgrade", "--write"], { env: pythonEnvWithHome(fakeHome) });

  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes(`name: "${path.basename(repo)}"`), "upgrade should initialize a newly created project name");
  for (const key of ["gate_changed", "gate_standard"]) {
    assert(engineering.includes(`${key}: "npm test"`), `upgrade should initialize commands.${key} from the ordinary Node test script`);
  }
  assert(engineering.includes('gate_full: "npm run test:full"'), "upgrade should infer full only from a dedicated test:full script");
}

function testUpgradeInstallsRuntimeRequiredByLauncher() {
  const repo = tmpdir("upgrade-missing-runtime");
  run("git", ["init", "-q"], { cwd: repo });
  run("python3", [assetAp, "--repo", repo, "upgrade", "--write"]);
  const projectRuntime = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  assert(exists(projectRuntime), "upgrade should install the runtime required by the new launcher");
  const help = run("python3", [launcher, "--help"]);
  assert(help.stdout.includes("autopipeline"), "upgraded launcher should remain executable");
}

function testLedgerArchiveRecognizesSettledStatuses() {
  const repo = tmpdir("ledger-status");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  writeFile(path.join(repo, "docs", "tasks", "taskbook.md"), [
    "# Taskbook", "", "## Task T001 - superseded work", "- Status: Superseded by T002", "",
    "## Task T002 - external dependency", "- Status: External Dependency", "",
    "## Task T003 - deployed work", "- Status: Deployed / Jenkins #123 SUCCESS", "",
    "## Task T004 - local pass", "- Status: Local PASS，待生产迁移窗口", "",
    "## Task T005 - markdown done", "- Status: `Done / PASS`", "",
    "## Task T006 - localized done", "- 状态：Done（PASS）", "",
  ].join("\n"));
  writeFile(path.join(repo, "docs", "tasks", "closure-log.md"), [
    "# Closure Log", "", "## T001 - superseded work", "- Result: DEV-CLOSED", "",
    "## T002 - external dependency", "- Result: PARTIAL", "",
    "## T003 - deployed work", "- Result: PASS", "",
    "## T004 - local pass", "- Result: DEV-CLOSED", "",
    "## T005 - markdown done", "- Result: PASS", "",
    "## T006 - localized done", "- Result: PASS", "",
  ].join("\n"));
  const result = run("python3", [assetAp, "--repo", repo, "docs-ledger-archive", "--plan", "--period", "2026-06", "--json"]);
  const parsed = JSON.parse(result.stdout);
  assert(parsed.counts.taskbook_sections === 6, `settled task sections should archive: ${result.stdout}`);
  assert(parsed.active_task_conflicts.length === 0, `settled statuses should not conflict: ${result.stdout}`);
}

function testLedgerArchiveUpdatesExistingPeriodIndex() {
  const repo = tmpdir("ledger-index-update");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);

  const taskbook = path.join(repo, "docs", "tasks", "taskbook.md");
  const closure = path.join(repo, "docs", "tasks", "closure-log.md");
  const designDir = path.join(repo, "docs", "design");
  writeFile(taskbook, "# Taskbook\n\n## Task T001 - first\n- Status: Done\n");
  writeFile(closure, "# Closure Log\n\n## T001 - first\n- Result: PASS\n");
  writeFile(path.join(designDir, "T001-first.md"), "# T001\n");
  run("python3", [assetAp, "--repo", repo, "docs-ledger-archive", "--write", "--period", "2026-06", "--json"]);

  fs.appendFileSync(taskbook, "\n## Task T002 - second\n- Status: `Done / PASS`\n");
  fs.appendFileSync(closure, "\n## T002 - second\n- Result: PASS\n");
  writeFile(path.join(designDir, "T002-second.md"), "# T002\n");
  run("python3", [assetAp, "--repo", repo, "docs-ledger-archive", "--write", "--period", "2026-06", "--json"]);

  const index = fs.readFileSync(path.join(repo, "docs", "tasks", "archive-index.md"), "utf8");
  assert((index.match(/^## 2026-06$/gm) || []).length === 1, `archive period should be unique: ${index}`);
  assert(index.includes("(2 sections)"), `archive index should report cumulative task/closure counts: ${index}`);
  assert(index.includes("(2 files)"), `archive index should report cumulative design count: ${index}`);
}

testPreflightAvoidsPartialInstall();
testDestVariants();
testLauncherFallsBackToGlobalRuntime();
testMinimalSyncConvergesWithinBudget();
testOrdinaryNodeTestIsNotPromotedToFullGate();
testManagedAgentModelsInheritAndOverridesSurvive();
testForcePreservesCustomAgentsAndModelOverrides();
testInvalidManagedAgentModelsFailStatusAndAreDroppedOnSync();
testModelTextInsideInstructionsIsNotPromotedToOverride();
testCommandSpecificArgumentsAreRejectedBeforeWrites();
testBridgeIsGeneric();
testUpgradeCleansManagedBridgeExtrasOnly();
testOptionalDocsAndLegacyToolsDoNotCauseDrift();
testOptionalScaffoldIsOnDemandAndIdempotent();
testTestingScaffoldMatchesCheckMatrixSchema();
testReviewScaffoldLeavesBaselineGenerationToBaselineCommand();
testUpgradePrefersModernProjectAssetsAndIgnoresRetiredTemplates();
testUpgradeInitializesNewEngineeringDefaults();
testUpgradeInstallsRuntimeRequiredByLauncher();
testLedgerArchiveRecognizesSettledStatuses();
testLedgerArchiveUpdatesExistingPeriodIndex();

console.log("cli-installer-regression-ok");
