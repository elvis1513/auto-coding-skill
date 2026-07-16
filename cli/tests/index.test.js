import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import zlib from "node:zlib";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(repoRoot, "cli", "src", "index.js");
const assetAp = path.join(repoRoot, "cli", "assets", "skill", "scripts", "ap.py");
// Frozen gzip/base64 fixture of the official v2.2.0 ENGINEERING body (frontmatter excluded).
const officialV220EngineeringBody = zlib.gunzipSync(Buffer.from(
  "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",
  "base64",
)).toString("utf8");
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

function fillRequiredAccess(repo, password = "local-dev-password") {
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const text = fs.readFileSync(engineering, "utf8");
  const block = [
    "access:",
    "  project:",
    "    frontend:",
    '      url: "http://project-frontend.local"',
    '      username: "project-frontend-user"',
    `      password: ${JSON.stringify(password)}`,
    "    backend:",
    '      url: "http://project-backend.local"',
    '      username: "project-backend-user"',
    `      password: ${JSON.stringify(password)}`,
    "  jenkins:",
    "    frontend:",
    '      url: "http://jenkins-frontend.local"',
    '      username: "jenkins-frontend-user"',
    `      password: ${JSON.stringify(password)}`,
    "    backend:",
    '      url: "http://jenkins-backend.local"',
    '      username: "jenkins-backend-user"',
    `      password: ${JSON.stringify(password)}`,
    "  gitlab:",
    '    url: "http://gitlab.local"',
    '    username: "gitlab-user"',
    `    password: ${JSON.stringify(password)}`,
    "  nexus:",
    "    frontend:",
    '      url: "http://nexus-frontend.local"',
    '      username: "nexus-frontend-user"',
    `      password: ${JSON.stringify(password)}`,
  ].join("\n");
  const withAccess = text.replace(/^access:\r?\n[\s\S]*?(?=^concurrency:)/m, `${block}\n\n`);
  const updated = withAccess
    .replace('  project_fast: ""', '  project_fast: "true"')
    .replace(
      "  routes: []",
      [
        "  routes:",
        '    - name: "project-code"',
        '      paths: ["**"]',
        '      exclude: ["*.md", "docs/**"]',
        '      commands: ["project_fast"]',
      ].join("\n"),
    );
  assert(updated !== text || text.includes(password), "required project values should be replaceable");
  fs.writeFileSync(engineering, updated);
}

function assertStatusOk(repo) {
  fillRequiredAccess(repo);
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

  for (const rel of ["docs/ENGINEERING.md", "docs/tools/autopipeline/ap.py"]) {
    assert(exists(path.join(repo, rel)), `missing core scaffold file: ${rel}`);
  }
  for (const rel of ["docs/tasks/taskbook.md", "docs/tasks/closure-log.md", "docs/interfaces/api.md", "docs/design/_TEMPLATE-DD.md", "docs/testing/regression-matrix.md", "docs/tools/autopipeline/core.py", "docs/tools/autopipeline/http_checks.py"]) {
    assert(!exists(path.join(repo, rel)), `optional/duplicate file should not be installed: ${rel}`);
  }

  const files = listProjectFiles(repo);
  const lines = files.reduce((total, file) => total + fs.readFileSync(file, "utf8").split(/\r?\n/).length, 0);
  assert(files.length <= 23, `minimal scaffold file budget exceeded: ${files.length}`);
  assert(lines <= 10800, `minimal scaffold line budget exceeded: ${lines}`);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes("profile: \"auto\""), "engineering should enable adaptive profiles");
  assert(engineering.includes("isolation: \"adaptive\""), "engineering should default to adaptive clean-branch/worktree isolation");
  assert(engineering.includes('completion: "push"'), "engineering should complete normal development at push");
  assert(engineering.includes('project_fast: ""'), "generic projects should expose an optional project-fast command");
  assert(engineering.includes("max_command_seconds: 120"), "engineering should bound each final route command");
  assert(engineering.includes("max_total_seconds: 180"), "engineering should bound the complete final gate");
  assert(engineering.includes(`name: "${path.basename(repo)}"`), "project name should be initialized automatically");
  assert(!engineering.includes("## Design, review, and subagents"), "engineering must not duplicate the behavioral protocol");
  const agentsProtocol = fs.readFileSync(path.join(repo, "AGENTS.md"), "utf8");
  assert(agentsProtocol.includes("## Minimum mechanism budget"), "AGENTS should own the shared behavioral protocol");
  assert(agentsProtocol.includes("One writer in a clean checkout works directly"), "AGENTS should enforce direct clean serial work");
  const fixer = fs.readFileSync(path.join(repo, ".agents", "agents", "fixer.toml"), "utf8");
  const reviewer = fs.readFileSync(path.join(repo, ".agents", "agents", "reviewer.toml"), "utf8");
  const browserDebugger = fs.readFileSync(path.join(repo, ".agents", "agents", "browser-debugger.toml"), "utf8");
  assert(fixer.includes("owned_paths"), "fixer should receive explicit path ownership");
  assert(fixer.includes("不提交、不推送、不集成"), "fixer should leave Git lifecycle to the main agent");
  assert(reviewer.includes("diff_fingerprint"), "reviewer verdict should bind to a stable diff");
  assert(browserDebugger.includes('sandbox_mode = "read-only"'), "browser discovery should be read-only");

  const incomplete = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(incomplete.status !== 0, "status should require access values after scaffold creation");
  const missing = JSON.parse(incomplete.stdout).results[0].missingConfigTokens;
  for (const field of [
    "access.project.frontend.password",
    "access.project.backend.password",
    "access.jenkins.frontend.password",
    "access.jenkins.backend.password",
    "access.gitlab.password",
    "access.nexus.frontend.password",
  ]) {
    assert(missing.includes(field), `status should report missing direct credential: ${field}`);
  }
  assert(!JSON.parse(incomplete.stdout).results[0].next.includes("upgrade"), "fresh projects with present blank fields should be told to fill them directly");

  assertStatusOk(repo);

  const doctor = run("python3", [path.join(repo, "docs", "tools", "autopipeline", "ap.py"), "--repo", repo, "doctor"], { check: false });
  const doctorOutput = `${doctor.stdout}\n${doctor.stderr}`;
  assert(doctor.status === 0, `filled generic project should pass the local doctor: ${doctorOutput}`);
  for (const unexpected of ["target_env.name", "backend_root", "jenkins.base_url", "docs.api_doc", "gate_full"]) {
    assert(!doctorOutput.includes(unexpected), `default doctor should not require optional field: ${unexpected}`);
  }
}

function testStatusRejectsLegacyIsolation() {
  const repo = tmpdir("legacy-isolation-status");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  fillRequiredAccess(repo);
  const engineeringPath = path.join(repo, "docs", "ENGINEERING.md");
  const engineering = fs.readFileSync(engineeringPath, "utf8").replace(
    'isolation: "adaptive"',
    'isolation: "legacy"',
  );
  fs.writeFileSync(engineeringPath, engineering);

  const result = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(result.status !== 0, "status must reject legacy isolation");
  const parsed = JSON.parse(result.stdout).results[0];
  assert(
    parsed.invalidConfigTokens.includes("concurrency.isolation (must be adaptive or worktree)"),
    `status should identify the invalid isolation value: ${result.stdout}`,
  );
  assert(parsed.next.includes("upgrade --write"), "status should direct legacy projects through upgrade");
}

function testStatusRejectsLegacyGateEscalation() {
  const repo = tmpdir("legacy-gate-status");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineeringPath = path.join(repo, "docs", "ENGINEERING.md");
  const engineering = fs.readFileSync(engineeringPath, "utf8").replace(
    "validation:\n",
    'gate:\n  full_on_unknown: "true"\n  full_on: ["prod_config"]\n  rules:\n    - match: ["Jenkinsfile"]\n      scope: "full"\n      commands: ["gate_full"]\n\nvalidation:\n',
  );
  fs.writeFileSync(engineeringPath, engineering);
  const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(status.status === 2, "legacy automatic gate escalation must make status non-zero");
  const invalid = JSON.parse(status.stdout).results[0].invalidConfigTokens;
  for (const expected of ["gate.full_on", "gate.full_on_unknown", "gate.rules[].scope", "gate.rules[].commands"]) {
    assert(invalid.some(item => item.includes(expected)), `status should report ${expected}`);
  }
}

function testOrdinaryNodeTestIsNotPromotedToAutomaticGate() {
  const repo = tmpdir("node-gate-inference");
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes('project_fast: ""'), "ordinary test must not be promoted to the project-fast command");
  assert(!engineering.includes("gate_standard:"), "ordinary test must not seed an automatic standard gate");
  assert(!engineering.includes("gate_full:"), "ordinary test must not seed an automatic full gate");

  fillRequiredAccess(repo);
  run("git", ["init", "-q"], { cwd: repo });
  run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
  run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
  run("git", ["add", "-A"], { cwd: repo });
  run("git", ["commit", "-qm", "baseline"], { cwd: repo });
  writeFile(path.join(repo, "migrations", "001.sql"), "-- migration\n");
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  const doctor = run("python3", [launcher, "--repo", repo, "doctor"], { check: false });
  assert(doctor.status === 0, `high-risk paths must not expand the local gate: ${doctor.stdout}\n${doctor.stderr}`);
  const gate = run("python3", [launcher, "--repo", repo, "light-gate", "--scope", "changed"]);
  assert(gate.stdout.includes("[run] project_fast"), "the configured project-fast route should run");
  assert((gate.stdout.match(/\[diff-check\] OK/g) || []).length === 1, "the built-in fast diff gate should run exactly once");
  const expanded = run("python3", [launcher, "--repo", repo, "light-gate", "--scope", "full"], { check: false });
  assert(expanded.status !== 0 && expanded.stderr.includes("invalid choice"), "light-gate must reject standard/full scopes instead of silently downgrading them");
}

function testAccessPasswordsAreRequiredButNeverPrintedByStatus() {
  const repo = tmpdir("required-access");
  const secret = "unique-local-secret-7f91";
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  fillRequiredAccess(repo, secret);

  const healthy = run("node", [cli, "status", "--projects", repo, "--json"]);
  assert(!healthy.stdout.includes(secret), "status JSON must not echo configured passwords");

  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  writeFile(engineering, fs.readFileSync(engineering, "utf8").replace(
    `      password: ${JSON.stringify(secret)}`,
    '      password: "" # direct value required\n      password_env: "PROJECT_FRONTEND_PASSWORD"',
  ));
  const missing = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(missing.status !== 0, "an environment reference must not replace the required direct password");
  assert(JSON.parse(missing.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), "status should name the missing direct password field");
  assert(!missing.stdout.includes(secret), "failed status JSON must not echo other configured passwords");
  assert(!JSON.parse(missing.stdout).results[0].next.includes("upgrade"), "present but blank fields should not trigger a no-op upgrade recommendation");

  for (const yamlValue of ["false", "[]", "{}", "2026-07-13", "0x10", "|"]) {
    fillRequiredAccess(repo);
    writeFile(engineering, fs.readFileSync(engineering, "utf8").replace('      password: "local-dev-password"', `      password: ${yamlValue}`));
    const nonString = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
    assert(JSON.parse(nonString.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), `YAML non-string ${yamlValue} must not count as a credential string`);
  }
  fillRequiredAccess(repo);
  writeFile(engineering, fs.readFileSync(engineering, "utf8").replace('      password: "local-dev-password"', '      password: "TO\\u0044O"'));
  const escapedPlaceholder = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(JSON.parse(escapedPlaceholder.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), "escaped YAML placeholders must be decoded before validation");

  writeFile(engineering, fs.readFileSync(engineering, "utf8").replace(/^access:\r?\n[\s\S]*?(?=^concurrency:)/m, ""));
  const absent = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(JSON.parse(absent.stdout).results[0].next.includes("upgrade --write"), "missing access paths should recommend configuration upgrade");
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
  const bridge = fs.readFileSync(path.join(repo, "AGENTS.md"), "utf8");
  assert(bridge.includes("Every writing agent owns a distinct task ID, worktree"), "bridge should expose writer isolation");
  assert(bridge.includes("integrates in dependency order"), "bridge should expose dependency ordering");
  for (const filename of [`CO${"DEX.md"}`, `CLA${"UDE.md"}`]) {
    assert(!exists(path.join(repo, filename)), "client-named bridge should not be created");
  }
}

function testUpgradeCleansAllManagedSkillExtras() {
  const repo = tmpdir("upgrade-extra");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "data", "templates", "bridges", "OLD.md"), "old\n");
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "custom.txt"), "custom\n");
  run("python3", [assetAp, "--repo", repo, "upgrade", "--write"]);
  assert(!exists(path.join(repo, ".agents", "skills", "auto-coding-skill", "data", "templates", "bridges", "OLD.md")), "managed bridge extra should be removed");
  assert(!exists(path.join(repo, ".agents", "skills", "auto-coding-skill", "custom.txt")), "fully managed Skill extras should be removed");
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
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test", "test:changed": "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });

  const projectAp = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  run("python3", [projectAp, "--repo", repo, "upgrade", "--write"], { env: pythonEnvWithHome(fakeHome) });

  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(engineering.includes(`name: "${path.basename(repo)}"`), "upgrade should initialize a newly created project name");
  assert(engineering.includes('project_fast: "npm run test:changed"'), "upgrade should infer only a dedicated changed-scope test");
  assert(!engineering.includes("gate_standard:"), "upgrade must not infer an automatic standard gate");
  assert(!engineering.includes("gate_full:"), "upgrade must not infer an automatic full gate");
}

function testUpgradeMigratesLegacyAutomaticGateToFastDefault() {
  const repo = tmpdir("upgrade-legacy-fast-gate");
  run("git", ["init", "-q"], { cwd: repo });
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });
  writeFile(path.join(repo, "docs", "ENGINEERING.md"), [
    "---",
    "workflow:",
    "  mode: verify",
    "  profile: auto",
    "project:",
    '  name: "legacy"',
    "concurrency:",
    "  isolation: legacy",
    "  base_ref: origin/dev",
    "  target_branch: dev",
    "commands:",
    '  gate_changed: "npm test"',
    '  gate_standard: "npm test"',
    '  gate_full: "npm run test:full"',
    "gate:",
    "  default_scope: auto",
    "  fallback_scope: standard",
    "  full_on_unknown: true",
    "  no_change_scope: standard",
    "  rules: []",
    "---",
    "# Legacy engineering",
    "",
  ].join("\n"));

  run("python3", [assetAp, "--repo", repo, "upgrade", "--write"]);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  assert(/project_fast:\s*(?:''|"")/.test(engineering), "upgrade should not promote an ordinary npm test to the project-fast gate");
  assert(engineering.includes("mode: dev"), "upgrade should migrate verify mode to fast development mode");
  assert(engineering.includes("completion: push"), "upgrade should add push completion");
  assert(engineering.includes("isolation: adaptive"), "upgrade should migrate legacy isolation to adaptive");
  assert(engineering.includes("on_unmapped: error"), "upgrade should fail closed when changed code has no validation route");
  assert(engineering.includes("rules: []"), "upgrade should remove legacy automatic gate escalation rules");
}

function testRemovedVerificationFlagsFailFast() {
  const repo = tmpdir("removed-verification-flags");
  const result = run("python3", [assetAp, "--repo", repo, "commit-push", "T1", "--msg", "T1: test", "--require-jenkins"], { check: false });
  assert(result.status !== 0 && result.stderr.includes("unrecognized arguments"), "removed post-push verification flags must fail instead of being ignored");
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

function testManagedEngineeringSyncIsControlledAndIdempotent() {
  const repo = tmpdir("managed-engineering");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);

  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const initial = fs.readFileSync(engineering, "utf8");
  const startPattern = /<!-- auto-coding-skill:managed-workflow:start version=4\.1\.1 -->/;
  const endMarker = "<!-- auto-coding-skill:managed-workflow:end -->";
  assert(startPattern.test(initial), "new projects should include a versioned managed workflow marker");
  assert(initial.includes(endMarker), "new projects should include the managed workflow end marker");

  const customized = initial
    .replace("workflow:\n", "# project-frontmatter-comment\nworkflow:\n")
    .replace(startPattern, "project note before managed workflow\n<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->")
    .replace(endMarker, `${endMarker}\nproject note after managed workflow`)
    .replace("The frontmatter contract is:", "Stale managed workflow contract:");
  writeFile(engineering, customized);
  const staleStart = customized.indexOf("<!-- auto-coding-skill:managed-workflow:start");
  const staleEnd = customized.indexOf(endMarker) + endMarker.length;
  const outsideBefore = customized.slice(0, staleStart);
  const outsideAfter = customized.slice(staleEnd);

  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryResult = JSON.parse(dryRun.stdout).results[0];
  assert(dryResult.managedWorkflow.state === "stale", `dry-run should expose stale workflow state: ${dryRun.stdout}`);
  assert(dryResult.managedWorkflow.version === "4.1.1", "dry-run should expose the target workflow version");
  assert(dryResult.actions.some(item => item.action === "would-update" && item.path === "docs/ENGINEERING.md"), "dry-run should plan the managed body update");
  assert(fs.readFileSync(engineering, "utf8") === customized, "dry-run must not write ENGINEERING.md");

  run("node", [cli, "sync", "--projects", repo]);
  const updated = fs.readFileSync(engineering, "utf8");
  const updatedStart = updated.indexOf("<!-- auto-coding-skill:managed-workflow:start");
  const updatedEnd = updated.indexOf(endMarker) + endMarker.length;
  assert(updated.slice(0, updatedStart) === outsideBefore, "sync must preserve frontmatter and content before the managed block byte-for-byte");
  assert(updated.slice(updatedEnd) === outsideAfter, "sync must preserve content after the managed block byte-for-byte");
  assert(updated.includes("version=4.1.1"), "sync should install the current managed workflow version");
  assert(updated.includes("The frontmatter contract is:"), "sync should refresh stale managed workflow content");

  fillRequiredAccess(repo);
  const status = run("node", [cli, "status", "--projects", repo, "--json"]);
  const statusResult = JSON.parse(status.stdout).results[0];
  assert(statusResult.managedWorkflow.state === "current", `status should expose current managed workflow state: ${status.stdout}`);
  assert(statusResult.managedWorkflow.version === "4.1.1", "status should expose the installed managed workflow version");

  const beforeSecondSync = fs.readFileSync(engineering, "utf8");
  const second = run("node", [cli, "sync", "--projects", repo, "--json"]);
  assert(!JSON.parse(second.stdout).results[0].actions.some(item => item.path === "docs/ENGINEERING.md"), "current managed workflow should be idempotent");
  assert(fs.readFileSync(engineering, "utf8") === beforeSecondSync, "idempotent sync must not rewrite ENGINEERING.md");
}

function testLegacyEngineeringMigrationPreservesExistingBody() {
  const repo = tmpdir("legacy-managed-engineering");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const current = fs.readFileSync(engineering, "utf8");
  const start = current.indexOf("<!-- auto-coding-skill:managed-workflow:start");
  const endMarker = "<!-- auto-coding-skill:managed-workflow:end -->";
  const end = current.indexOf(endMarker) + endMarker.length;
  const legacyNote = "\n## Legacy project facts\n\nKeep this project note exactly.\n";
  const legacy = `${current.slice(0, start)}${legacyNote}${current.slice(end)}`;
  writeFile(engineering, legacy);

  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryResult = JSON.parse(dryRun.stdout).results[0];
  assert(dryResult.managedWorkflow.state === "legacy-custom", "unknown unmarked documents should be reported as a custom legacy migration");
  assert(dryResult.managedWorkflow.preservedCustom === true, "custom legacy migration should expose its preservation policy");
  assert(dryResult.actions.find(item => item.path === "docs/ENGINEERING.md")?.detail.includes("preserved-custom"), "custom legacy action should be labeled preserved-custom");
  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(engineering, "utf8");
  assert(migrated.includes("version=4.1.1"), "legacy migration should insert the current managed workflow");
  assert(migrated.includes(legacyNote), "legacy migration must preserve the complete existing body");
  const migratedStart = migrated.indexOf("<!-- auto-coding-skill:managed-workflow:start");
  const migratedEnd = migrated.indexOf(endMarker) + endMarker.length;
  assert(`${migrated.slice(0, migratedStart)}${migrated.slice(migratedEnd)}` === legacy, "removing the inserted managed block should recover custom legacy content byte-for-byte");

  const stable = fs.readFileSync(engineering, "utf8");
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(engineering, "utf8") === stable, "legacy migration should converge after one sync");
}

function testOfficialLegacyEngineeringBodyIsReplacedWithoutDuplication() {
  const repo = tmpdir("official-legacy-engineering");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const current = fs.readFileSync(engineering, "utf8");
  const frontmatter = current.match(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/)?.[0];
  assert(frontmatter, "official legacy fixture requires frontmatter");
  const customizedFrontmatter = frontmatter.replace("workflow:\n", "# keep-official-migration-config\nworkflow:\n");
  writeFile(engineering, `${customizedFrontmatter}${officialV220EngineeringBody}`);

  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryResult = JSON.parse(dryRun.stdout).results[0];
  assert(dryResult.managedWorkflow.state === "legacy-official", `official body hash should select replacement migration: ${dryRun.stdout}`);
  assert(dryResult.actions.find(item => item.path === "docs/ENGINEERING.md")?.detail.includes("official-legacy"), "official legacy action should identify replacement migration");
  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(engineering, "utf8");
  assert(migrated.startsWith(customizedFrontmatter), "official legacy migration must preserve YAML frontmatter byte-for-byte");
  assert((migrated.match(/auto-coding-skill:managed-workflow:start/g) || []).length === 1, "official legacy migration should install exactly one managed workflow");
  assert((migrated.match(/^## Delivery levels$/gm) || []).length === 0, "official legacy migration must remove the old duplicated workflow body");

  const stable = fs.readFileSync(engineering, "utf8");
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(engineering, "utf8") === stable, "official legacy migration should be idempotent");
}

function testMalformedManagedMarkersFailClosed() {
  const cases = {
    "single-start": "<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->\nold\n",
    "single-end": "old\n<!-- auto-coding-skill:managed-workflow:end -->\n",
    duplicate: "<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->\n<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->\n<!-- auto-coding-skill:managed-workflow:end -->\n",
    nested: "<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->\n<!-- auto-coding-skill:managed-workflow:end -->\n<!-- auto-coding-skill:managed-workflow:end -->\n",
  };
  for (const [name, malformed] of Object.entries(cases)) {
    const repo = tmpdir(`managed-marker-${name}`);
    run("node", [cli, "init"], { cwd: repo });
    run("node", [cli, "sync", "--projects", repo]);
    const engineering = path.join(repo, "docs", "ENGINEERING.md");
    const text = fs.readFileSync(engineering, "utf8");
    const start = text.indexOf("<!-- auto-coding-skill:managed-workflow:start");
    const endMarker = "<!-- auto-coding-skill:managed-workflow:end -->";
    const end = text.indexOf(endMarker) + endMarker.length;
    writeFile(engineering, `${text.slice(0, start)}${malformed}${text.slice(end)}`);
    const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
    writeFile(skill, `user-sentinel-${name}\n`);
    const before = fs.readFileSync(engineering, "utf8");

    const result = run("node", [cli, "sync", "--projects", repo], { check: false });
    assert(result.status !== 0 && result.stderr.includes("refusing"), `${name}: malformed markers should reject sync`);
    assert(fs.readFileSync(engineering, "utf8") === before, `${name}: rejected sync must not touch ENGINEERING.md`);
    assert(fs.readFileSync(skill, "utf8") === `user-sentinel-${name}\n`, `${name}: preflight must reject before writing the skill`);
  }
}

function testPartialSkillSyncIsRejectedWithoutWrites() {
  const repo = tmpdir("partial-skill-sync");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  writeFile(skill, "stale skill\n");
  const rejected = run("node", [cli, "sync", "--projects", repo, "--components", "skill"], { check: false });
  assert(rejected.status !== 0 && rejected.stderr.includes("removed in 4.1"), "partial sync must explain whole-install convergence");
  assert(fs.readFileSync(skill, "utf8") === "stale skill\n", "rejected partial sync must not write the skill");
}

function testLegacyTaskPreflightRejectsWholeBatchAtomically() {
  const first = tmpdir("legacy-batch-first");
  const second = tmpdir("legacy-batch-second");
  for (const repo of [first, second]) {
    run("git", ["init", "-q"], { cwd: repo });
    run("node", [cli, "init"], { cwd: repo });
    run("node", [cli, "sync", "--projects", repo]);
  }
  const firstSkill = path.join(first, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const secondAgent = path.join(second, ".agents", "agents", "explorer.toml");
  writeFile(firstSkill, "first-project-sentinel\n");
  writeFile(secondAgent, `${fs.readFileSync(secondAgent, "utf8")}\n# second-project-sentinel\n`);
  const secondAgentBefore = fs.readFileSync(secondAgent);
  writeFile(path.join(second, ".git", "auto-coding-skill", "tasks", "T-V3.json"), JSON.stringify({ schema: 3, task_id: "T-V3", state: "active" }));

  const result = run("node", [cli, "sync", "--projects", `${first},${second}`], { check: false });
  assert(result.status !== 0 && result.stderr.includes("entire sync batch"), "one legacy task should reject the complete multi-project batch");
  assert(fs.readFileSync(firstSkill, "utf8") === "first-project-sentinel\n", "batch preflight must reject before writing an earlier clean project");
  assert(fs.readFileSync(secondAgent).equals(secondAgentBefore), "batch preflight must not write the project containing the legacy task");
}

function testManagedAgentsMigrationReplacesWholeFileAndArchivesPreviousRules() {
  const repo = tmpdir("managed-agents-document");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const agents = path.join(repo, "AGENTS.md");
  const initial = fs.readFileSync(agents, "utf8");
  assert(initial.includes("managed-agents:start version=4.1.1"), "new projects should receive the versioned root AGENTS block");

  const custom = [
    "# Project rules",
    "",
    "- Preserve this repository-specific rule exactly.",
    "- `high-risk` cannot be downgraded and must execute `commands.gate_full`; changed or standard fallbacks do not count. Use `PASS / FAIL / PARTIAL` only from the required executed evidence.",
    "",
  ].join("\n");
  writeFile(agents, custom);
  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const plan = JSON.parse(dryRun.stdout).results[0].managedAgentsDocument;
  assert(plan.state === "legacy-custom", `unmarked custom AGENTS should be migrated: ${dryRun.stdout}`);
  assert(plan.migrations.includes("agents-whole-file-replacement"), "AGENTS should use the whole-file convergence migration");
  const dryActions = JSON.parse(dryRun.stdout).results[0].actions;
  assert(dryActions.some(item => item.action === "would-archive"), "dry-run should expose the historical AGENTS archive");

  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(agents, "utf8");
  assert(migrated.includes("managed-agents:start version=4.1.1"), "AGENTS migration should install the current managed block");
  assert(!migrated.includes("Preserve this repository-specific rule exactly."), "root AGENTS must contain no project-specific tail");
  assert(!migrated.includes("must execute `commands.gate_full`"), "known official conflicting rule should be removed");
  const canonical = fs.readFileSync(path.join(repoRoot, "cli", "assets", "skill", "data", "templates", "bridges", "AGENTS.md"), "utf8");
  assert(migrated === canonical, "root AGENTS must be byte-identical to the packaged canonical file");
  const archive = path.join(repo, "docs", "archive", "workflow", "AGENTS.pre-4.1.1.md");
  assert(fs.readFileSync(archive, "utf8").includes("Preserve this repository-specific rule exactly."), "previous AGENTS content must be archived once");
  const stable = fs.readFileSync(agents);
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(agents).equals(stable), "managed AGENTS sync should be idempotent");
}

function testUnknownWorkflowConflictFailsWholeBatchBeforeWrites() {
  const first = tmpdir("workflow-conflict-first");
  const second = tmpdir("workflow-conflict-second");
  for (const repo of [first, second]) {
    run("git", ["init", "-q"], { cwd: repo });
    run("node", [cli, "init"], { cwd: repo });
    run("node", [cli, "sync", "--projects", repo]);
  }
  const firstSkill = path.join(first, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  writeFile(firstSkill, "batch-sentinel\n");
  const secondEngineering = path.join(second, "docs", "ENGINEERING.md");
  fs.appendFileSync(secondEngineering, "\nHigh-risk changes must run the real full gate before push.\n");

  const status = run("node", [cli, "status", "--projects", second, "--json"], { check: false });
  assert(status.status !== 0, "status must be non-ok for an unknown conflicting workflow rule");
  const statusPlan = JSON.parse(status.stdout).results[0].managedWorkflow;
  assert(statusPlan.state === "conflict", `status should expose the document conflict: ${status.stdout}`);
  assert(statusPlan.conflicts[0].file === "docs/ENGINEERING.md" && statusPlan.conflicts[0].line > 0, "status conflict should include file and line");

  const sync = run("node", [cli, "sync", "--projects", `${first},${second}`], { check: false });
  assert(sync.status !== 0 && sync.stderr.includes("entire sync batch before writes"), "one unknown conflict must reject the complete batch");
  assert(fs.readFileSync(firstSkill, "utf8") === "batch-sentinel\n", "batch conflict preflight must run before an earlier project's skill write");
}

function testEngineeringMarkerBoundaryIsNormalized() {
  const repo = tmpdir("engineering-marker-boundary");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const marker = "<!-- auto-coding-skill:managed-workflow:end -->";
  const current = fs.readFileSync(engineering, "utf8");
  writeFile(engineering, current.replace(`${marker}\n`, `${marker}# Project-specific workflow\n`));
  run("node", [cli, "sync", "--projects", repo]);
  const normalized = fs.readFileSync(engineering, "utf8");
  assert(normalized.includes(`${marker}\n# Project-specific workflow\n`), "sync should normalize a heading glued to the managed end marker");
}

function testEngineeringFrameworkAllowsProjectFactsButRejectsDuplicateWorkflow() {
  const repo = tmpdir("engineering-framework");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  fillRequiredAccess(repo);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  fs.appendFileSync(engineering, "\n# Project Facts\n\n## Repository boundaries\n\n- backend owns APIs.\n");
  const projectFactsStatus = run("node", [cli, "status", "--projects", repo, "--json"]);
  assert(JSON.parse(projectFactsStatus.stdout).results[0].managedWorkflow.state === "current", "project fact sections should remain outside the managed block");

  fs.appendFileSync(engineering, "\n## Delivery flow\n\n1. Known obsolete workflow.\n");
  const migration = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const migrationResult = JSON.parse(migration.stdout).results[0];
  assert(migrationResult.managedWorkflow.state === "stale", "known duplicate sections should use controlled migration");
  assert(migrationResult.managedWorkflow.migrations.includes("engineering-section-delivery-flow"), "known section migration should be explicit");
  assert(migrationResult.actions.some(item => item.action === "would-archive" && item.path.includes("ENGINEERING.pre-4.1.1")), "controlled section cleanup should archive the previous ENGINEERING file");
  run("node", [cli, "sync", "--projects", repo]);
  assert(!fs.readFileSync(engineering, "utf8").includes("Known obsolete workflow"), "known duplicate workflow section should be removed");

  fs.appendFileSync(engineering, "\n## Team workflow\n\n1. Unknown competing workflow.\n");
  const duplicateStatus = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(duplicateStatus.status !== 0, "duplicate workflow sections must make status non-current");
  const plan = JSON.parse(duplicateStatus.stdout).results[0].managedWorkflow;
  assert(plan.state === "conflict" && plan.conflicts.some(item => item.ruleId === "duplicate-managed-workflow-section"), "duplicate workflow conflict should identify the docs framework rule");
}

function testReleaseVersionMarkersStayInSync() {
  const expected = "4.1.1";
  const pkg = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  const lock = JSON.parse(fs.readFileSync(path.join(repoRoot, "package-lock.json"), "utf8"));
  const policy = JSON.parse(fs.readFileSync(
    path.join(repoRoot, "src", "auto-coding-skill", "data", "policies", "workflow-migrations-v1.json"),
    "utf8",
  ));
  assert(pkg.version === expected, "package version must match the 4.1.1 release");
  assert(lock.version === expected && lock.packages[""].version === expected, "package-lock versions must match");
  assert(policy.managed_versions.engineering === expected && policy.managed_versions.agents === expected, "managed workflow versions must match");
  for (const rel of [
    "src/auto-coding-skill/data/templates/ENGINEERING.md",
    "src/auto-coding-skill/data/templates/bridges/AGENTS.md",
    "cli/assets/skill/data/templates/ENGINEERING.md",
    "cli/assets/skill/data/templates/bridges/AGENTS.md",
  ]) {
    assert(fs.readFileSync(path.join(repoRoot, rel), "utf8").includes(`version=${expected}`), `${rel}: missing ${expected} marker`);
  }
}

function testProtocolResponsibilitiesStaySeparated() {
  const skill = fs.readFileSync(path.join(repoRoot, "src", "auto-coding-skill", "SKILL.md"), "utf8");
  const agents = fs.readFileSync(path.join(repoRoot, "src", "auto-coding-skill", "data", "templates", "bridges", "AGENTS.md"), "utf8");
  const engineering = fs.readFileSync(path.join(repoRoot, "src", "auto-coding-skill", "data", "templates", "ENGINEERING.md"), "utf8");
  const totalLines = [skill, agents, engineering].reduce((sum, text) => sum + text.split(/\r?\n/).length, 0);
  assert(totalLines <= 350, `shared protocol context budget exceeded: ${totalLines} lines`);
  assert(agents.includes("## Minimum mechanism budget") && agents.includes("## Bounded real validation"), "AGENTS must remain the behavioral protocol");
  assert(skill.includes("## Select the minimum mechanism set") && !skill.includes("## Authority"), "SKILL must remain invocation guidance");
  assert(engineering.includes("The frontmatter contract is:") && !engineering.includes("## Git and parallel work"), "ENGINEERING must remain project configuration/facts");
}

testPreflightAvoidsPartialInstall();
testDestVariants();
testLauncherFallsBackToGlobalRuntime();
testMinimalSyncConvergesWithinBudget();
testStatusRejectsLegacyIsolation();
testStatusRejectsLegacyGateEscalation();
testOrdinaryNodeTestIsNotPromotedToAutomaticGate();
testAccessPasswordsAreRequiredButNeverPrintedByStatus();
testManagedAgentModelsInheritAndOverridesSurvive();
testForcePreservesCustomAgentsAndModelOverrides();
testInvalidManagedAgentModelsFailStatusAndAreDroppedOnSync();
testModelTextInsideInstructionsIsNotPromotedToOverride();
testCommandSpecificArgumentsAreRejectedBeforeWrites();
testBridgeIsGeneric();
testUpgradeCleansAllManagedSkillExtras();
testOptionalDocsAndLegacyToolsDoNotCauseDrift();
testOptionalScaffoldIsOnDemandAndIdempotent();
testTestingScaffoldMatchesCheckMatrixSchema();
testReviewScaffoldLeavesBaselineGenerationToBaselineCommand();
testUpgradePrefersModernProjectAssetsAndIgnoresRetiredTemplates();
testUpgradeInitializesNewEngineeringDefaults();
testUpgradeMigratesLegacyAutomaticGateToFastDefault();
testRemovedVerificationFlagsFailFast();
testUpgradeInstallsRuntimeRequiredByLauncher();
testLedgerArchiveRecognizesSettledStatuses();
testLedgerArchiveUpdatesExistingPeriodIndex();
testManagedEngineeringSyncIsControlledAndIdempotent();
testLegacyEngineeringMigrationPreservesExistingBody();
testOfficialLegacyEngineeringBodyIsReplacedWithoutDuplication();
testMalformedManagedMarkersFailClosed();
testPartialSkillSyncIsRejectedWithoutWrites();
testLegacyTaskPreflightRejectsWholeBatchAtomically();
testManagedAgentsMigrationReplacesWholeFileAndArchivesPreviousRules();
testUnknownWorkflowConflictFailsWholeBatchBeforeWrites();
testEngineeringMarkerBoundaryIsNormalized();
testEngineeringFrameworkAllowsProjectFactsButRejectsDuplicateWorkflow();
testReleaseVersionMarkersStayInSync();
testProtocolResponsibilitiesStaySeparated();

console.log("cli-installer-regression-ok");
