import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import zlib from "node:zlib";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const cli = path.join(repoRoot, "cli", "src", "index.js");
const assetAp = path.join(repoRoot, "cli", "assets", "skill", "scripts", "ap.py");
const projectConfigRelativePath = path.join("docs", "project", "auto-coding-skill.yaml");
const projectConfigSchema = "auto-coding-skill/project-config/v1";
// Frozen gzip/base64 fixture of the official v2.2.0 ENGINEERING body (frontmatter excluded).
const officialV220EngineeringBody = zlib.gunzipSync(Buffer.from(
  "H4sIAAAAAAAAE51YwY7bOBK98ysKk8PuApaMnezuoTMYwNPuzfZObyboJDPHFk2WJMYUqWGR7mjQH78oUpLdQA6ZviRtWSSrXr33qmjxCm5cZxxiMK6D33w4ttY/CvGxNwStsQiGIPYIZFxnEQbpkrR2gkEaF6VxqOFxXgXKu9Z0KchovKvhZ8QRTATjxFsTa9hpDX7k76QFQsV/EXhnJ3js0eVjxuA/o4qATh4slqMDWhlRA6XQSoW1EK9ewc0XVIl34CUcKAnRLJHU87MrkCn6BggtqshnIfgWYh8QAduWYzjhusOVEE/wvnyAJ/g4jUZJm/ODJ3grIz+9tp5SQBi8RngST1BVFXzlX/EEzWBU8A08gfaKthEpUsX5buCEYQIapLVgyJf85nNUL12HmlfhqexDUTotg+atfNDGyTBBizJyINJp0Mi5LDssr19u0Zuur4KhI++x/2krU+y3o5wGdHGrcbR+2h6SsXquIvgAGpWVATXwYuDF8ARtshaeOAHTTvAkRFMwNnMp5Yy2DzV87L8CM78p7aOcaAFoc5HhRvhwGW0NO1g/AZmOyaOkcz7CAUH7R9cFqRk+E3uQcH13C62VOQEpFj6FZLGGnQP8MlqjTATnXcWRr2EFHK1USJkzfyGw/nHrfBikhYMktMZhfUExrv/VDEMD0pKHgL8nE2bWZpw6GZmv7+comvyZY6EGBjktCEMzytgTA6H8MEin89+k/IjNJldYulU7oplDbmq4niWH55U1H/LAxzfwVx/AYifVdPE9f/XALzV/g9YHcYaXk3sDEqzp+sgArkyaF4P2SMDYK59cBEkgn2X66hX8zzjDoD1zAyHuCziaj4QZV40ntH5kDl4JUcFzdJsraDSeGg6kmYF+9tICwxUUDm6+Sih4TijeYWZF7eSA/EBGsCgpZoNIxNaTE1rSfrMmg8CSLQZy+QatFiZgNTElmW8YlCFcZL1ZMS11zeDlQhNHltM0qjholKHD+IDu9DBTSzd50fPXPqM7Gkfnd4S4KzVfqnbEiYCS6rlgZyLkMhcmbKD5PRl1fGCT4k/z/9Jp0WRfaCAgmz5QGkcfIuoa7pODRnsWe5Pril+kijAY4nZRtQatBm1k5zxFo6gW4rcMU04MLrNgVyimz8BoDc05+7pHaWP/wDJ8SME2Jaz5KUunKd2lDd5FdHp7kOqITsOn+7vZljg6BgiJrRadHr1xEVSP6kglT+s747aEKmCEgC0GdOwH5w51kGQU+0PP4a7b1ZCz+m+pAxgSzzOZC9QUizKRsqFsP/tDDnADhyCd6jcgQzStVIshw4BRahnlRkQzoE9xA59ut7v3t5AIQwkbRkn06IOGk7SJww2A7mSCd6yri0Rq+OQSoRZr76XeJ6uXwsoD5QUy9hgg9tLxBGAXa83u2HurMVBR+h5bmWxcBwAh9s8E/fca7lFqiOswwfGyOcrSEaKkI6CLYarF94VOuUySPGsp+NT10CgribjZVFUWSmnqtXjN2yvOPA8o3EyRIkPTJvYWbhbsVfgGVEAW636/3e3vLwpqnGb+oa7FP2q4HUaLGTTe0KFCIu60RbqQmNSAXwxF/mNROcWQ1NqJAyZCyOSiWvyzJFWmGPL2hHrtN8Ux/7Um0exvfq2u7375cLNvNlm6Js4VTtTXQvxn9emstLmPXYpoxnw9UdpLc/6e2wXverHp6xp+LZ18pixc324XIudqZRVWl4ya5zDKmC3Bv999+MC+8e/d7d3sue939x9vd3cNy3LgkidpAU9GMxtrnjFzKXsfTJSZDz5oDDMdCW7evb19d3Nzf/vu7SZT5eD9cSuD6s0JabNUmKVrXMQcFIQcD20gYBeQyHi3PaTu/FzN89sSCO/DYpvFUt4SMbNj4cM80O59bn2DDEdIDvMEinr2ELZWBqFI48NKitFboyYh3qLDYNQFXZZ1zBx9MuTDBAeeCbKq8vQ05SkhIBtuURCZP3Aj2uSyhMvHIpoOv1TsK5rj9iFWB5+40Uzz1MQ+kzK1JzhYr45nHYhmjapG1/qgctpX5T3jujzeLZSz07kdchPA0ZOJPkyVy2UUuUQRz6JQfhiNxZBH4BV5iPLIUyEqLJ/9CQN0M05ODsZ1oscUTGkecJ+1tQqwRztiKDSVJ280uy1/kdxyZQhIo3dkDsaaaJBE9CBtQKknsMzsDCq9AV1KS6M1PNtohAED2gmiB5LRUDvluchhmXxqIT4RQrNMhmCciVBVj8FEhKpKo5YRq4JTM3efFadHo3ElwnzDqMVOKRxjHrcp+pDvHhoPPOda7zoCU3SdEcrpLafnfmd9V7h37WfY18uW9ipxQamIbmYYkJJt68vIH7PkMiNWuz6rrvjQIh0+Ca6zpQoaURlpzR+oz8ec73PZ4R2izkPxcCVE0zBovRin2Hv3er4aeW+J7yR+NGNJSY71OJ1DlKNZ4P2zS2efeOHqZ2R+4R4BTwYfX7qaRcO0fnH6q729cIdD6ujF8Fm7Lm2aRojnkpnn2Q5dRWkYZJiald/MGBPApzimSKBNQBXtVK6VZYIQZ4JekLOwNfqxsjyPwH5fZJ6tNrvifNtmVC3qDgO94blB8DBLVXlUzZ0Gqmq00jVwwDYrKz/mpXzkKtdpEd8weLdeC/4s38sw/Y0vf3Uw+sa1efav8hXmcjVUFdu8NO5bC700jiq3s5eEUkadigcS+OHj7sPPD7f7H6GqBurgu/XBFfwwM+TH774dzLWYObpvXMeoVPOYVkjLjLMyOcWTMfMn5HvP1/ZoQCNfuSP/DuAvfzsLyfEYz7+HNbXs2Ci3dDR23qBSnrtXlR9tSQUzRmrW1qQTd98iCxmXzWrxf3x8K0DDEwAA",
  "base64",
)).toString("utf8");
const managedAgentEfforts = {
  "browser-debugger.toml": "xhigh",
  "docs-researcher.toml": "medium",
  "explorer.toml": "medium",
  "fixer.toml": "medium",
  "reviewer.toml": "xhigh",
};
const exactDocs = [
  "docs/ENGINEERING.md",
  "docs/architecture/adr/_TEMPLATE-ADR.md",
  "docs/architecture/structure-standard.md",
  "docs/bugs/bug-list.md",
  "docs/deployment/deploy-records/_TEMPLATE-DEPLOY-RECORD.md",
  "docs/deployment/deploy-runbook.md",
  "docs/design/_TEMPLATE-DD.md",
  "docs/interfaces/api-change-log.md",
  "docs/interfaces/api.md",
  "docs/project/overview.md",
  "docs/project/repository-map.md",
  "docs/project/runtime.md",
  "docs/reviews/_TEMPLATE-REVIEW.md",
  "docs/skill-feedback/README.md",
  "docs/skill-feedback/_TEMPLATE-SKILL-FEEDBACK.md",
  "docs/testing/regression-matrix.md",
  "docs/tools/autopipeline/ap.py",
];

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

function installTrustedEngineeringDefault(repo, content, version) {
  const installedRelative = path.join(
    ".agents",
    "skills",
    "auto-coding-skill",
    "data",
    "templates",
    "ENGINEERING.md",
  );
  writeFile(path.join(repo, installedRelative), content);
  const manifestPath = path.join(repo, ".agents", "managed-install.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.skill_version = version;
  const entry = manifest.entries.find(item => item.path === installedRelative);
  assert(entry, "installed manifest must contain the managed ENGINEERING source template");
  Object.assign(entry, {
    source: "skill/data/templates/ENGINEERING.md",
    ownership: "exact",
    sha256: crypto.createHash("sha256").update(content).digest("hex"),
    version,
  });
  writeFile(manifestPath, `${JSON.stringify(manifest)}\n`);
}

function readEngineeringConfig(file) {
  const script = [
    "import json, pathlib, sys, yaml",
    "text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')",
    "parts = text.split('---', 2)",
    "assert len(parts) == 3 and not parts[0].strip(), 'missing YAML frontmatter'",
    "print(json.dumps(yaml.safe_load(parts[1]) or {}, sort_keys=True))",
  ].join("; ");
  return JSON.parse(run("python3", ["-c", script, file]).stdout);
}

function readYamlConfig(file) {
  const script = [
    "import json, pathlib, sys, yaml",
    "value = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
    "print(json.dumps(value, sort_keys=True))",
  ].join("; ");
  return JSON.parse(run("python3", ["-c", script, file]).stdout);
}

function projectConfigPath(repo) {
  return path.join(repo, projectConfigRelativePath);
}

function writeProjectConfig(repo, overrides) {
  writeFile(projectConfigPath(repo), `${JSON.stringify({ schema: projectConfigSchema, overrides }, null, 2)}\n`);
}

function renderYaml(value) {
  const script = [
    "import json, sys, yaml",
    "print(yaml.safe_dump(json.loads(sys.argv[1]), allow_unicode=True, sort_keys=False), end='')",
  ].join("; ");
  return run("python3", ["-c", script, JSON.stringify(value)]).stdout;
}

function readEffectiveConfig(repo) {
  const script = [
    "import json, pathlib, sys",
    "repo = pathlib.Path(sys.argv[1]).resolve()",
    "sys.path.insert(0, str(repo / '.agents' / 'skills' / 'auto-coding-skill' / 'scripts'))",
    "import core",
    "print(json.dumps(core.load_effective_config(repo), sort_keys=True))",
  ].join("; ");
  return JSON.parse(run("python3", ["-c", script, repo]).stdout);
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
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

function fillLegacyEngineeringAccess(repo, password = "local-dev-password") {
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
    .replace(/  project_fast: (?:""|'')/, '  project_fast: "true"')
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

function fillRequiredAccess(repo, password = "local-dev-password") {
  const overlay = projectConfigPath(repo);
  const existing = exists(overlay) ? (readYamlConfig(overlay).overrides ?? {}) : {};
  const required = requiredProjectOverrides(existing.project?.name ?? path.basename(repo), password);
  writeProjectConfig(repo, {
    ...existing,
    project: { ...required.project, ...(existing.project ?? {}) },
    access: required.access,
    commands: { ...(existing.commands ?? {}), ...required.commands },
    validation: { ...(existing.validation ?? {}), ...required.validation },
  });
}

function requiredProjectOverrides(projectName, password = "overlay-local-dev-password") {
  return {
    project: {
      name: projectName,
    },
    access: {
      project: {
        frontend: { url: "http://project-frontend.local", username: "project-frontend-user", password },
        backend: { url: "http://project-backend.local", username: "project-backend-user", password },
      },
      jenkins: {
        frontend: { url: "http://jenkins-frontend.local", username: "jenkins-frontend-user", password },
        backend: { url: "http://jenkins-backend.local", username: "jenkins-backend-user", password },
      },
      gitlab: { url: "http://gitlab.local", username: "gitlab-user", password },
      nexus: {
        frontend: { url: "http://nexus-frontend.local", username: "nexus-frontend-user", password },
      },
    },
    commands: {
      project_fast: "true",
    },
    validation: {
      routes: [
        {
          name: "project-code",
          paths: ["**"],
          exclude: ["*.md", "docs/**"],
          commands: ["project_fast"],
        },
      ],
    },
  };
}

function assertStatusOk(repo) {
  fillRequiredAccess(repo);
  const result = run("node", [cli, "status", "--projects", repo, "--json"]);
  const parsed = JSON.parse(result.stdout);
  assert(parsed.results[0].ok === true, `status should be ok: ${result.stdout}`);
}

function testInitFullyConvergesExistingProject() {
  const repo = tmpdir("full-init");
  run("node", [cli, "init"], { cwd: repo });
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const structureStandard = path.join(repo, "docs", "architecture", "structure-standard.md");
  assert(
    fs.readFileSync(structureStandard, "utf8").startsWith("# Project Structure Standard"),
    "first init must scaffold the project structure standard",
  );
  const customStructureStandard = "# XJMate Structure Standard\n\nProject-owned architecture policy.\n";
  const expectedRiskRules = [
    {
      name: "frontend-manifest-and-extension-policy",
      paths: ["package.json", "frontend/package.json", "frontend/extensions/**"],
      profile: "high-risk",
      review: "required",
      design: "required",
    },
  ];
  const expectedStructure = {
    enabled: false,
    enforcement: "blocking",
    architecture_standard: "xjmate-clean-architecture",
    exclude: ["docs/**"],
    allow_large_files: ["generated/**"],
    reusable_tool_dirs: ["tools/**"],
    max_file_lines_warn: 701,
    max_file_lines_block: 1401,
    max_function_lines_warn: 101,
    max_added_lines_to_large_file: 41,
    require_reuse_search: false,
    block_new_responsibility_in_large_file: false,
    accepted_debt_paths: ["legacy/accepted/**"],
    layer_rules: {
      enabled: false,
      block: true,
      rules: [
        {
          name: "project-domain",
          paths: ["src/domain/**"],
          forbidden_imports: ["src/infrastructure/**"],
        },
      ],
    },
  };
  writeProjectConfig(repo, {
    ...requiredProjectOverrides(path.basename(repo), "preserved-project-secret"),
    risk: { rules: expectedRiskRules },
    structure: expectedStructure,
  });
  const overlayBefore = fs.readFileSync(projectConfigPath(repo));
  writeFile(engineering, fs.readFileSync(engineering, "utf8")
    .replace("# Project Facts", "# Obsolete workflow rules\n\nRun a full build every time.\n\n# Project Facts"));
  writeFile(path.join(repo, "docs", "legacy", "old-taskbook.md"), "historical\n");
  writeFile(path.join(repo, "docs", "architecture", "system-context.md"), "# System context\n\nKeep me.\n");
  writeFile(path.join(repo, "docs", "architecture", "adr", "0042-project-choice.md"), "# ADR-0042\n\nKeep me.\n");
  writeFile(path.join(repo, "docs", "interfaces", "event-contracts.md"), "# Events\n\nKeep me.\n");
  writeFile(path.join(repo, "docs", "project", "operations.md"), "# Project operations\n\nKeep me.\n");
  const projectAssets = new Map([
    ["docs/architecture/diagrams/system.svg", Buffer.from("<svg>architecture</svg>\n")],
    ["docs/bugs/attachments/trace.bin", Buffer.from([0, 1, 2, 255])],
    ["docs/deployment/assets/values.yaml", Buffer.from("replicas: 2\n")],
    ["docs/design/T0055-login-comparison.png", Buffer.from([137, 80, 78, 71, 0, 255])],
    ["docs/interfaces/schemas/event.json", Buffer.from('{"type":"object"}\n')],
    ["docs/project/assets/logo.bin", Buffer.from([10, 20, 30, 40])],
    ["docs/reviews/evidence/chart.svg", Buffer.from("<svg>review</svg>\n")],
    ["docs/testing/fixtures/sample.dat", Buffer.from("fixture\u0000bytes")],
  ]);
  for (const [relative, bytes] of projectAssets) writeFile(path.join(repo, relative), bytes);
  writeFile(path.join(repo, "docs", "legacy", "orphan.bin"), Buffer.from([7, 8, 9]));
  const skillFeedback = path.join(repo, "docs", "skill-feedback", "reports", "2026-07-18-review-timeout-a13f82c1.md");
  const skillFeedbackContent = "project-owned feedback bytes\n";
  writeFile(skillFeedback, skillFeedbackContent);
  writeFile(structureStandard, customStructureStandard);
  writeFile(path.join(repo, ".agents", "agents", "custom.toml"), 'name = "custom"\n');
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "obsolete.txt"), "obsolete\n");

  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryActions = JSON.parse(dryRun.stdout).results[0].actions;
  for (const [relative, bytes] of projectAssets) {
    assert(!dryActions.some(item => item.path === relative && item.action === "would-delete"), `${relative}: dry-run must preserve project-owned assets`);
    assert(fs.readFileSync(path.join(repo, relative)).equals(bytes), `${relative}: dry-run must preserve bytes`);
  }

  run("node", [cli, "init"], { cwd: repo });
  const installedDocs = listProjectFiles(path.join(repo, "docs"))
    .map(file => path.relative(repo, file).split(path.sep).join("/"))
    .sort();
  const expectedInstalledDocs = [
    ...exactDocs,
    "docs/architecture/adr/0042-project-choice.md",
    "docs/architecture/system-context.md",
    "docs/interfaces/event-contracts.md",
    "docs/project/auto-coding-skill.yaml",
    "docs/project/operations.md",
    "docs/skill-feedback/reports/2026-07-18-review-timeout-a13f82c1.md",
    ...projectAssets.keys(),
  ].sort();
  assert(JSON.stringify(installedDocs) === JSON.stringify(expectedInstalledDocs), `docs framework must converge while preserving valid artifacts: ${installedDocs.join(", ")}`);
  const converged = fs.readFileSync(engineering, "utf8");
  const convergedConfig = readEffectiveConfig(repo);
  assert(convergedConfig.access?.project?.frontend?.password === "preserved-project-secret", "project access values must survive init in the overlay");
  assert(!converged.includes("preserved-project-secret"), "managed ENGINEERING must not retain project access values");
  assert(!converged.includes("Run a full build every time"), "legacy workflow text must be removed");
  assert(canonicalJson(convergedConfig.risk?.rules) === canonicalJson(expectedRiskRules), "project risk.rules must survive init path-for-path");
  for (const [key, expected] of Object.entries(expectedStructure)) {
    assert(
      canonicalJson(convergedConfig.structure?.[key]) === canonicalJson(expected),
      `supported structure.${key} must survive init`,
    );
  }
  assert(exists(path.join(repo, ".agents", "agents", "custom.toml")), "project-owned custom agents must survive init");
  assert(!exists(path.join(repo, ".agents", "skills", "auto-coding-skill", "obsolete.txt")), "extra Skill files must be removed");
  assert(exists(path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "legacy", "old-taskbook.md")), "removed docs must be archived outside active docs");
  assert(exists(path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "legacy", "orphan.bin")), "unowned legacy binary assets must still be archived");
  assert(fs.readFileSync(structureStandard, "utf8") === customStructureStandard, "init must preserve a project-owned structure standard");
  assert(fs.readFileSync(path.join(repo, "docs", "architecture", "adr", "0042-project-choice.md"), "utf8").includes("Keep me"), "numbered ADR artifacts must survive init");
  assert(fs.readFileSync(path.join(repo, "docs", "architecture", "system-context.md"), "utf8").includes("Keep me"), "architecture artifacts must survive init");
  assert(fs.readFileSync(path.join(repo, "docs", "interfaces", "event-contracts.md"), "utf8").includes("Keep me"), "interface artifacts must survive init");
  assert(fs.readFileSync(path.join(repo, "docs", "project", "operations.md"), "utf8").includes("Keep me"), "project fact documents promised by the manifest must survive init");
  assert(fs.readFileSync(skillFeedback, "utf8") === skillFeedbackContent, "project Skill feedback must survive init byte-for-byte");
  assert(fs.readFileSync(projectConfigPath(repo)).equals(overlayBefore), "init must preserve the project configuration overlay byte-for-byte");
  for (const [relative, bytes] of projectAssets) {
    assert(fs.readFileSync(path.join(repo, relative)).equals(bytes), `${relative}: init must preserve project-owned bytes`);
  }

  run("node", [cli, "init"], { cwd: repo });
  assert(fs.readFileSync(engineering, "utf8") === converged, "repeated init must be byte-idempotent for ENGINEERING.md");
  assert(fs.readFileSync(projectConfigPath(repo)).equals(overlayBefore), "repeated init must preserve the project configuration overlay byte-for-byte");
  assert(fs.readFileSync(structureStandard, "utf8") === customStructureStandard, "repeated init must preserve the project structure standard byte-for-byte");
  assert(fs.readFileSync(skillFeedback, "utf8") === skillFeedbackContent, "repeated init must preserve project Skill feedback byte-for-byte");
  for (const [relative, bytes] of projectAssets) {
    assert(fs.readFileSync(path.join(repo, relative)).equals(bytes), `${relative}: repeated init must preserve project-owned bytes`);
  }
  const secondDocs = listProjectFiles(path.join(repo, "docs"))
    .map(file => path.relative(repo, file).split(path.sep).join("/"))
    .sort();
  assert(JSON.stringify(secondDocs) === JSON.stringify(expectedInstalledDocs), "repeated init must stay idempotent");
}

function testStructureBlockWarningsDefaultsPreserveAndConverge() {
  const repo = tmpdir("structure-block-warnings");
  run("node", [cli, "init"], { cwd: repo });
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const initialized = fs.readFileSync(engineering, "utf8");
  const initializedConfig = readEngineeringConfig(engineering);
  assert(
    initializedConfig.structure?.block_warnings === false,
    "new projects must default structure.block_warnings to false",
  );

  const initialOverrides = readYamlConfig(projectConfigPath(repo)).overrides;
  writeProjectConfig(repo, {
    ...initialOverrides,
    structure: { ...(initialOverrides.structure ?? {}), block_warnings: true },
  });
  const customized = fs.readFileSync(projectConfigPath(repo));

  run("node", [cli, "init"], { cwd: repo });
  const converged = fs.readFileSync(engineering, "utf8");
  assert(
    readEffectiveConfig(repo).structure?.block_warnings === true,
    "init must apply an explicit true project structure.block_warnings override",
  );
  assert(fs.readFileSync(projectConfigPath(repo)).equals(customized), "init must preserve the block_warnings overlay byte-for-byte");
  run("node", [cli, "init"], { cwd: repo });
  assert(
    fs.readFileSync(engineering, "utf8") === converged,
    "repeated init must be byte-idempotent for managed defaults",
  );

  run("node", [cli, "sync", "--projects", repo]);
  const synced = fs.readFileSync(engineering, "utf8");
  assert(
    readEffectiveConfig(repo).structure?.block_warnings === true,
    "sync must preserve an explicit true project structure.block_warnings override",
  );
  assert(synced === converged, "sync must not rewrite a converged block_warnings=true config");
  assert(fs.readFileSync(projectConfigPath(repo)).equals(customized), "sync must preserve the block_warnings overlay byte-for-byte");
  run("node", [cli, "sync", "--projects", repo]);
  assert(
    fs.readFileSync(engineering, "utf8") === synced,
    "repeated sync must be byte-idempotent with block_warnings=true",
  );
}

function testProjectDocumentationSpecialFilesFailBeforeWrites() {
  if (process.platform === "win32") return;
  const repo = tmpdir("docs-special-files");
  run("node", [cli, "init"], { cwd: repo });
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const sentinel = "stale-skill-must-survive-rejected-docs-preflight\n";
  writeFile(skill, sentinel);

  const externalFile = path.join(tmpdir("docs-special-target"), "external.png");
  writeFile(externalFile, "external-target\n");
  const linkedFile = path.join(repo, "docs", "design", "linked.png");
  fs.symlinkSync(externalFile, linkedFile);
  let rejected = run("node", [cli, "sync", "--projects", repo], { check: false });
  assert(rejected.status !== 0 && rejected.stderr.includes("regular non-symlink files"), "project document file symlinks must fail before writes");
  assert(fs.readFileSync(skill, "utf8") === sentinel && fs.readFileSync(externalFile, "utf8") === "external-target\n", "rejected file symlink must not mutate managed or external files");
  fs.unlinkSync(linkedFile);

  const externalDir = tmpdir("docs-special-directory-target");
  const linkedDir = path.join(repo, "docs", "reviews", "linked-assets");
  fs.symlinkSync(externalDir, linkedDir);
  rejected = run("node", [cli, "sync", "--projects", repo], { check: false });
  assert(rejected.status !== 0 && rejected.stderr.includes("regular non-symlink files"), "project document directory symlinks must fail before writes");
  assert(fs.readFileSync(skill, "utf8") === sentinel && fs.readdirSync(externalDir).length === 0, "rejected directory symlink must preserve both roots");
  fs.unlinkSync(linkedDir);

  const fifo = path.join(repo, "docs", "testing", "fixture.pipe");
  run("mkfifo", [fifo]);
  rejected = run("node", [cli, "sync", "--projects", repo], { check: false });
  assert(rejected.status !== 0 && rejected.stderr.includes("regular non-symlink files"), "project document FIFOs must fail before writes");
  assert(fs.readFileSync(skill, "utf8") === sentinel, "rejected special files must preserve managed bytes");
  fs.unlinkSync(fifo);
}

function testManagedPolicySummaryPreservesProjectConfiguration() {
  const repo = tmpdir("managed-policy-summary");
  run("node", [cli, "init"], { cwd: repo });
  fs.unlinkSync(projectConfigPath(repo));
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const current = fs.readFileSync(engineering, "utf8");
  const neutralSummary = "- `structure` and `optimization`: managed defaults that the project overlay may\n  replace explicitly.";
  const legacySummary = "- `structure` and `optimization`: advisory architecture and no-new-debt policy.";
  const installedOldDefault = current
    .replace(/^  skill_version:.*$/m, "  skill_version: 4.2.5")
    .replace("managed-workflow:start version=4.3.4", "managed-workflow:start version=4.2.5")
    .replace(neutralSummary, legacySummary);
  installTrustedEngineeringDefault(repo, installedOldDefault, "4.2.5");
  const customized = current
    .replace(/^  skill_version:.*$/m, "  skill_version: 4.2.5")
    .replace("managed-workflow:start version=4.3.4", "managed-workflow:start version=4.2.5")
    .replace(neutralSummary, legacySummary)
    .replace(/^  enforcement:.*$/m, "  enforcement: blocking")
    .replace("  block_warnings: false", "  block_warnings: true")
    .replace("    block: false", "    block: true")
    .replace(/^  completion_policy:.*$/m, "  completion_policy: baseline-aware")
    .replace("  require_baseline_for_global_review: false", "  require_baseline_for_global_review: true")
    .replace("  report_accepted_debt_as_findings: false", "  report_accepted_debt_as_findings: true");
  assert(customized !== current && customized.includes(legacySummary), "fixture must represent the 4.2.5 managed summary");
  writeFile(engineering, customized);
  const beforeUpgrade = readEngineeringConfig(engineering);
  assert(beforeUpgrade.workflow?.skill_version === "4.2.5", "fixture must identify the previous workflow version");
  assert(beforeUpgrade.structure?.enforcement === "blocking", "fixture must enable blocking structure enforcement");
  assert(beforeUpgrade.optimization?.completion_policy === "baseline-aware", "fixture must enable baseline-aware completion");

  run("node", [cli, "init"], { cwd: repo });
  const upgraded = fs.readFileSync(engineering, "utf8");
  const managedAfterUpgrade = readEngineeringConfig(engineering);
  const afterUpgrade = readEffectiveConfig(repo);
  assert(managedAfterUpgrade.workflow?.skill_version === "4.3.4", "init must upgrade the managed workflow version");
  assert(canonicalJson(afterUpgrade.structure) === canonicalJson(beforeUpgrade.structure), "init must preserve the complete project structure policy");
  assert(canonicalJson(afterUpgrade.optimization) === canonicalJson(beforeUpgrade.optimization), "init must preserve the complete project optimization policy");
  assert(upgraded.includes(neutralSummary), "upgraded managed text must defer to frontmatter policy");
  assert(!upgraded.includes(legacySummary), "upgraded managed text must remove the hard-coded default policy description");

  const migratedOverlay = fs.readFileSync(projectConfigPath(repo));
  run("node", [cli, "init"], { cwd: repo });
  assert(fs.readFileSync(engineering, "utf8") === upgraded, "repeated init must be byte-idempotent after the policy-summary upgrade");
  assert(fs.readFileSync(projectConfigPath(repo)).equals(migratedOverlay), "repeated init must preserve the migrated project policy overlay byte-for-byte");
}

function testInitRejectsMissingPythonRuntimeBeforeWrites() {
  if (process.platform === "win32") return;
  const repo = tmpdir("missing-python-runtime");
  const fakePython = path.join(repo, "python-without-yaml");
  writeFile(fakePython, "#!/bin/sh\necho 'No module named yaml' >&2\nexit 1\n");
  fs.chmodSync(fakePython, 0o755);
  const result = run("node", [cli, "init"], {
    cwd: repo,
    check: false,
    env: { AUTOCODING_PYTHON: fakePython },
  });
  assert(result.status !== 0, "init should fail when its Python runtime cannot import PyYAML");
  assert(result.stderr.includes("Python runtime dependency check failed"), "init should identify the runtime dependency failure");
  assert(result.stderr.includes("requirements.txt") && result.stderr.includes("Then rerun autocoding init"), "init should print one deterministic recovery command");
  assert(!exists(path.join(repo, ".agents")), "runtime preflight must fail before writing .agents");
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

function testMinimalInitConvergesWithinBudget() {
  const repo = tmpdir("minimal-sync");
  run("node", [cli, "init"], { cwd: repo });

  for (const rel of exactDocs) {
    assert(exists(path.join(repo, rel)), `missing core scaffold file: ${rel}`);
  }
  for (const rel of ["docs/tasks/taskbook.md", "docs/tasks/closure-log.md", "docs/tools/autopipeline/core.py", "docs/tools/autopipeline/http_checks.py"]) {
    assert(!exists(path.join(repo, rel)), `optional/duplicate file should not be installed: ${rel}`);
  }

  const files = listProjectFiles(repo);
  const lines = files.reduce((total, file) => total + fs.readFileSync(file, "utf8").split(/\r?\n/).length, 0);
  assert(files.length <= 40, `minimal scaffold file budget exceeded: ${files.length}`);
  // Integrity, staging, fail-closed classification, immutable Reviewer snapshots,
  // bounded runtime supervision, failure-evidence binding, immutable one-shot
  // Reviewer migration audits, contract helpers,
  // effective-config overlay parsing/migration, release-aware metadata-only
  // feedback lifecycle collection, and the language-aware structure scanner are executable
  // support code, not prompt context. Keep a measured ceiling while leaving
  // safety checks readable.
  assert(lines <= 21250, `minimal scaffold line budget exceeded: ${lines}`);
  const engineering = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"), "utf8");
  const managedConfig = readEngineeringConfig(path.join(repo, "docs", "ENGINEERING.md"));
  assert(managedConfig.workflow?.profile === "auto", "engineering should enable adaptive profiles");
  assert(managedConfig.concurrency?.isolation === "adaptive", "engineering should default to adaptive clean-branch/worktree isolation");
  assert(managedConfig.workflow?.completion === "push", "engineering should complete normal development at push");
  assert(managedConfig.commands?.project_fast === "", "generic projects should expose an optional project-fast command");
  assert(managedConfig.validation?.max_command_seconds === 120, "engineering should bound each final route command");
  assert(managedConfig.validation?.max_total_seconds === 180, "engineering should bound the complete final gate");
  assert(readYamlConfig(projectConfigPath(repo)).overrides?.project?.name === path.basename(repo), "project name should be initialized in the project-owned overlay");
  assert(managedConfig.project?.name === "", "managed ENGINEERING must keep the neutral project-name default");
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
  assert(reviewer.includes("agent-result-template"), "reviewer should use the complete result skeleton");
  assert(reviewer.includes("AUTOCODING_REVIEW_ASSIGNMENT"), "reviewer should receive the supervised assignment path");
  assert(reviewer.includes("150 秒"), "reviewer should enforce the focused review budget");
  assert(agentsProtocol.includes("ap.py review-run"), "AGENTS should use the supervised Reviewer runtime");
  assert(agentsProtocol.includes("review-runtime-override"), "AGENTS should document the audited runtime bypass");
  assert(agentsProtocol.includes("cannot stop an in-app subagent"), "AGENTS should state the supervision boundary honestly");
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

function testSkillFeedbackTemplatesAndReportsSurviveSync() {
  const repo = tmpdir("skill-feedback-sync");
  run("node", [cli, "init"], { cwd: repo });
  fillRequiredAccess(repo);
  const feedbackReadme = path.join(repo, "docs", "skill-feedback", "README.md");
  const feedbackTemplate = path.join(repo, "docs", "skill-feedback", "_TEMPLATE-SKILL-FEEDBACK.md");
  const report = path.join(repo, "docs", "skill-feedback", "reports", "2026-07-18-installer-gap-a13f82c1.md");
  const reportBytes = Buffer.from("project-owned\u0000feedback\n", "utf8");
  fs.mkdirSync(path.dirname(report), { recursive: true });
  fs.writeFileSync(report, reportBytes);
  assert(exists(feedbackReadme) && exists(feedbackTemplate), "init must install managed Skill feedback guidance and template");

  writeFile(feedbackReadme, "managed template drift\n");
  const dry = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryResult = JSON.parse(dry.stdout).results[0];
  assert(
    dryResult.actions.some(item => item.path === "docs/skill-feedback/README.md" && item.action === "would-replace"),
    "sync dry-run must report managed feedback template drift",
  );
  assert(fs.readFileSync(feedbackReadme, "utf8") === "managed template drift\n", "sync dry-run must not write feedback templates");
  assert(fs.readFileSync(report).equals(reportBytes), "sync dry-run must not touch project feedback reports");

  run("node", [cli, "sync", "--projects", repo, "--json"]);
  assert(fs.readFileSync(feedbackReadme, "utf8").includes("Auto Coding Skill Feedback"), "sync must restore the managed feedback README");
  assert(fs.readFileSync(report).equals(reportBytes), "sync must preserve project feedback reports byte-for-byte");
  assertStatusOk(repo);

  if (process.platform !== "win32") {
    const external = path.join(tmpdir("feedback-managed-symlink"), "external.md");
    const installedSkill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
    const skillBefore = fs.readFileSync(installedSkill);
    writeFile(external, "external must not change\n");
    fs.unlinkSync(feedbackReadme);
    fs.symlinkSync(external, feedbackReadme);
    const unsafeInit = run("node", [cli, "init"], { cwd: repo, check: false });
    assert(unsafeInit.status !== 0 && unsafeInit.stderr.includes("non-symlink"), "init must reject a managed feedback template symlink before writes");
    assert(fs.readFileSync(external, "utf8") === "external must not change\n", "init must never follow a managed feedback template symlink");
    assert(fs.readFileSync(installedSkill).equals(skillBefore), "managed feedback symlink preflight must happen before install writes");
    fs.unlinkSync(feedbackReadme);
    run("node", [cli, "init"], { cwd: repo });
    assert(fs.readFileSync(report).equals(reportBytes), "feedback report must survive repair of a managed template symlink");

    const parentLinkRepo = tmpdir("feedback-managed-parent-symlink");
    const externalDir = tmpdir("feedback-managed-parent-external");
    run("node", [cli, "init"], { cwd: parentLinkRepo });
    const parentInstalledSkill = path.join(parentLinkRepo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
    const parentSkillBefore = fs.readFileSync(parentInstalledSkill);
    fs.rmSync(path.join(parentLinkRepo, "docs", "skill-feedback"), { recursive: true, force: true });
    fs.symlinkSync(externalDir, path.join(parentLinkRepo, "docs", "skill-feedback"));
    const unsafeParentInit = run("node", [cli, "init"], { cwd: parentLinkRepo, check: false });
    assert(unsafeParentInit.status !== 0 && unsafeParentInit.stderr.includes("real directory"), "init must reject a symlink in the managed feedback parent chain");
    assert(fs.readdirSync(externalDir).length === 0, "init must not write through a managed feedback parent symlink");
    assert(fs.readFileSync(parentInstalledSkill).equals(parentSkillBefore), "parent symlink preflight must happen before install writes");
  }
}

function testStatusRejectsLegacyIsolation() {
  const repo = tmpdir("legacy-isolation-status");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  fillRequiredAccess(repo);
  const overrides = readYamlConfig(projectConfigPath(repo)).overrides;
  writeProjectConfig(repo, {
    ...overrides,
    concurrency: { ...(overrides.concurrency ?? {}), isolation: "legacy" },
  });

  const result = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(result.status !== 0, "status must reject legacy isolation");
  const parsed = JSON.parse(result.stdout).results[0];
  assert(
    parsed.invalidConfigTokens.includes("concurrency.isolation (must be adaptive or worktree)"),
    `status should identify the invalid isolation value: ${result.stdout}`,
  );
  assert(parsed.next.includes("autocoding init"), "status should direct legacy projects through authoritative init");
}

function testStatusRejectsLegacyGateEscalation() {
  const repo = tmpdir("legacy-gate-status");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const overrides = readYamlConfig(projectConfigPath(repo)).overrides;
  writeProjectConfig(repo, {
    ...overrides,
    gate: {
      full_on_unknown: "true",
      full_on: ["prod_config"],
      rules: [{ match: ["Jenkinsfile"], scope: "full", commands: ["gate_full"] }],
    },
  });
  const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(status.status === 2, "legacy automatic gate escalation must make status non-zero");
  const invalid = JSON.parse(status.stdout).results[0].invalidConfigTokens;
  for (const expected of ["gate.full_on", "gate.full_on_unknown", "gate.rules[0].scope", "gate.rules[0].commands"]) {
    assert(invalid.some(item => item.includes(expected)), `status should report ${expected}: ${status.stdout}`);
  }
}

function testStatusAcceptsValidIndentlessYamlRoutes() {
  const repo = tmpdir("indentless-routes");
  run("node", [cli, "init"], { cwd: repo });
  fillRequiredAccess(repo);
  const overlay = projectConfigPath(repo);
  const parsed = readYamlConfig(overlay);
  const text = renderYaml(parsed);
  assert(/^    routes:\r?\n    - /m.test(text), "fixture must use a valid indentless YAML route sequence");
  writeFile(overlay, text);
  const status = run("node", [cli, "status", "--projects", repo, "--json"]);
  assert(JSON.parse(status.stdout).results[0].ok === true, "valid indentless YAML routes must not be reported as empty");
}

function testOrdinaryNodeTestIsNotPromotedToAutomaticGate() {
  const repo = tmpdir("node-gate-inference");
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  const effective = readEffectiveConfig(repo);
  assert(effective.commands?.project_fast === "", "ordinary test must not be promoted to the project-fast command");
  assert(effective.commands?.gate_standard === undefined, "ordinary test must not seed an automatic standard gate");
  assert(effective.commands?.gate_full === undefined, "ordinary test must not seed an automatic full gate");

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

  const overlay = projectConfigPath(repo);
  const missingPassword = readYamlConfig(overlay).overrides;
  missingPassword.access.project.frontend.password = "";
  missingPassword.access.project.frontend.password_env = "PROJECT_FRONTEND_PASSWORD";
  writeProjectConfig(repo, missingPassword);
  const missing = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(missing.status !== 0, "an environment reference must not replace the required direct password");
  assert(JSON.parse(missing.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), "status should name the missing direct password field");
  assert(!missing.stdout.includes(secret), "failed status JSON must not echo other configured passwords");
  assert(!JSON.parse(missing.stdout).results[0].next.includes("upgrade"), "present but blank fields should not trigger a no-op upgrade recommendation");

  fillRequiredAccess(repo);
  const validOverlaySource = fs.readFileSync(overlay, "utf8");
  for (const yamlValue of ["false", "[]", "{}", "2026-07-13", "0x10", "|"]) {
    const invalid = validOverlaySource.replace('"password": "local-dev-password"', `"password": ${yamlValue}`);
    assert(invalid !== validOverlaySource, `${yamlValue}: fixture must replace one overlay password`);
    writeFile(overlay, invalid);
    const nonString = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
    assert(JSON.parse(nonString.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), `YAML non-string ${yamlValue} must not count as a credential string: ${nonString.stdout}`);
  }
  writeFile(overlay, validOverlaySource.replace('"password": "local-dev-password"', '"password": "TO\\u0044O"'));
  const escapedPlaceholder = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(JSON.parse(escapedPlaceholder.stdout).results[0].missingConfigTokens.includes("access.project.frontend.password"), "escaped YAML placeholders must be decoded before validation");

  const absentOverrides = readYamlConfig(overlay).overrides;
  delete absentOverrides.access;
  writeProjectConfig(repo, absentOverrides);
  const absent = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  const absentStatus = JSON.parse(absent.stdout).results[0];
  assert(absentStatus.unfilledConfigTokens.includes("access.project.frontend.password"), `status must retain its redacted required-field summary: ${absent.stdout}`);
  assert(absentStatus.invalidConfigTokens.some(item => item.includes("access.project.frontend.password") && item.includes("explicitly filled string")), `status must consume the complete doctor contract: ${absent.stdout}`);
  assert(absentStatus.next.includes("doctor"), `invalid effective configuration must direct the user through doctor: ${absent.stdout}`);
}

function testProjectConfigOverlayMigratesLegacyEngineeringAndStaysByteStable() {
  const repo = tmpdir("project-config-migration");
  const secret = "legacy-overlay-secret-6e2f";
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  const overlay = projectConfigPath(repo);
  assert(exists(overlay), "new project init must create the project-owned config overlay");
  const initializedOverlay = readYamlConfig(overlay);
  assert(initializedOverlay.schema === projectConfigSchema, "new project overlay must use the versioned schema");
  assert(initializedOverlay.overrides?.project?.name === path.basename(repo), "new project overlay must own the inferred project name");

  // Simulate the last pre-overlay release: project values lived directly in the
  // otherwise managed ENGINEERING frontmatter and no overlay existed yet.
  fs.unlinkSync(overlay);
  fillLegacyEngineeringAccess(repo, secret);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const current = fs.readFileSync(engineering, "utf8");
  const legacy = current
    .replace(/^  name:.*$/m, '  name: "legacy-specialized-project"')
    .replace(/^  stack:.*$/m, '  stack: "node-go-specialized"')
    .replace(/^  target_branch:.*$/m, '  target_branch: "dev"')
    .replace(/^  cleanup_merged: true$/m, "  cleanup_merged: 1")
    .replace(/^  max_command_seconds: 120$/m, "  max_command_seconds: 120.0")
    .replace(/^risk:\r?\n  rules: \[\]$/m, [
      "risk:",
      "  rules:",
      "    - name: project-device-credentials",
      "      paths: [src/device-credentials/**]",
      "      profile: high-risk",
      "      review: required",
    ].join("\n"))
    .replace(/^structure:\r?\n  enabled: true$/m, "structure:\n  enabled: false")
    .replace(/^  block_warnings: false$/m, "  block_warnings: true")
    .replace(/^    block: false$/m, "    block: 0")
    .replace(/^  api_docs_required: false$/m, "  api_docs_required: true");
  assert(legacy !== current, "legacy migration fixture must contain project-specific frontmatter changes");
  writeFile(engineering, legacy);

  run("node", [cli, "init"], { cwd: repo });
  const migrated = readYamlConfig(overlay);
  assert(migrated.schema === projectConfigSchema, "migration must create the current project overlay schema");
  assert(migrated.overrides?.project?.name === "legacy-specialized-project", "migration must extract project.name from legacy ENGINEERING");
  assert(migrated.overrides?.project?.stack === "node-go-specialized", "migration must extract the project stack");
  assert(migrated.overrides?.concurrency?.target_branch === "dev", "migration must extract the target branch");
  assert(migrated.overrides?.concurrency?.cleanup_merged === 1, "migration must distinguish integer 1 from boolean true");
  assert(migrated.overrides?.validation?.max_command_seconds === 120, "migration must retain the numeric timeout value");
  assert(migrated.overrides?.access?.project?.frontend?.password === secret, "migration must extract project access without printing it");
  assert(migrated.overrides?.risk?.rules?.[0]?.name === "project-device-credentials", "migration must extract project risk rules");
  assert(migrated.overrides?.structure?.enabled === false && migrated.overrides?.structure?.block_warnings === true, "migration must extract explicit project structure policy");
  assert(migrated.overrides?.structure?.layer_rules?.block === 0, "migration must distinguish integer 0 from boolean false");
  assert(migrated.overrides?.docs?.api_docs_required === true, "migration must extract project documentation policy");
  assert(migrated.overrides?.workflow?.skill_version === undefined, "migration must never copy the managed Skill version into project overrides");
  const migratedOverlaySource = fs.readFileSync(overlay, "utf8");
  assert(migratedOverlaySource.includes("max_command_seconds: 120.0"), "migration must distinguish float 120.0 from integer 120");

  const managed = readEngineeringConfig(engineering);
  assert(managed.project?.name === "" && managed.project?.stack === "generic", "ENGINEERING must converge to managed defaults after migration");
  assert(managed.access?.project?.frontend?.password === "", "ENGINEERING must no longer retain project access after migration");
  assert(managed.risk?.rules?.length === 0 && managed.structure?.enabled === true, "ENGINEERING policy defaults must remain release-owned");
  const effective = readEffectiveConfig(repo);
  assert(effective.project?.name === "legacy-specialized-project", "effective config must retain the migrated project identity");
  assert(effective.concurrency?.cleanup_merged === 1, "effective config must preserve integer 1 instead of restoring boolean true");
  assert(effective.structure?.layer_rules?.block === 0, "effective config must preserve integer 0 instead of restoring boolean false");
  assert(effective.access?.project?.frontend?.password === secret, "effective config must retain migrated access values");
  assert(effective.docs?.api_docs_required === true, "effective config must apply migrated project overrides");
  assert(effective.docs?.api_change_log === "docs/interfaces/api-change-log.md", "fields absent from the legacy project config must inherit the new managed default");

  const stableOverlay = fs.readFileSync(overlay);
  const stableEngineering = fs.readFileSync(engineering);
  run("node", [cli, "init"], { cwd: repo });
  assert(fs.readFileSync(overlay).equals(stableOverlay), "repeated init must preserve the project overlay byte-for-byte");
  assert(fs.readFileSync(engineering).equals(stableEngineering), "repeated init must keep the managed default document stable");
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(overlay).equals(stableOverlay), "sync must preserve the project overlay byte-for-byte");
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(overlay).equals(stableOverlay), "repeated sync must preserve the project overlay byte-for-byte");
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(overlay).equals(stableOverlay), "transactional sync must preserve an existing project overlay byte-for-byte");
}

function testProjectConfigOverlayMergeKeepsExplicitFalseZeroEmptyAndList() {
  const repo = tmpdir("project-config-merge");
  run("node", [cli, "init"], { cwd: repo });
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const managedDefault = fs.readFileSync(engineering, "utf8");
  const base = managedDefault
    .replace(/^  target_branch: (?:(?:""|'')|null)$/m, '  target_branch: "release-default"')
    .replace(/^risk:\r?\n  rules: \[\]$/m, [
      "risk:",
      "  rules:",
      "    - name: new-managed-default",
      "      paths: [managed-default/**]",
      "      profile: high-risk",
      "      review: required",
    ].join("\n"))
    .replace(/^structure:\r?\n  enabled: true$/m, "structure:\n  enabled: true\n  max_file_lines_warn: 777")
    .replace(/^  api_docs_required: false$/m, "  api_docs_required: true");
  writeFile(engineering, base);
  writeProjectConfig(repo, {
    project: { name: "explicit-overlay-values" },
    concurrency: { target_branch: "" },
    risk: { rules: [] },
    structure: { enabled: false, max_file_lines_warn: 0 },
  });

  const effective = readEffectiveConfig(repo);
  assert(effective.project?.name === "explicit-overlay-values", "project scalar must override the managed default");
  assert(effective.structure?.enabled === false, "explicit false must override a true managed default");
  assert(effective.structure?.max_file_lines_warn === 0, "explicit zero must not fall back to a non-zero managed default");
  assert(effective.concurrency?.target_branch === "", "explicit empty string must override a non-empty managed default");
  assert(Array.isArray(effective.risk?.rules) && effective.risk.rules.length === 0, "explicit empty list must replace the managed list instead of merging it");
  assert(effective.docs?.api_docs_required === true, "an unoverridden field must inherit a new managed default");

  const overlay = projectConfigPath(repo);
  const stableOverlay = fs.readFileSync(overlay);
  writeFile(engineering, managedDefault);
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(overlay).equals(stableOverlay), "managed convergence must never normalize or rewrite an existing valid overlay");
  const convergedEffective = readEffectiveConfig(repo);
  assert(convergedEffective.structure?.enabled === false && convergedEffective.structure?.max_file_lines_warn === 0, "project scalar overrides must survive managed convergence");
  assert(convergedEffective.concurrency?.target_branch === "" && convergedEffective.risk?.rules?.length === 0, "project empty values must survive managed convergence");
}

function testOversizedLegacyMigrationFailsBeforeCreatingAnInvalidOverlay() {
  const repo = tmpdir("project-config-oversized-migration");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  const overlay = projectConfigPath(repo);
  fs.unlinkSync(overlay);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const current = fs.readFileSync(engineering, "utf8");
  const oversized = current.replace(
    /^project:\r?\n/m,
    `project:\n  oversized_legacy_value: ${JSON.stringify("x".repeat(140 * 1024))}\n`,
  );
  assert(oversized !== current, "oversized legacy migration fixture must modify managed frontmatter");
  writeFile(engineering, oversized);
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const manifest = path.join(repo, ".agents", "managed-install.json");
  const before = {
    engineering: fs.readFileSync(engineering),
    skill: fs.readFileSync(skill),
    manifest: fs.readFileSync(manifest),
  };

  const failed = run("node", [cli, "init"], { cwd: repo, check: false });
  const output = `${failed.stdout}\n${failed.stderr}`;
  assert(failed.status !== 0 && output.includes("exceeds its size limit"), `oversized migrated overlay must fail before writes: ${output}`);
  assert(!exists(overlay), "installer must not create an overlay that violates its own size contract");
  assert(fs.readFileSync(engineering).equals(before.engineering), "oversized migration failure must preserve legacy ENGINEERING bytes");
  assert(fs.readFileSync(skill).equals(before.skill), "oversized migration failure must not switch the installed Skill");
  assert(fs.readFileSync(manifest).equals(before.manifest), "oversized migration failure must not replace the install manifest");
}

function testInvalidProjectConfigOverlayFailsBeforeAnyWrites() {
  const invalidCases = [
    {
      name: "null",
      content: `${JSON.stringify({ schema: projectConfigSchema, overrides: { structure: { enabled: null } } }, null, 2)}\n`,
      hints: ["null"],
    },
    {
      name: "duplicate",
      content: [
        `schema: ${projectConfigSchema}`,
        "overrides:",
        "  project:",
        "    name: duplicate-one",
        "    name: duplicate-two",
        "",
      ].join("\n"),
      hints: ["duplicate"],
    },
    {
      name: "alias",
      content: [
        `schema: ${projectConfigSchema}`,
        "overrides:",
        "  project: &shared_project",
        "    name: alias-project",
        "  docs: *shared_project",
        "",
      ].join("\n"),
      hints: ["alias", "anchor"],
    },
  ];
  for (const invalid of invalidCases) {
    const repo = tmpdir(`project-config-invalid-${invalid.name}`);
    run("node", [cli, "init"], { cwd: repo });
    const overlay = projectConfigPath(repo);
    writeFile(overlay, invalid.content);
    const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
    writeFile(skill, `must-stay-${invalid.name}\n`);
    const engineeringBefore = fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md"));
    const result = run("node", [cli, "init"], { cwd: repo, check: false });
    const output = `${result.stdout}\n${result.stderr}`.toLowerCase();
    assert(result.status !== 0, `${invalid.name}: invalid project overlay must reject init`);
    assert(invalid.hints.some(hint => output.includes(hint)), `${invalid.name}: failure must identify the unsafe YAML construct: ${output}`);
    assert(fs.readFileSync(skill, "utf8") === `must-stay-${invalid.name}\n`, `${invalid.name}: overlay validation must happen before managed Skill writes`);
    assert(fs.readFileSync(path.join(repo, "docs", "ENGINEERING.md")).equals(engineeringBefore), `${invalid.name}: overlay validation must happen before managed document writes`);
    assert(fs.readFileSync(overlay, "utf8") === invalid.content, `${invalid.name}: rejected init must not rewrite the project overlay`);
  }

  const batchFirst = tmpdir("project-config-invalid-batch-first");
  const batchSecond = tmpdir("project-config-invalid-batch-second");
  run("node", [cli, "init"], { cwd: batchFirst });
  run("node", [cli, "init"], { cwd: batchSecond });
  const firstSkill = path.join(batchFirst, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  writeFile(firstSkill, "batch-must-stay\n");
  writeFile(projectConfigPath(batchSecond), invalidCases[0].content);
  const batch = run("node", [cli, "sync", "--projects", `${batchFirst},${batchSecond}`], { check: false });
  assert(batch.status !== 0, "one invalid overlay must reject the complete multi-project sync batch");
  assert(fs.readFileSync(firstSkill, "utf8") === "batch-must-stay\n", "multi-project overlay preflight must run before writing an earlier valid project");
  assert(fs.readFileSync(projectConfigPath(batchSecond), "utf8") === invalidCases[0].content, "multi-project rejection must not rewrite the invalid overlay");

  if (process.platform !== "win32") {
    const repo = tmpdir("project-config-invalid-symlink");
    run("node", [cli, "init"], { cwd: repo });
    const overlay = projectConfigPath(repo);
    const external = path.join(tmpdir("project-config-external"), "outside.yaml");
    const externalBytes = `${JSON.stringify({ schema: projectConfigSchema, overrides: { project: { name: "outside" } } }, null, 2)}\n`;
    writeFile(external, externalBytes);
    fs.unlinkSync(overlay);
    fs.symlinkSync(external, overlay);
    const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
    writeFile(skill, "must-stay-symlink\n");
    const result = run("node", [cli, "sync", "--projects", repo], { check: false });
    const output = `${result.stdout}\n${result.stderr}`.toLowerCase();
    assert(result.status !== 0 && (output.includes("symlink") || output.includes("non-symlink")), "overlay symlink must reject sync before writes");
    assert(fs.readFileSync(skill, "utf8") === "must-stay-symlink\n", "overlay symlink preflight must happen before managed Skill writes");
    assert(fs.readFileSync(external, "utf8") === externalBytes, "overlay validation must never follow or rewrite a symlink target");
    assert(fs.lstatSync(overlay).isSymbolicLink(), "rejected sync must leave the project-owned symlink untouched");
  }
}

function testStatusRejectsManagedAgentSymlinksWithoutLeakingExternalContent() {
  if (process.platform === "win32") return;
  for (const target of ["agents-directory", "agents-parent"]) {
    const repo = tmpdir(`status-agent-symlink-${target}`);
    const secret = `UNIQUE_STATUS_AGENT_SYMLINK_SECRET_${target}_7f42`;
    run("node", [cli, "init"], { cwd: repo });
    fillRequiredAccess(repo);
    const agentsRoot = path.join(repo, ".agents");
    const agentsDir = path.join(agentsRoot, "agents");

    if (target === "agents-directory") {
      const external = path.join(tmpdir("status-external-agents-directory"), "agents");
      fs.mkdirSync(external);
      writeFile(path.join(external, "explorer.toml"), `description = ${JSON.stringify(secret)}\n`);
      fs.rmSync(agentsDir, { recursive: true });
      fs.symlinkSync(external, agentsDir);
    } else {
      const external = path.join(tmpdir("status-external-agents-parent"), "agents-root");
      fs.renameSync(agentsRoot, external);
      fs.appendFileSync(path.join(external, "agents", "explorer.toml"), `\n# ${secret}\n`);
      fs.symlinkSync(external, agentsRoot);
    }

    const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
    const output = `${status.stdout}\n${status.stderr}`;
    assert(status.status !== 0, `${target}: status must reject a managed-agent path that escapes through a symlink`);
    assert(!output.includes(secret), `${target}: status must never echo content read from the external symlink target: ${output}`);
    assert(/symlink|junction|real directory|non-directory/i.test(output), `${target}: status must explain the unsafe managed target shape: ${output}`);
  }
}

function testMultiProjectSyncRejectsManagedTargetSymlinksBeforeAnyProjectWrite() {
  if (process.platform === "win32") return;
  for (const target of ["parent", "leaf"]) {
    const first = tmpdir(`managed-target-batch-first-${target}`);
    const second = tmpdir(`managed-target-batch-second-${target}`);
    run("node", [cli, "init"], { cwd: first });
    run("node", [cli, "init"], { cwd: second });

    const firstProtected = [
      path.join(first, ".agents", "skills", "auto-coding-skill", "SKILL.md"),
      path.join(first, ".agents", "managed-install.json"),
      path.join(first, ".agents", "agents", "explorer.toml"),
      path.join(first, "docs", "ENGINEERING.md"),
    ];
    writeFile(firstProtected[0], `first-project-zero-write-sentinel-${target}\n`);
    const before = new Map(firstProtected.map(file => [file, fs.readFileSync(file)]));
    const secret = `UNIQUE_BATCH_MANAGED_TARGET_SECRET_${target}_98d1`;
    const external = path.join(tmpdir(`managed-target-external-${target}`), "target");
    let linked;
    let externalFile;
    if (target === "parent") {
      fs.mkdirSync(external);
      externalFile = path.join(external, "explorer.toml");
      writeFile(externalFile, `description = ${JSON.stringify(secret)}\n`);
      linked = path.join(second, ".agents", "agents");
      fs.rmSync(linked, { recursive: true });
      fs.symlinkSync(external, linked);
    } else {
      externalFile = external;
      writeFile(external, `description = ${JSON.stringify(secret)}\n`);
      linked = path.join(second, ".agents", "agents", "explorer.toml");
      fs.unlinkSync(linked);
      fs.symlinkSync(external, linked);
    }

    const sync = run("node", [cli, "sync", "--projects", `${first},${second}`], { check: false });
    const output = `${sync.stdout}\n${sync.stderr}`;
    assert(sync.status !== 0, `${target}: one unsafe managed target must reject multi-project sync`);
    assert(/symlink|junction|non-directory/i.test(output), `${target}: batch rejection must identify the unsafe target shape: ${output}`);
    assert(!output.includes(secret), `${target}: batch rejection must not echo the external managed-target content: ${output}`);
    for (const file of firstProtected) {
      assert(fs.readFileSync(file).equals(before.get(file)), `${target}: second-project preflight failure must leave first project untouched: ${path.relative(first, file)}`);
    }
    assert(fs.lstatSync(linked).isSymbolicLink(), `${target}: rejected batch must leave the unsafe second-project link untouched`);
    assert(fs.readFileSync(externalFile, "utf8").includes(secret), `${target}: rejected batch must leave the external target untouched`);
  }
}

function testTamperedInstalledDefaultRejectsInitAndSyncWithoutWrites() {
  const repo = tmpdir("project-config-tampered-old-default");
  run("node", [cli, "init"], { cwd: repo });
  const overlay = projectConfigPath(repo);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const installedTemplate = path.join(
    repo,
    ".agents",
    "skills",
    "auto-coding-skill",
    "data",
    "templates",
    "ENGINEERING.md",
  );
  const manifest = path.join(repo, ".agents", "managed-install.json");
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const oldDefault = fs.readFileSync(engineering, "utf8")
    .replace(/^  skill_version:.*$/m, '  skill_version: "4.2.7"')
    .replace("managed-workflow:start version=4.3.4", "managed-workflow:start version=4.2.7");
  installTrustedEngineeringDefault(repo, oldDefault, "4.2.7");
  writeFile(engineering, oldDefault);
  fs.unlinkSync(overlay);
  fillLegacyEngineeringAccess(repo, "tampered-old-default-secret");
  fs.appendFileSync(installedTemplate, "\n# untrusted template mutation\n");
  writeFile(skill, "tampered-template-zero-write-sentinel\n");

  const protectedPaths = [engineering, installedTemplate, manifest, skill];
  for (const args of [["init"], ["sync", "--projects", repo]]) {
    const before = new Map(protectedPaths.map(file => [file, fs.readFileSync(file)]));
    const result = run("node", [cli, ...args], { cwd: repo, check: false });
    const output = `${result.stdout}\n${result.stderr}`;
    assert(result.status !== 0, `${args[0]} must reject a tampered installed old default`);
    assert(output.includes("managed manifest identity check"), `${args[0]} must identify the untrusted installed template: ${output}`);
    for (const file of protectedPaths) {
      assert(fs.readFileSync(file).equals(before.get(file)), `${args[0]} must perform zero writes before rejecting ${path.relative(repo, file)}`);
    }
    assert(!exists(overlay), `${args[0]} must not create an overlay from an untrusted installed default`);
  }
}

function testExistingOverlayConflictRejectsInitAndSyncWithoutWrites() {
  const repo = tmpdir("project-config-existing-conflict");
  run("node", [cli, "init"], { cwd: repo });
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const overlay = projectConfigPath(repo);
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const conflicting = fs.readFileSync(engineering, "utf8")
    .replace(/^  name:.*$/m, '  name: "legacy-conflicting-name"');
  writeFile(engineering, conflicting);
  writeFile(skill, "overlay-conflict-zero-write-sentinel\n");

  const protectedPaths = [engineering, overlay, skill, path.join(repo, ".agents", "managed-install.json")];
  for (const args of [["init"], ["sync", "--projects", repo]]) {
    const before = new Map(protectedPaths.map(file => [file, fs.readFileSync(file)]));
    const result = run("node", [cli, ...args], { cwd: repo, check: false });
    const output = `${result.stdout}\n${result.stderr}`;
    assert(result.status !== 0, `${args[0]} must reject legacy values that conflict with an existing overlay`);
    assert(output.includes("overlay conflicts with legacy project configuration"), `${args[0]} must explain the conflicting ownership boundary: ${output}`);
    for (const file of protectedPaths) {
      assert(fs.readFileSync(file).equals(before.get(file)), `${args[0]} must perform zero writes before rejecting ${path.relative(repo, file)}`);
    }
  }
}

function testExistingOverlayLegacyDeletionRejectsInitAndSyncWithoutWrites() {
  const repo = tmpdir("project-config-existing-deletion");
  run("node", [cli, "init"], { cwd: repo });
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const overlay = projectConfigPath(repo);
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  const current = fs.readFileSync(engineering, "utf8");
  const deletedDefault = current.replace(/^  api_change_log: "docs\/interfaces\/api-change-log\.md"\r?\n/m, "");
  assert(deletedDefault !== current, "legacy deletion fixture must remove one managed default key");
  writeFile(engineering, deletedDefault);
  writeFile(skill, "legacy-deletion-zero-write-sentinel\n");

  const protectedPaths = [engineering, overlay, skill, path.join(repo, ".agents", "managed-install.json")];
  for (const args of [["init"], ["sync", "--projects", repo]]) {
    const before = new Map(protectedPaths.map(file => [file, fs.readFileSync(file)]));
    const result = run("node", [cli, ...args], { cwd: repo, check: false });
    const output = `${result.stdout}\n${result.stderr}`;
    assert(result.status !== 0, `${args[0]} must reject a legacy deletion that additive overrides cannot represent`);
    assert(output.includes("cannot be represented as additive overrides"), `${args[0]} must explain the deleted-default ambiguity: ${output}`);
    for (const file of protectedPaths) {
      assert(fs.readFileSync(file).equals(before.get(file)), `${args[0]} must perform zero writes before rejecting ${path.relative(repo, file)}`);
    }
  }
}

function testLiveInstallTransactionRejectsSecondInstallerWithoutWrites() {
  const repo = tmpdir("live-install-owner");
  run("node", [cli, "init"], { cwd: repo });
  const installedAp = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  writeFile(installedAp, "live-owner-sentinel\n");

  const first = spawn(
    process.execPath,
    [cli, "sync", "--projects", repo],
    {
      cwd: repo,
      env: {
        ...process.env,
        AUTOCODING_TEST_HOLD_PHASE: "after-stage-copy",
        AUTOCODING_TEST_HOLD_MILLISECONDS: "5000",
      },
      stdio: "ignore",
    },
  );
  const transaction = path.join(repo, ".agents", ".auto-coding-skill-install-transaction");
  const statePath = path.join(transaction, "state.json");
  const sleep = new Int32Array(new SharedArrayBuffer(4));
  const stagedDeadline = Date.now() + 10000;
  while (!exists(statePath) && Date.now() < stagedDeadline) Atomics.wait(sleep, 0, 0, 5);
  assert(exists(statePath), "first installer must publish a durable state before the concurrency check");
  const owner = JSON.parse(fs.readFileSync(path.join(transaction, "owner.json"), "utf8"));
  assert(owner.pid === first.pid, "transaction owner lease must bind the live installer pid");

  const protectedPaths = [
    installedAp,
    path.join(repo, ".agents", "managed-install.json"),
    path.join(repo, "docs", "ENGINEERING.md"),
    projectConfigPath(repo),
  ];
  const beforeSecond = new Map(protectedPaths.map(file => [file, fs.readFileSync(file)]));
  const second = run("node", [cli, "sync", "--projects", repo], { cwd: repo, check: false });
  const secondOutput = `${second.stdout}\n${second.stderr}`;
  assert(second.status !== 0, "a second installer must reject a live install transaction");
  assert(secondOutput.includes("install transaction is active under owner pid"), `live-owner rejection must be explicit: ${secondOutput}`);
  assert(exists(transaction), "second installer must not remove the live transaction");
  for (const file of protectedPaths) {
    assert(fs.readFileSync(file).equals(beforeSecond.get(file)), `second installer must perform zero canonical writes: ${path.relative(repo, file)}`);
  }

  const waitForCompletion = [
    "const fs = require('node:fs');",
    "const target = process.argv[1];",
    "const sleep = new Int32Array(new SharedArrayBuffer(4));",
    "const deadline = Date.now() + 15000;",
    "while (fs.existsSync(target) && Date.now() < deadline) Atomics.wait(sleep, 0, 0, 10);",
    "process.exit(fs.existsSync(target) ? 2 : 0);",
  ].join("\n");
  const completed = run(process.execPath, ["-e", waitForCompletion, transaction], { check: false });
  first.kill();
  assert(completed.status === 0, "live owner must finish normally after the rejected second installer");
  assert(!fs.readFileSync(installedAp, "utf8").includes("live-owner-sentinel"), "the live owner must retain control and finish its own upgrade");
}

function testStagedRuntimeTamperingIsRejectedBeforeExecution() {
  const repo = tmpdir("staged-runtime-tamper");
  run("node", [cli, "init"], { cwd: repo });

  // Keep beginInstallTransaction busy after it has hashed new-skill. The
  // watcher uses old-skill creation as the deterministic signal that this
  // binding has already happened, then changes the staged runtime.
  const installedSkill = path.join(repo, ".agents", "skills", "auto-coding-skill");
  fs.writeFileSync(path.join(installedSkill, "zzzz-staging-delay.bin"), Buffer.alloc(32 * 1024 * 1024, 0x61));
  const installedAp = path.join(installedSkill, "scripts", "ap.py");
  const installedBefore = fs.readFileSync(installedAp);
  const transaction = path.join(repo, ".agents", ".auto-coding-skill-install-transaction");
  const oldSkill = path.join(transaction, "old-skill");
  const stagedAp = path.join(transaction, "new-skill", "scripts", "ap.py");
  const ready = path.join(repo, "attacker-ready");
  const tampered = path.join(repo, "staged-runtime-tampered");
  const executed = path.join(repo, "tampered-runtime-executed");
  const malicious = [
    "from pathlib import Path",
    `Path(${JSON.stringify(executed)}).write_text('executed', encoding='utf-8')`,
    "print('{}')",
    "",
  ].join("\n");
  const watcher = [
    "const fs = require('node:fs');",
    "const [oldSkill, stagedAp, ready, tampered, malicious] = process.argv.slice(1);",
    "fs.writeFileSync(ready, 'ready');",
    "const deadline = Date.now() + 15000;",
    "const sleep = new Int32Array(new SharedArrayBuffer(4));",
    "while (Date.now() < deadline) {",
    "  if (fs.existsSync(oldSkill) && fs.existsSync(stagedAp)) {",
    "    fs.writeFileSync(stagedAp, Buffer.from(malicious, 'base64'));",
    "    fs.writeFileSync(tampered, 'tampered');",
    "    process.exit(0);",
    "  }",
    "  Atomics.wait(sleep, 0, 0, 1);",
    "}",
    "process.exit(3);",
  ].join("\n");
  const attacker = spawn(
    process.execPath,
    ["-e", watcher, oldSkill, stagedAp, ready, tampered, Buffer.from(malicious).toString("base64")],
    { stdio: "ignore" },
  );
  const sleep = new Int32Array(new SharedArrayBuffer(4));
  const readyDeadline = Date.now() + 5000;
  while (!exists(ready) && Date.now() < readyDeadline) Atomics.wait(sleep, 0, 0, 5);
  assert(exists(ready), "staged-runtime tamper watcher must start before sync");

  const result = run("node", [cli, "sync", "--projects", repo], { cwd: repo, check: false });
  attacker.kill();
  const output = `${result.stdout}\n${result.stderr}`;
  assert(exists(tampered), `test watcher must alter the staged runtime: ${output}`);
  assert(result.status !== 0, "transaction must reject a staged runtime changed after its binding hash");
  assert(output.includes("staged Skill failed its transaction identity check"), `tamper failure must identify the staged Skill binding: ${output}`);
  assert(!exists(executed), "tampered staged ap.py must never execute");
  assert(fs.readFileSync(installedAp).equals(installedBefore), "pre-switch tamper rejection must leave the installed runtime unchanged");
  assert(exists(path.join(transaction, "state.json")), "tamper rejection must retain the verified rollback transaction");
}

function testInterruptedStagedInstallRecoversForInitAndSync() {
  const cases = [
    {
      name: "init-after-config-finalize",
      phase: "after-config-finalize",
      args() { return ["init"]; },
    },
    {
      name: "sync-after-runtime-switch",
      phase: "after-runtime-switch",
      args(repo) { return ["sync", "--projects", repo]; },
    },
  ];

  for (const interrupted of cases) {
    const repo = tmpdir(`staged-recovery-${interrupted.name}`);
    const projectName = `specialized-${interrupted.name}`;
    const projectStack = `stack-${interrupted.name}`;
    const secret = `secret-${interrupted.name}`;
    run("node", [cli, "init"], { cwd: repo });

    // Exercise the migration/finalize boundary: prepare must first extract
    // these project-owned values from a legacy managed document into a new
    // overlay, and recovery must never normalize or lose that overlay.
    fs.unlinkSync(projectConfigPath(repo));
    fillLegacyEngineeringAccess(repo, secret);
    const engineering = path.join(repo, "docs", "ENGINEERING.md");
    const specialized = fs.readFileSync(engineering, "utf8")
      .replace(/^  name:.*$/m, `  name: ${JSON.stringify(projectName)}`)
      .replace(/^  stack:.*$/m, `  stack: ${JSON.stringify(projectStack)}`)
      .replace(/^  target_branch:.*$/m, '  target_branch: "dev"')
      .replace(/^  api_docs_required: false$/m, "  api_docs_required: true");
    writeFile(engineering, specialized);

    const args = interrupted.args(repo);
    const failed = run("node", [cli, ...args], {
      cwd: repo,
      check: false,
      env: { AUTOCODING_TEST_FAIL_PHASE: interrupted.phase },
    });
    const failedOutput = `${failed.stdout}\n${failed.stderr}`;
    assert(failed.status !== 0, `${interrupted.name}: injected staged install must fail`);
    assert(failedOutput.includes(`injected auto-coding-skill install fault: ${interrupted.phase}`), `${interrupted.name}: failure must identify the injected phase: ${failedOutput}`);

    const transaction = path.join(repo, ".agents", ".auto-coding-skill-install-transaction");
    assert(exists(transaction), `${interrupted.name}: interrupted install must retain its recovery transaction`);
    const overlay = projectConfigPath(repo);
    assert(exists(overlay), `${interrupted.name}: prepare must durably create the project overlay before runtime switching`);
    const overlayAfterFailure = fs.readFileSync(overlay);
    const migrated = readYamlConfig(overlay).overrides;
    assert(migrated.project?.name === projectName && migrated.project?.stack === projectStack, `${interrupted.name}: interrupted prepare must preserve specialized project values`);
    assert(migrated.access?.project?.frontend?.password === secret, `${interrupted.name}: interrupted prepare must preserve specialized access values`);

    run("node", [cli, ...args], { cwd: repo });
    assert(fs.readFileSync(overlay).equals(overlayAfterFailure), `${interrupted.name}: retry recovery must preserve overlay bytes exactly`);
    const effective = readEffectiveConfig(repo);
    assert(effective.project?.name === projectName && effective.project?.stack === projectStack, `${interrupted.name}: recovered effective config must retain specialized project identity`);
    assert(effective.concurrency?.target_branch === "dev", `${interrupted.name}: recovered effective config must retain the specialized target branch`);
    assert(effective.access?.project?.frontend?.password === secret, `${interrupted.name}: recovered effective config must retain specialized access values`);
    assert(effective.docs?.api_docs_required === true, `${interrupted.name}: recovered effective config must retain specialized documentation policy`);
    assert(!exists(transaction), `${interrupted.name}: successful retry must remove the active install transaction`);
    const transactionArtifacts = fs.readdirSync(path.join(repo, ".agents"))
      .filter(name => name.startsWith(".auto-coding-skill-install-"));
    assert(transactionArtifacts.length === 0, `${interrupted.name}: successful retry must clean every install transaction artifact: ${transactionArtifacts.join(", ")}`);

    const status = run("node", [cli, "status", "--projects", repo, "--json"]);
    assert(JSON.parse(status.stdout).results[0].ok === true, `${interrupted.name}: recovered installation must be complete and healthy: ${status.stdout}`);
    assert(fs.readFileSync(overlay).equals(overlayAfterFailure), `${interrupted.name}: read-only status must leave overlay bytes stable`);
  }
}

function testArchiveFallbackCollisionsNeverLosePreviousContent() {
  const digest12 = payload => crypto.createHash("sha256").update(payload).digest("hex").slice(0, 12);
  const assertUnchanged = (file, expected, label) => {
    assert(fs.readFileSync(file).equals(expected), `${label}: occupied archive bytes must not be overwritten`);
  };
  const assertPreservedAnywhere = (repo, expected, label) => {
    assert(
      listProjectFiles(repo).some(file => fs.readFileSync(file).equals(expected)),
      `${label}: occupied archive bytes must remain available somewhere in project history`,
    );
  };
  const assertArchived = (directory, expected, label, suffix = false) => {
    const archived = listProjectFiles(directory).some(file => {
      const payload = fs.readFileSync(file);
      if (!suffix) return payload.equals(expected);
      return payload.length >= expected.length
        && payload.subarray(payload.length - expected.length).equals(expected);
    });
    assert(archived, `${label}: previous content must survive default and digest archive collisions`);
  };

  {
    const repo = tmpdir("archive-collision-engineering");
    run("node", [cli, "init"], { cwd: repo });
    fs.unlinkSync(projectConfigPath(repo));
    fillLegacyEngineeringAccess(repo, "archive-collision-secret");
    const engineering = path.join(repo, "docs", "ENGINEERING.md");
    fs.appendFileSync(engineering, "\n## Archive collision sentinel\n\nPreserve these ENGINEERING bytes.\n");
    const previous = fs.readFileSync(engineering);
    const archiveDir = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs");
    const preferred = path.join(archiveDir, "ENGINEERING.md");
    const legacyDigest = path.join(archiveDir, `ENGINEERING-${digest12(previous)}.md`);
    const occupiedPreferred = Buffer.from("occupied-engineering-default\n");
    const occupiedDigest = Buffer.from("occupied-engineering-digest\n");
    writeFile(preferred, occupiedPreferred);
    writeFile(legacyDigest, occupiedDigest);

    run("node", [cli, "init"], { cwd: repo });

    assertUnchanged(preferred, occupiedPreferred, "ENGINEERING default collision");
    assertUnchanged(legacyDigest, occupiedDigest, "ENGINEERING digest collision");
    assertArchived(archiveDir, previous, "ENGINEERING migration", true);
    assert(
      readEffectiveConfig(repo).access?.project?.frontend?.password === "archive-collision-secret",
      "ENGINEERING archive fallback must not disrupt project configuration migration",
    );
  }

  {
    const repo = tmpdir("archive-collision-managed-template");
    run("node", [cli, "init"], { cwd: repo });
    const managed = path.join(repo, "docs", "design", "_TEMPLATE-DD.md");
    const previous = Buffer.from("# Project-specific design template\n\nPreserve these exact bytes.\n");
    fs.writeFileSync(managed, previous);
    const archiveDir = path.join(
      repo,
      ".agents",
      "archive",
      "auto-coding-skill",
      "4.3.4",
      "docs",
      "design",
    );
    const preferred = path.join(archiveDir, "_TEMPLATE-DD.md");
    const legacyDigest = path.join(archiveDir, `_TEMPLATE-DD-${digest12(previous)}.md`);
    const occupiedPreferred = Buffer.from("occupied-template-default\n");
    const occupiedDigest = Buffer.from("occupied-template-digest\n");
    writeFile(preferred, occupiedPreferred);
    writeFile(legacyDigest, occupiedDigest);

    run("node", [cli, "init"], { cwd: repo });

    assertUnchanged(preferred, occupiedPreferred, "managed template default collision");
    assertUnchanged(legacyDigest, occupiedDigest, "managed template digest collision");
    assertArchived(archiveDir, previous, "managed template migration");
    assert(!fs.readFileSync(managed).equals(previous), "managed template must still converge after safe archival");
  }

  {
    const repo = tmpdir("archive-collision-agents-sync");
    run("node", [cli, "init"], { cwd: repo });
    const agents = path.join(repo, "AGENTS.md");
    const previous = Buffer.from("# Project AGENTS before sync\n\nPreserve this sync history.\n");
    fs.writeFileSync(agents, previous);
    const archiveDir = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4");
    const preferred = path.join(archiveDir, "AGENTS.md");
    const legacyDigest = path.join(archiveDir, `AGENTS-${digest12(previous)}.md`);
    const occupiedPreferred = Buffer.from("occupied-sync-default\n");
    const occupiedDigest = Buffer.from("occupied-sync-digest\n");
    writeFile(preferred, occupiedPreferred);
    writeFile(legacyDigest, occupiedDigest);

    run("node", [cli, "sync", "--projects", repo]);

    assertPreservedAnywhere(repo, occupiedPreferred, "sync AGENTS default collision");
    assertPreservedAnywhere(repo, occupiedDigest, "sync AGENTS digest collision");
    assertArchived(archiveDir, previous, "sync AGENTS migration", true);
    assert(!fs.readFileSync(agents).equals(previous), "sync AGENTS must still converge after safe archival");
  }

  {
    const repo = tmpdir("archive-collision-agents-init");
    run("node", [cli, "init"], { cwd: repo });
    const agents = path.join(repo, "AGENTS.md");
    const previous = Buffer.from("# Project AGENTS before init\n\nPreserve this init history.\n");
    fs.writeFileSync(agents, previous);
    const archiveDir = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4");
    const preferred = path.join(archiveDir, "AGENTS.md");
    const legacyDigest = path.join(archiveDir, `AGENTS-${digest12(previous)}.md`);
    const occupiedPreferred = Buffer.from("occupied-init-default\n");
    const occupiedDigest = Buffer.from("occupied-init-digest\n");
    writeFile(preferred, occupiedPreferred);
    writeFile(legacyDigest, occupiedDigest);

    run("node", [cli, "init"], { cwd: repo });

    assertUnchanged(preferred, occupiedPreferred, "init AGENTS default collision");
    assertUnchanged(legacyDigest, occupiedDigest, "init AGENTS digest collision");
    assertArchived(archiveDir, previous, "init AGENTS migration");
    assert(!fs.readFileSync(agents).equals(previous), "init AGENTS must still converge after safe archival");
  }
}

function testProjectMutationAndInstallSwitchRejectParentSwap() {
  if (process.platform === "win32") return;

  const assertExternalUntouched = (external, sentinel, label) => {
    const files = listProjectFiles(external);
    assert(files.length === 1 && files[0] === sentinel, `${label}: project mutation must not create external files`);
    assert(fs.readFileSync(sentinel, "utf8") === "external-sentinel\n", `${label}: external sentinel must remain unchanged`);
  };
  const restoreParent = (target, backup) => {
    assert(fs.lstatSync(target).isSymbolicLink(), `swap fixture must leave a symlink at ${target}`);
    fs.unlinkSync(target);
    fs.renameSync(backup, target);
  };

  {
    const repo = tmpdir("project-file-parent-swap");
    run("node", [cli, "init"], { cwd: repo });
    const external = tmpdir("project-file-parent-swap-external");
    const sentinel = path.join(external, "sentinel.txt");
    writeFile(sentinel, "external-sentinel\n");
    const parent = path.join(repo, ".agents", "agents");
    const backup = path.join(repo, ".agents", "agents.autocoding-test-backup");
    const failed = run("node", [cli, "init"], {
      cwd: repo,
      check: false,
      env: {
        AUTOCODING_TEST_MODE: "1",
        AUTOCODING_TEST_PROJECT_FILE_SWAP_PATH: ".agents/agents/browser-debugger.toml",
        AUTOCODING_TEST_PROJECT_FILE_SWAP_EXTERNAL: external,
        AUTOCODING_TEST_PROJECT_FILE_SWAP_BACKUP: backup,
      },
    });
    const output = `${failed.stdout}\n${failed.stderr}`;
    assert(failed.status !== 0 && output.includes("Project path parent changed"), `project file parent swap must fail closed: ${output}`);
    assertExternalUntouched(external, sentinel, "project file parent swap");
    restoreParent(parent, backup);
    run("node", [cli, "init"], { cwd: repo });
    assertExternalUntouched(external, sentinel, "project file parent swap recovery");
  }

  {
    const repo = tmpdir("install-switch-parent-swap");
    run("node", [cli, "init"], { cwd: repo });
    const external = tmpdir("install-switch-parent-swap-external");
    const sentinel = path.join(external, "sentinel.txt");
    writeFile(sentinel, "external-sentinel\n");
    const parent = path.join(repo, ".agents", "skills");
    const backup = path.join(repo, ".agents", "skills.autocoding-test-backup");
    const failed = run("node", [cli, "init"], {
      cwd: repo,
      check: false,
      env: {
        AUTOCODING_TEST_MODE: "1",
        AUTOCODING_TEST_INSTALL_IO_SWAP_PHASE: "switch",
        AUTOCODING_TEST_INSTALL_IO_SWAP_PARENT: ".agents/skills",
        AUTOCODING_TEST_INSTALL_IO_SWAP_EXTERNAL: external,
        AUTOCODING_TEST_INSTALL_IO_SWAP_BACKUP: backup,
      },
    });
    const output = `${failed.stdout}\n${failed.stderr}`;
    assert(failed.status !== 0 && output.includes("Install I/O project parent changed"), `install switch parent swap must fail closed: ${output}`);
    assertExternalUntouched(external, sentinel, "install switch parent swap");
    restoreParent(parent, backup);
    run("node", [cli, "init"], { cwd: repo });
    assertExternalUntouched(external, sentinel, "install switch parent swap recovery");
  }
}

function testNoChangeLightGateRejectsInvalidEffectiveContracts() {
  const cases = [
    {
      name: "risk-rules",
      mutate(overrides) {
        overrides.risk = { rules: { invalid: true } };
      },
      hints: ["risk.rules", "must be a list"],
    },
    {
      name: "validation-route",
      mutate(overrides) {
        overrides.validation = {
          ...(overrides.validation ?? {}),
          routes: [{ name: "invalid-empty-command-route", paths: ["**"], commands: [] }],
        };
      },
      hints: ["validation.routes[0].commands", "must not be empty"],
    },
    {
      name: "validation-budget",
      mutate(overrides) {
        overrides.validation = {
          ...(overrides.validation ?? {}),
          max_command_seconds: 181,
          max_total_seconds: 180,
        };
      },
      hints: ["max_command_seconds", "max_total_seconds"],
    },
  ];

  for (const invalid of cases) {
    const repo = tmpdir(`no-change-light-gate-${invalid.name}`);
    run("node", [cli, "init"], { cwd: repo });
    fillRequiredAccess(repo);
    const overrides = readYamlConfig(projectConfigPath(repo)).overrides;
    invalid.mutate(overrides);
    writeProjectConfig(repo, overrides);
    run("git", ["init", "-q"], { cwd: repo });
    run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
    run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
    run("git", ["add", "-A"], { cwd: repo });
    run("git", ["commit", "-qm", "invalid contract baseline"], { cwd: repo });
    assert(run("git", ["status", "--porcelain"], { cwd: repo }).stdout === "", `${invalid.name}: fixture must have no changed files`);

    const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
    if (invalid.name === "risk-rules") {
      const classify = run("python3", [
        launcher,
        "--repo", repo,
        "classify",
        "--planned-path", "sensitive/example.txt",
        "--json",
      ], { cwd: repo, check: false });
      const classifyOutput = `${classify.stdout}\n${classify.stderr}`;
      assert(classify.status !== 0, "malformed risk.rules must fail classify instead of downgrading a sensitive path");
      assert(classifyOutput.includes("risk.rules must be a list"), `classify must identify malformed risk.rules: ${classifyOutput}`);

      const taskStart = run("python3", [
        launcher,
        "--repo", repo,
        "task-start", "INVALID-RISK-CONTRACT",
        "--owned-path", "sensitive/example.txt",
        "--force-lifecycle",
      ], { cwd: repo, check: false });
      const taskOutput = `${taskStart.stdout}\n${taskStart.stderr}`;
      assert(taskStart.status !== 0, "malformed risk.rules must fail task-start before isolation/review decisions");
      assert(taskOutput.includes("risk.rules must be a list"), `task-start must identify malformed risk.rules: ${taskOutput}`);
    }
    const gate = run("python3", [launcher, "--repo", repo, "light-gate", "--scope", "changed"], { cwd: repo, check: false });
    const output = `${gate.stdout}\n${gate.stderr}`;
    assert(gate.status !== 0, `${invalid.name}: an invalid effective contract must fail light-gate even with no changed files`);
    for (const hint of invalid.hints) {
      assert(output.includes(hint), `${invalid.name}: light-gate must report ${hint}: ${output}`);
    }
  }
}

function testStatusRejectsInvalidStructureEnforcementFromDoctorContract() {
  const repo = tmpdir("invalid-structure-enforcement-status");
  run("node", [cli, "init"], { cwd: repo });
  fillRequiredAccess(repo);
  const overrides = readYamlConfig(projectConfigPath(repo)).overrides;
  writeProjectConfig(repo, {
    ...overrides,
    structure: { ...(overrides.structure ?? {}), enforcement: "strict-but-unknown" },
  });

  const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(status.status !== 0, "status must reject an invalid structure enforcement value");
  const parsed = JSON.parse(status.stdout).results[0];
  assert(
    parsed.invalidConfigTokens.includes("structure.enforcement must be advisory or blocking"),
    `status must expose the structure issue from the complete doctor contract: ${status.stdout}`,
  );
}

function testProjectConfigOverlayIsHighRiskAndReviewRequired() {
  const repo = tmpdir("project-config-classification");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
  run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
  run("git", ["add", "-A"], { cwd: repo });
  run("git", ["commit", "-qm", "baseline"], { cwd: repo });
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  for (const plannedPath of ["docs/ENGINEERING.md", "docs/project/auto-coding-skill.yaml"]) {
    const result = run("python3", [
      launcher,
      "--repo", repo,
      "classify",
      "--planned-path", plannedPath,
      "--intent", `change Skill configuration at ${plannedPath}`,
      "--json",
    ]);
    const parsed = JSON.parse(result.stdout);
    assert(parsed.profile === "high-risk", `${plannedPath} changes must be high-risk: ${result.stdout}`);
    assert(parsed.review_required === true, `${plannedPath} changes must require independent review: ${result.stdout}`);
  }
}

function testStatusAndFeedbackUseEffectiveProjectConfigWithoutLeakingAccess() {
  const repo = tmpdir("project-config-consumers");
  const projectName = "effective-overlay-project";
  const secret = "overlay-access-must-not-leak-c819";
  run("node", [cli, "init"], { cwd: repo });
  writeProjectConfig(repo, requiredProjectOverrides(projectName, secret));
  const engineering = readEngineeringConfig(path.join(repo, "docs", "ENGINEERING.md"));
  assert(engineering.project?.name === "", "managed ENGINEERING must not provide the effective project identity");
  assert(engineering.access?.project?.frontend?.password === "", "managed ENGINEERING must not provide effective access values");

  const status = run("node", [cli, "status", "--projects", repo, "--json"]);
  assert(JSON.parse(status.stdout).results[0].ok === true, `status must validate the effective overlay configuration: ${status.stdout}`);
  assert(!status.stdout.includes(secret), "status must never print access values loaded from the project overlay");

  const signature = `sha256:${"c".repeat(64)}`;
  const report = path.join(repo, "docs", "skill-feedback", "reports", "2026-07-18-effective-config-c819a2e4.md");
  writeFile(report, [
    "---",
    "schema: auto-coding-skill-feedback/v1",
    "report_id: ACSF-effective-20260718-c819a2e4",
    "status: open",
    'created_at: "2026-07-18T10:00:00+08:00"',
    `project: ${projectName}`,
    `observed_skill_version: ${engineering.workflow.skill_version}`,
    "component: config-overlay",
    "kind: defect",
    "impact: minor",
    "origin_surface: managed-script",
    "suspected_scope: shared",
    `signature: ${signature}`,
    "export: metadata-only",
    "---",
    "# Effective config consumer",
    "",
    "## Symptom",
    "A consumer ignored the project overlay.",
    "",
    "## Expected",
    "Every consumer uses the effective project configuration.",
    "",
    "## Minimal reproduction",
    "Read this report using the configured project identity.",
    "",
    "## Evidence",
    "The metadata is intentionally non-sensitive.",
    "",
    "## Workaround",
    "None.",
    "",
    "## Why shared",
    "The project-independent consumer is managed by the Skill.",
    "",
  ].join("\n"));
  const feedback = run("node", [cli, "feedback", "--projects", repo, "--json"]);
  const collected = JSON.parse(feedback.stdout);
  assert(collected.projects[0]?.project === projectName, `feedback collection must use effective project.name: ${feedback.stdout}`);
  assert(collected.report_count === 1 && collected.metadata[0]?.project === projectName, "feedback metadata must retain the effective project identity");
  assert(!feedback.stdout.includes(secret), "feedback collection must never print access values loaded from the project overlay");
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
  assert(fs.readFileSync(custom, "utf8") === customText, "init must preserve agents outside the managed set");
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
  assert(exists(path.join(repo, "AGENTS.md")), "generic bridge should be created");
  const bridge = fs.readFileSync(path.join(repo, "AGENTS.md"), "utf8");
  assert(bridge.includes("Every delegated fixer or parallel writer owns a task ID/worktree"), "bridge should expose delegated-writer isolation");
  assert(bridge.includes("integrates in dependency order"), "bridge should expose dependency ordering");
  for (const filename of [`CO${"DEX.md"}`, `CLA${"UDE.md"}`]) {
    assert(!exists(path.join(repo, filename)), "client-named bridge should not be created");
  }
}

function testSyncCleansAllManagedSkillExtras() {
  const repo = tmpdir("sync-extra");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--force"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "data", "templates", "bridges", "OLD.md"), "old\n");
  writeFile(path.join(repo, ".agents", "skills", "auto-coding-skill", "custom.txt"), "custom\n");
  run("node", [cli, "sync", "--projects", repo]);
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
  fillRequiredAccess(repo);
  const drift = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(drift.status !== 0, "extra runtime copies must be reported as drift");
  run("node", [cli, "init"], { cwd: repo });
  assert(!exists(path.join(repo, "docs", "tools", "autopipeline", "core.py")), "legacy runtime copy must be removed");
  assert(!exists(path.join(repo, "docs", "tools", "autopipeline", "http_checks.py")), "legacy HTTP copy must be removed");
  assert(fs.readFileSync(path.join(repo, "docs", "interfaces", "api.md"), "utf8") === "# Existing API\n", "mutable project docs must survive init");
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

function testBaselineUpdateConfigWritesOnlyProjectOverlay() {
  const repo = tmpdir("baseline-project-overlay-only");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  run("git", ["config", "user.email", "test@example.com"], { cwd: repo });
  run("git", ["config", "user.name", "Auto Coding Test"], { cwd: repo });
  writeFile(path.join(repo, "src", "large-module.js"), "export const line = 1;\n".repeat(801));
  run("git", ["add", "-A"], { cwd: repo });
  run("git", ["commit", "-qm", "baseline source"], { cwd: repo });

  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const overlay = projectConfigPath(repo);
  const engineeringBefore = fs.readFileSync(engineering);
  const overlayBefore = fs.readFileSync(overlay);
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  const baseline = run("python3", [
    launcher,
    "--repo", repo,
    "baseline", "init",
    "--write",
    "--update-config",
    "--json",
  ]);
  const parsed = JSON.parse(baseline.stdout);

  assert(parsed.updated_accepted_debt_paths.includes("src/large-module.js"), `baseline must discover the tracked large file: ${baseline.stdout}`);
  assert(fs.readFileSync(engineering).equals(engineeringBefore), "baseline --update-config must never modify managed ENGINEERING defaults");
  assert(!fs.readFileSync(overlay).equals(overlayBefore), "baseline --update-config must persist accepted debt in the project overlay");
  assert(readEffectiveConfig(repo).structure?.accepted_debt_paths?.includes("src/large-module.js"), "the overlay update must affect effective accepted_debt_paths");
  const changed = run("git", ["status", "--porcelain"], { cwd: repo }).stdout;
  assert(changed.includes("docs/project/auto-coding-skill.yaml"), `baseline must report the overlay as the changed configuration file: ${changed}`);
  assert(!changed.includes("docs/ENGINEERING.md"), `baseline must not report managed ENGINEERING as changed: ${changed}`);
 }

function testSyncUsesPackagedAssetsAndIgnoresRetiredTemplates() {
  const repo = tmpdir("sync-packaged-source");
  const fakeHome = tmpdir("sync-stale-home");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);

  const projectSkill = path.join(repo, ".agents", "skills", "auto-coding-skill");
  writeFile(path.join(projectSkill, "data", "templates", "docs", "interfaces", "api.md"), "# Retired project template\n");

  const staleGlobal = path.join(fakeHome, ".agents", "skills", "auto-coding-skill");
  writeFile(path.join(staleGlobal, "scripts", "ap.py"), "# legacy runtime\n");
  writeFile(path.join(staleGlobal, "data", "templates", "ENGINEERING.md"), "---\n---\n");
  writeFile(path.join(staleGlobal, "data", "templates", "docs", "interfaces", "api.md"), "# Retired global template\n");

  run("node", [cli, "sync", "--projects", repo], { env: pythonEnvWithHome(fakeHome) });
  assert(!exists(path.join(projectSkill, "data", "templates", "docs", "interfaces", "api.md")), "transactional sync must replace retired files in the managed Skill namespace");
  assert(fs.readFileSync(path.join(repo, "docs", "interfaces", "api.md"), "utf8").startsWith("# API Contract"), "transactional sync must not replace the canonical API doc with a retired physical template");
}

function testInitInitializesNewEngineeringDefaults() {
  const repo = tmpdir("init-engineering-defaults");
  run("git", ["init", "-q"], { cwd: repo });
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test", "test:changed": "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });

  const effective = readEffectiveConfig(repo);
  assert(effective.project?.name === path.basename(repo), "init should initialize a newly created project name in the overlay");
  assert(effective.commands?.project_fast === "npm run test:changed", "init should infer only a dedicated changed-scope test in the overlay");
  assert(effective.commands?.gate_standard === undefined, "init must not infer an automatic standard gate");
  assert(effective.commands?.gate_full === undefined, "init must not infer an automatic full gate");
}

function testInitMigratesLegacyAutomaticGateToFastDefault() {
  const repo = tmpdir("init-legacy-fast-gate");
  run("git", ["init", "-q"], { cwd: repo });
  writeFile(path.join(repo, "package.json"), JSON.stringify({ scripts: { test: "node --test" } }, null, 2) + "\n");
  run("node", [cli, "init"], { cwd: repo });
  fs.unlinkSync(projectConfigPath(repo));
  const legacyEngineering = [
    "---",
    "workflow:",
    '  skill_version: "4.2.8"',
    "  mode: dev",
    "  profile: auto",
    "  completion: push",
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
  ].join("\n");
  writeFile(path.join(repo, "docs", "ENGINEERING.md"), legacyEngineering);
  const legacyInstalledDefault = legacyEngineering
    .replace('  name: "legacy"', '  name: ""')
    .replace("  base_ref: origin/dev", '  base_ref: ""')
    .replace("  target_branch: dev", '  target_branch: ""');
  installTrustedEngineeringDefault(repo, legacyInstalledDefault, "4.2.8");

  run("node", [cli, "init"], { cwd: repo });
  const managed = readEngineeringConfig(path.join(repo, "docs", "ENGINEERING.md"));
  const effective = readEffectiveConfig(repo);
  assert(effective.commands?.project_fast === "", "init should not promote an ordinary npm test to the project-fast gate");
  assert(managed.workflow?.mode === "dev", "init should retain the managed fast development mode");
  assert(managed.workflow?.completion === "push", "init should retain managed push completion");
  assert(managed.concurrency?.isolation === "adaptive", "init should retain managed adaptive isolation");
  assert(managed.validation?.on_unmapped === "error", "init should retain the fail-closed unmapped default");
  assert(managed.risk?.rules?.length === 0, "init should retain empty managed project-risk defaults");
  assert(effective.project?.name === "legacy" && effective.concurrency?.target_branch === "dev", "init must migrate supported legacy project values into the overlay");
  assert(effective.gate === undefined && effective.commands?.gate_full === undefined, "init must drop removed automatic gate escalation fields");
}

function testRemovedVerificationFlagsFailFast() {
  const repo = tmpdir("removed-verification-flags");
  const result = run("python3", [assetAp, "--repo", repo, "commit-push", "T1", "--msg", "T1: test", "--require-jenkins"], { check: false });
  assert(result.status !== 0 && result.stderr.includes("unrecognized arguments"), "removed post-push verification flags must fail instead of being ignored");
}

function testInstallBootstrapsRuntimeRequiredByLauncher() {
  const repo = tmpdir("install-missing-runtime");
  const fakeHome = tmpdir("install-global-runtime-home");
  const env = pythonEnvWithHome(fakeHome);
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init", "--mode", "global", "--dest", fakeHome, "--force"]);
  const globalAp = path.join(fakeHome, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  run("python3", [globalAp, "--repo", repo, "install"], { env });
  const projectRuntime = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  assert(!exists(projectRuntime), "runtime bootstrap install must continue to rely on the invoking global Skill copy");
  assert(readYamlConfig(projectConfigPath(repo)).overrides?.project?.name === path.basename(repo), "bootstrap install must initialize the project overlay");
  const help = run("python3", [launcher, "--help"], { env });
  assert(help.stdout.includes("autopipeline"), "bootstrapped launcher should remain executable through the invoking runtime");
}

function testCliInstallArchivesFeedbackTemplatesAndPreservesReports() {
  const repo = tmpdir("cli-feedback-ownership");
  run("git", ["init", "-q"], { cwd: repo });
  const feedbackReadme = path.join(repo, "docs", "skill-feedback", "README.md");
  const report = path.join(repo, "docs", "skill-feedback", "reports", "2026-07-18-upgrade-gap-a13f82c1.md");
  const previousReadme = "project content that occupied the future managed feedback README\n";
  const reportContent = "project-owned feedback report bytes\n";
  writeFile(feedbackReadme, previousReadme);
  writeFile(report, reportContent);

  run("node", [cli, "init"], { cwd: repo });
  const archive = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "skill-feedback", "README.md");
  assert(fs.readFileSync(feedbackReadme, "utf8").includes("Auto Coding Skill Feedback"), "transactional init must install the managed feedback README");
  assert(fs.readFileSync(archive, "utf8") === previousReadme, "transactional init must archive a pre-existing feedback README before replacement");
  assert(fs.readFileSync(report, "utf8") === reportContent, "transactional init must preserve project feedback reports byte-for-byte");

  const archiveBefore = fs.readFileSync(archive);
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(archive).equals(archiveBefore), "repeated transactional sync must keep the original feedback archive stable");
  assert(fs.readFileSync(report, "utf8") === reportContent, "repeated transactional sync must keep project feedback reports stable");
}

function testLegacyUpgradeWriteFailsWithoutAnyWrites() {
  const repo = tmpdir("legacy-upgrade-write-rejected");
  run("git", ["init", "-q"], { cwd: repo });
  run("node", [cli, "init"], { cwd: repo });
  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  writeFile(skill, "legacy-upgrade-zero-write-sentinel\n");
  const beforeFiles = listProjectFiles(repo)
    .map(file => [path.relative(repo, file), fs.readFileSync(file)])
    .sort(([left], [right]) => left.localeCompare(right));
  const projectAp = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "ap.py");

  const rejected = run("python3", [projectAp, "--repo", repo, "upgrade", "--write"], { check: false });
  const output = `${rejected.stdout}\n${rejected.stderr}`;
  assert(rejected.status !== 0, "legacy ap.py upgrade --write must be rejected");
  assert(output.includes("retired") && output.includes("autocoding init") && output.includes("autocoding sync"), `legacy write rejection must direct callers to the transactional CLI: ${output}`);
  const afterFiles = listProjectFiles(repo)
    .map(file => [path.relative(repo, file), fs.readFileSync(file)])
    .sort(([left], [right]) => left.localeCompare(right));
  assert(afterFiles.length === beforeFiles.length, "rejected legacy write must not create or delete project files");
  for (let index = 0; index < beforeFiles.length; index += 1) {
    assert(afterFiles[index][0] === beforeFiles[index][0], `rejected legacy write must preserve the file set: ${beforeFiles[index][0]}`);
    assert(afterFiles[index][1].equals(beforeFiles[index][1]), `rejected legacy write must preserve bytes: ${beforeFiles[index][0]}`);
  }
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

function testManagedEngineeringInitIsAuthoritativeAndIdempotent() {
  const repo = tmpdir("managed-engineering");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);

  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  const initial = fs.readFileSync(engineering, "utf8");
  const startPattern = /<!-- auto-coding-skill:managed-workflow:start version=4\.3\.3 -->/;
  const endMarker = "<!-- auto-coding-skill:managed-workflow:end -->";
  assert(startPattern.test(initial), "new projects should include a versioned managed workflow marker");
  assert(initial.includes(endMarker), "new projects should include the managed workflow end marker");

  const customized = initial
    .replace("workflow:\n", "# project-frontmatter-comment\nworkflow:\n")
    .replace(startPattern, "project note before managed workflow\n<!-- auto-coding-skill:managed-workflow:start version=3.0.0 -->")
    .replace(endMarker, `${endMarker}\nproject note after managed workflow`)
    .replace("The frontmatter contract is:", "Stale managed workflow contract:");
  writeFile(engineering, customized);
  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const dryResult = JSON.parse(dryRun.stdout).results[0];
  assert(dryResult.managedWorkflow.state === "stale", `dry-run should expose stale workflow state: ${dryRun.stdout}`);
  assert(dryResult.managedWorkflow.version === "4.3.4", "dry-run should expose the target workflow version");
  assert(dryResult.actions.some(item => item.action === "would-replace" && item.path === "docs/ENGINEERING.md"), "dry-run should plan exact replacement of the managed default document");
  assert(fs.readFileSync(engineering, "utf8") === customized, "dry-run must not write ENGINEERING.md");

  run("node", [cli, "init"], { cwd: repo });
  const updated = fs.readFileSync(engineering, "utf8");
  assert(!updated.includes("project note before") && !updated.includes("project note after"), "init must remove text outside the canonical ENGINEERING body");
  assert(updated.includes("version=4.3.4"), "init should install the current managed workflow version");
  assert(updated.includes("The frontmatter contract is:"), "init should refresh stale managed workflow content");

  fillRequiredAccess(repo);
  const status = run("node", [cli, "status", "--projects", repo, "--json"]);
  const statusResult = JSON.parse(status.stdout).results[0];
  assert(statusResult.managedWorkflow.state === "current", `status should expose current managed workflow state: ${status.stdout}`);
  assert(statusResult.managedWorkflow.version === "4.3.4", "status should expose the installed managed workflow version");

  const beforeSecondInit = fs.readFileSync(engineering, "utf8");
  run("node", [cli, "init"], { cwd: repo });
  assert(fs.readFileSync(engineering, "utf8") === beforeSecondInit, "idempotent init must not rewrite ENGINEERING.md");
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
  assert(dryResult.actions.some(item => item.action === "would-replace" && item.path === "docs/ENGINEERING.md"), "custom legacy migration must plan exact managed replacement");
  assert(dryResult.actions.some(item => item.action === "would-archive" && item.path.endsWith("/docs/ENGINEERING.md")), "custom legacy migration must plan archival before replacement");
  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(engineering, "utf8");
  assert(migrated.includes("version=4.3.4"), "legacy migration should insert the current managed workflow");
  assert(!migrated.includes(legacyNote), "legacy project text must not remain in the exact managed default document");
  const archive = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "ENGINEERING.md");
  assert(fs.readFileSync(archive, "utf8").includes(legacyNote), "legacy migration must preserve the complete previous body in history");
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
  assert(dryResult.actions.some(item => item.action === "would-replace" && item.path === "docs/ENGINEERING.md"), "official legacy migration must plan exact managed replacement");
  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(engineering, "utf8");
  const canonicalEngineering = fs.readFileSync(path.join(repoRoot, "cli", "assets", "skill", "data", "templates", "ENGINEERING.md"), "utf8");
  assert(migrated === canonicalEngineering, "official legacy migration must install the exact managed default document");
  assert((migrated.match(/auto-coding-skill:managed-workflow:start/g) || []).length === 1, "official legacy migration should install exactly one managed workflow");
  assert((migrated.match(/^## Execution profiles$/gm) || []).length === 0, "official legacy migration must remove the old duplicated workflow body");
  const archive = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "ENGINEERING.md");
  assert(fs.readFileSync(archive, "utf8").includes("## Execution profiles"), "official legacy body must remain available in the historical archive");

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
  assert(initial.includes("managed-agents:start version=4.3.4"), "new projects should receive the versioned root AGENTS block");

  const custom = [
    "# Project rules",
    "",
    "- Preserve this repository-specific rule exactly.",
    "- `high-risk` cannot be downgraded and must execute `commands.gate_full`; changed or standard fallbacks do not count. Use `PASS / FAIL / PARTIAL` only from the required executed evidence.",
    "",
  ].join("\n");
  writeFile(agents, custom);
  const legacyActiveArchive = path.join(repo, "docs", "archive", "workflow", "AGENTS.pre-4.3.1.md");
  const legacyActiveArchiveBytes = Buffer.from("# Historical 4.3.1 AGENTS archive\n");
  writeFile(legacyActiveArchive, legacyActiveArchiveBytes);
  const dryRun = run("node", [cli, "sync", "--projects", repo, "--dry-run", "--json"]);
  const plan = JSON.parse(dryRun.stdout).results[0].managedAgentsDocument;
  assert(plan.state === "legacy-custom", `unmarked custom AGENTS should be migrated: ${dryRun.stdout}`);
  assert(plan.migrations.includes("agents-whole-file-replacement"), "AGENTS should use the whole-file convergence migration");
  const dryActions = JSON.parse(dryRun.stdout).results[0].actions;
  assert(dryActions.some(item => item.action === "would-archive"), "dry-run should expose the historical AGENTS archive");

  run("node", [cli, "sync", "--projects", repo]);
  const migrated = fs.readFileSync(agents, "utf8");
  assert(migrated.includes("managed-agents:start version=4.3.4"), "AGENTS migration should install the current managed block");
  assert(!migrated.includes("Preserve this repository-specific rule exactly."), "root AGENTS must contain no project-specific tail");
  assert(!migrated.includes("must execute `commands.gate_full`"), "known official conflicting rule should be removed");
  const canonical = fs.readFileSync(path.join(repoRoot, "cli", "assets", "skill", "data", "templates", "bridges", "AGENTS.md"), "utf8");
  assert(migrated === canonical, "root AGENTS must be byte-identical to the packaged canonical file");
  const archive = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "AGENTS.md");
  assert(fs.readFileSync(archive, "utf8").includes("Preserve this repository-specific rule exactly."), "previous AGENTS content must be archived once");
  assert(!exists(legacyActiveArchive), "legacy active-doc AGENTS archives must leave docs/archive during upgrade");
  const migratedLegacyArchiveDir = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "archive", "workflow");
  assert(
    listProjectFiles(migratedLegacyArchiveDir).some(file => fs.readFileSync(file).equals(legacyActiveArchiveBytes)),
    "legacy active-doc AGENTS archive bytes must survive under the managed archive root",
  );
  const stable = fs.readFileSync(agents);
  run("node", [cli, "sync", "--projects", repo]);
  assert(fs.readFileSync(agents).equals(stable), "managed AGENTS sync should be idempotent");
  fillRequiredAccess(repo);
  const postUpgradeStatus = JSON.parse(run("node", [cli, "status", "--projects", repo, "--json"]).stdout).results[0];
  assert(postUpgradeStatus.ok === true && postUpgradeStatus.docsDiffs.length === 0, "status must be current immediately after AGENTS archive migration");
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
  const secret = "UNIQUE_POLICY_BEARER_SECRET_4d920f7a";
  fs.appendFileSync(secondEngineering, `\nHigh-risk changes must run the real full gate before push. Authorization: Bearer ${secret}\n`);

  const status = run("node", [cli, "status", "--projects", second, "--json"], { check: false });
  assert(status.status !== 0, "status must be non-ok for an unknown conflicting workflow rule");
  assert(!`${status.stdout}\n${status.stderr}`.includes(secret), `status must redact Bearer values from policy-conflict excerpts: ${status.stdout}\n${status.stderr}`);
  const statusPlan = JSON.parse(status.stdout).results[0].managedWorkflow;
  assert(statusPlan.state === "conflict", `status should expose the document conflict: ${status.stdout}`);
  assert(statusPlan.conflicts[0].file === "docs/ENGINEERING.md" && statusPlan.conflicts[0].line > 0, "status conflict should include file and line");

  const launcher = path.join(second, "docs", "tools", "autopipeline", "ap.py");
  const effective = run("python3", [launcher, "--repo", second, "config-effective", "--json"]);
  assert(!`${effective.stdout}\n${effective.stderr}`.includes(secret), `config-effective must redact Bearer values from policy conflicts: ${effective.stdout}\n${effective.stderr}`);
  const effectiveStatus = JSON.parse(effective.stdout);
  assert(effectiveStatus.contract_valid === false && effectiveStatus.policy_issues.length > 0, `config-effective must retain redacted conflict diagnostics: ${effective.stdout}`);

  const sync = run("node", [cli, "sync", "--projects", `${first},${second}`], { check: false });
  assert(sync.status !== 0 && sync.stderr.includes("entire sync batch before writes"), "one unknown conflict must reject the complete batch");
  assert(!`${sync.stdout}\n${sync.stderr}`.includes(secret), `sync preflight must redact Bearer values from conflict diagnostics: ${sync.stdout}\n${sync.stderr}`);
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
  assert(normalized === current, "sync should restore the exact managed document when text is glued to its end marker");
  assert(!normalized.includes("# Project-specific workflow"), "project workflow text must not remain in the managed default document");
  const archive = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "ENGINEERING.md");
  assert(fs.readFileSync(archive, "utf8").includes(`${marker}# Project-specific workflow`), "the malformed previous document must remain available in history");
}

function testEngineeringFrameworkRejectsAnyNonCanonicalWorkflowText() {
  const repo = tmpdir("engineering-framework");
  run("node", [cli, "init"], { cwd: repo });
  run("node", [cli, "sync", "--projects", repo]);
  fillRequiredAccess(repo);
  const engineering = path.join(repo, "docs", "ENGINEERING.md");
  fs.appendFileSync(engineering, "\n# Project Facts\n\n## Repository boundaries\n\n- backend owns APIs.\n");
  const status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  assert(status.status !== 0, "text outside the canonical ENGINEERING body must be drift");
  assert(JSON.parse(status.stdout).results[0].docsDiffs.some(item => item.path === "docs/ENGINEERING.md"), "status should identify ENGINEERING convergence");

  run("node", [cli, "init"], { cwd: repo });
  assert(!fs.readFileSync(engineering, "utf8").includes("backend owns APIs"), "init must restore the canonical ENGINEERING body");
  const archived = path.join(repo, ".agents", "archive", "auto-coding-skill", "4.3.4", "docs", "ENGINEERING.md");
  assert(fs.readFileSync(archived, "utf8").includes("backend owns APIs"), "removed project text should remain in non-authoritative history");
}

function testManagedInstallIntegrityIsBoundedAndRepairable() {
  const repo = tmpdir("managed-integrity");
  const initialized = run("node", [cli, "init"], { cwd: repo });
  assert(initialized.stdout.includes("verify: .agents/managed-install.json"), "init must verify managed files before reporting success");
  fillRequiredAccess(repo);

  const manifestPath = path.join(repo, ".agents", "managed-install.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  assert(manifest.schema_version === 1 && manifest.skill_version === "4.3.4", "installed manifest must identify the release");
  assert(manifest.entries.length > 0, "installed manifest must list managed files");
  for (const entry of manifest.entries) {
    assert(typeof entry.path === "string" && !path.isAbsolute(entry.path) && !entry.path.includes(".."), "manifest paths must be safe relative paths");
    assert(/^[0-9a-f]{64}$/.test(entry.sha256), `${entry.path}: manifest hash must be sha256`);
    assert(entry.version === "4.3.4" && typeof entry.executable === "boolean", `${entry.path}: version/executable metadata missing`);
  }
  assert(!manifest.managed_namespaces.some(item => item.path === ".agents" || item.path === "docs"), "manifest must not mirror entire project-owned trees");

  const customAgent = path.join(repo, ".agents", "agents", "project-specialist.toml");
  const archiveNote = path.join(repo, ".agents", "archive", "owner-note.md");
  const adr = path.join(repo, "docs", "architecture", "adr", "0042-project-choice.md");
  writeFile(customAgent, 'name = "project-specialist"\ndescription = "project owned"\n');
  writeFile(archiveNote, "historical\n");
  writeFile(adr, "# ADR-0042\n\nProject owned.\n");
  assertStatusOk(repo);
  const launcher = path.join(repo, "docs", "tools", "autopipeline", "ap.py");
  run("python3", [launcher, "--repo", repo, "doctor"]);

  const skill = path.join(repo, ".agents", "skills", "auto-coding-skill", "SKILL.md");
  fs.appendFileSync(skill, "\nmanaged drift\n");
  let doctor = run("python3", [launcher, "--repo", repo, "doctor"], { check: false });
  assert(doctor.status !== 0 && `${doctor.stdout}\n${doctor.stderr}`.includes("SKILL.md: managed content drift"), "doctor must identify managed Skill drift");
  run("node", [cli, "init"], { cwd: repo });

  const extraSkill = path.join(repo, ".agents", "skills", "auto-coding-skill", "obsolete.txt");
  writeFile(extraSkill, "obsolete\n");
  let status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  let parsed = JSON.parse(status.stdout).results[0];
  assert(status.status !== 0 && parsed.installIntegrity.errors.some(item => item.includes("unexpected file in managed namespace")), "status must reject extras in the exact Skill namespace");
  run("node", [cli, "init"], { cwd: repo });

  const oldRuntime = path.join(repo, "docs", "tools", "autopipeline", "core.py");
  writeFile(oldRuntime, "# obsolete project runtime copy\n");
  status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  parsed = JSON.parse(status.stdout).results[0];
  assert(status.status !== 0 && parsed.installIntegrity.errors.some(item => item.includes("docs/tools/autopipeline/core.py")), "launcher namespace extras must be drift");
  run("node", [cli, "init"], { cwd: repo });
  assert(!exists(oldRuntime), "init must clean obsolete files from the exact launcher namespace");

  if (process.platform !== "win32") {
    const core = path.join(repo, ".agents", "skills", "auto-coding-skill", "scripts", "core.py");
    fs.chmodSync(core, fs.statSync(core).mode & ~0o111);
    status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
    parsed = JSON.parse(status.stdout).results[0];
    assert(status.status !== 0 && parsed.installIntegrity.errors.some(item => item.includes("core.py: executable bit drift")), "status must detect executable-bit drift");
    run("node", [cli, "init"], { cwd: repo });
    assert((fs.statSync(core).mode & 0o111) !== 0, "init must restore the declared executable bit");
  }

  const explorer = path.join(repo, ".agents", "agents", "explorer.toml");
  writeFile(explorer, fs.readFileSync(explorer, "utf8").replace(/^description\s*=.*$/m, '$&\nmodel = "vendor/project-model"'));
  assertStatusOk(repo);
  writeFile(explorer, fs.readFileSync(explorer, "utf8").replace('model = "vendor/project-model"', "model = []"));
  doctor = run("python3", [launcher, "--repo", repo, "doctor"], { check: false });
  assert(doctor.status !== 0 && `${doctor.stdout}\n${doctor.stderr}`.includes("model must be a non-empty TOML string"), "doctor must reject invalid normalized-agent overrides");
  run("node", [cli, "init"], { cwd: repo });

  const staleManifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  staleManifest.skill_version = "0.0.0";
  writeFile(manifestPath, `${JSON.stringify(staleManifest)}\n`);
  status = run("node", [cli, "status", "--projects", repo, "--json"], { check: false });
  parsed = JSON.parse(status.stdout).results[0];
  assert(status.status !== 0 && parsed.installManifestDiffs.some(item => item.status === "stale"), "status must compare the local manifest with the release manifest");
  doctor = run("python3", [launcher, "--repo", repo, "doctor"], { check: false });
  assert(doctor.status !== 0 && `${doctor.stdout}\n${doctor.stderr}`.includes("manifest version"), "doctor must reject a mismatched local manifest");
  run("node", [cli, "init"], { cwd: repo });

  assert(fs.readFileSync(customAgent, "utf8").includes("project owned"), "init must preserve project-owned custom agents");
  assert(fs.readFileSync(archiveNote, "utf8") === "historical\n", "init must preserve archives untouched");
  assert(fs.readFileSync(adr, "utf8").includes("Project owned"), "init must preserve project-owned documents");
  assertStatusOk(repo);
}

function testSkillFeedbackCollectionIsBoundedReadOnlyAndMetadataOnly() {
  const first = tmpdir("feedback-collect-first");
  const second = tmpdir("feedback-collect-second");
  const third = tmpdir("feedback-collect-empty");
  run("node", [cli, "init"], { cwd: first });
  run("node", [cli, "init"], { cwd: second });
  run("node", [cli, "init"], { cwd: third });
  const emptyStatus = JSON.parse(
    run("node", [cli, "status", "--projects", third, "--json"], { check: false }).stdout,
  ).results[0];
  assert(emptyStatus.feedback.available === true, "status must expose feedback before the first report");
  assert(emptyStatus.feedback.skillVersion === "4.3.4", "empty feedback status must expose the installed Skill version");
  const signature = `sha256:${"a".repeat(64)}`;
  const marker = path.join(os.tmpdir(), `autocoding-feedback-must-not-execute-${crypto.randomUUID()}`);
  const render = (project, reportId, privateMarker) => [
    "---",
    "schema: auto-coding-skill-feedback/v1",
    `report_id: ${reportId}`,
    "status: open",
    'created_at: "2026-07-18T10:00:00+08:00"',
    `project: ${project}`,
    "observed_skill_version: 4.3.4",
    "component: reviewer-runtime",
    "kind: defect",
    "impact: blocking",
    "origin_surface: managed-script",
    "suspected_scope: shared",
    `signature: ${signature}`,
    "export: metadata-only",
    "---",
    "# Reviewer runtime stalls",
    "",
    "## Symptom",
    `${privateMarker}; $(touch ${marker})`,
    "",
    "## Expected",
    "The managed runtime must return before its deadline.",
    "",
    "## Minimal reproduction",
    "Use a synthetic read-only assignment.",
    "",
    "## Evidence",
    "The bounded local fixture reproduced the timeout.",
    "",
    "## Workaround",
    "Use the explicit runtime override only with user authorization.",
    "",
    "## Why shared",
    "Managed runtime behavior reproduces outside project configuration.",
    "",
  ].join("\n");
  const renderV2 = (project, reportId, privateMarker, options) => render(project, reportId, privateMarker)
    .replace("schema: auto-coding-skill-feedback/v1", "schema: auto-coding-skill-feedback/v2")
    .replace("status: open", `status: ${options.status ?? "open"}`)
    .replace('created_at: "2026-07-18T10:00:00+08:00"', 'created_at: "2026-07-18T10:00:00+08:00"\nupdated_at: "2026-07-19T10:00:00+08:00"')
    .replace("observed_skill_version: 4.3.4", `observed_skill_version: ${options.observed ?? "4.3.4"}\nlast_verified_skill_version: ${options.lastVerified ?? options.observed ?? "4.3.4"}`)
    .replace(signature, options.signature)
    .replace("export: metadata-only", `resolution: ${options.resolution ?? "pending"}\nexport: metadata-only`);
  const firstReport = path.join(first, "docs", "skill-feedback", "reports", "2026-07-18-review-timeout-a13f82c1.md");
  const firstOtherReport = path.join(first, "docs", "skill-feedback", "reports", "2026-07-18-installer-gap-c35fa4e3.md");
  const secondReport = path.join(second, "docs", "skill-feedback", "reports", "2026-07-18-review-timeout-b24f93d2.md");
  const closedReport = path.join(third, "docs", "skill-feedback", "reports", "2026-07-18-resolved-gap-d45fa4e3.md");
  const fixedReport = path.join(first, "docs", "skill-feedback", "reports", "2026-07-18-project-assets-fd5748e4.md");
  const rerouteReport = path.join(third, "docs", "skill-feedback", "reports", "2026-07-18-project-policy-a5eeb5eb.md");
  const firstContent = render(path.basename(first), "ACSF-geesight-20260718-a13f82c1", "PRIVATE-BODY-FIRST");
  const firstOtherContent = render(path.basename(first), "ACSF-geesight-20260718-c35fa4e3", "PRIVATE-BODY-OTHER")
    .replaceAll(signature, `sha256:${"b".repeat(64)}`);
  const secondContent = render(path.basename(second), "ACSF-xjmate-20260718-b24f93d2", "PRIVATE-BODY-SECOND");
  const closedContent = render(path.basename(third), "ACSF-closed-20260718-d45fa4e3", "PRIVATE-BODY-CLOSED")
    .replace("status: open", "status: resolved")
    .replaceAll(signature, `sha256:${"d".repeat(64)}`);
  const fixedContent = renderV2(path.basename(first), "ACSF-assets-20260718-fd5748e4", "PRIVATE-BODY-FIXED", {
    signature: "sha256:fd5748e4ae40e9f86762c4f62b3302bbbb2b8ae9661adf9e0e07a2327ccf7a36",
    observed: "4.3.0",
    lastVerified: "4.3.0",
  });
  const rerouteContent = renderV2(path.basename(third), "ACSF-policy-20260718-a5eeb5eb", "PRIVATE-BODY-REROUTE", {
    signature: "sha256:a5eeb5eb0ef5073dbeec726fa6c2016593b43eb1230171e3028f364c5b07bd86",
  });
  writeFile(firstReport, firstContent);
  writeFile(firstOtherReport, firstOtherContent);
  writeFile(secondReport, secondContent);
  writeFile(closedReport, closedContent);
  writeFile(fixedReport, fixedContent);
  writeFile(rerouteReport, rerouteContent);

  const collected = run("node", [cli, "feedback", "--projects", `${first},${second},${third}`, "--json"]);
  const result = JSON.parse(collected.stdout);
  assert(result.schema === "auto-coding-skill-feedback-collection/v2", "feedback collection must identify its active-only grouping schema");
  assert(result.report_count === 6 && result.active_report_count === 3 && result.groups.length === 2, "feedback collection must group only current active reports");
  assert(result.closed_report_count === 1 && result.lifecycle_counts.closed === 1, "closed v1 feedback must remain readable but leave active grouping");
  assert(result.action_required_count === 2, `catalog resolutions must produce bounded project actions: ${collected.stdout}`);
  const fixedAction = result.action_required.find(item => item.report_id === "ACSF-assets-20260718-fd5748e4");
  assert(fixedAction?.lifecycle === "verification-due" && fixedAction.recommended_action.includes("verify-fix"), "a project at the fixed release must verify and close its old report");
  const rerouteAction = result.action_required.find(item => item.report_id === "ACSF-policy-20260718-a5eeb5eb");
  assert(rerouteAction?.lifecycle === "reroute-due" && rerouteAction.recommended_action.includes("docs/project/auto-coding-skill.yaml"), "project preferences must route to the project overlay");
  const statusWithFeedback = run("node", [cli, "status", "--projects", first, "--json"], { check: false });
  const statusFeedback = JSON.parse(statusWithFeedback.stdout).results[0].feedback;
  assert(statusFeedback.available === true && statusFeedback.actionRequiredCount >= 1, "status must surface feedback maintenance without making it installation drift");
  assert(result.projects.length === 3 && result.projects.every(item => item.source_project && item.project), "feedback collection must retain every explicit initialized project, including one with no reports");
  const sharedGroup = result.groups.find(item => item.signature === signature);
  assert(sharedGroup?.cross_project === true && sharedGroup.project_count === 2, "same signature from two explicit roots must be cross-project");
  const localGroup = result.groups.find(item => item.signature === `sha256:${"b".repeat(64)}`);
  assert(localGroup?.cross_project === false && localGroup.project_count === 1, "a separate one-project signature must remain a local candidate group");
  const rawReportDigests = [firstContent, firstOtherContent, secondContent, closedContent, fixedContent, rerouteContent]
    .map(content => crypto.createHash("sha256").update(content).digest("hex"));
  assert(result.metadata.every(item => !("content_sha256" in item) && item.size_bytes > 0), "feedback metadata must not export a hash oracle over private report bodies");
  assert(rawReportDigests.every(digest => !collected.stdout.includes(digest)), "collector output must not expose raw report body digests");
  assert(!collected.stdout.includes("PRIVATE-BODY") && !collected.stdout.includes("touch"), "collector output must never include report bodies");
  assert(!collected.stdout.includes(first) && !collected.stdout.includes(second) && !collected.stdout.includes(third), "collector output must not expose absolute project roots");
  assert(!exists(marker), "collector must never execute report content");
  assert(fs.readFileSync(firstReport, "utf8") === firstContent && fs.readFileSync(firstOtherReport, "utf8") === firstOtherContent && fs.readFileSync(secondReport, "utf8") === secondContent, "collection must not modify reports");
  assert(fs.readFileSync(closedReport, "utf8") === closedContent && fs.readFileSync(fixedReport, "utf8") === fixedContent && fs.readFileSync(rerouteReport, "utf8") === rerouteContent, "lifecycle collection must preserve every project-owned report byte-for-byte");

  writeFile(fixedReport, fixedContent.replace("last_verified_skill_version: 4.3.0", "last_verified_skill_version: 4.3.3"));
  let lifecycleCheck = JSON.parse(run("node", [cli, "feedback", "--projects", first, "--json"]).stdout);
  assert(lifecycleCheck.metadata.find(item => item.report_id === "ACSF-assets-20260718-fd5748e4")?.lifecycle === "regression-current", "a fixed signature reproduced on the fixed release must re-enter active triage as a regression");
  writeFile(fixedReport, fixedContent);

  writeFile(firstOtherReport, firstOtherContent.replace("observed_skill_version: 4.3.4", "observed_skill_version: 4.2.8"));
  lifecycleCheck = JSON.parse(run("node", [cli, "feedback", "--projects", first, "--json"]).stdout);
  assert(lifecycleCheck.metadata.find(item => item.report_id === "ACSF-geesight-20260718-c35fa4e3")?.lifecycle === "recheck-due", "an unresolved v1 report from an older Skill version must require recheck");
  writeFile(firstOtherReport, firstOtherContent);

  writeFile(secondReport, render("spoofed-project", "ACSF-xjmate-20260718-b24f93d2", "PRIVATE-BODY-SECOND"));
  const spoofed = run("node", [cli, "feedback", "--projects", second, "--json"], { check: false });
  assert(spoofed.status !== 0 && spoofed.stderr.includes("project must equal") && spoofed.stderr.includes("project.name"), "collector must bind report project identity to effective project configuration");
  writeFile(secondReport, secondContent);

  const secondOverlay = projectConfigPath(second);
  const secondOverlayContent = fs.readFileSync(secondOverlay);
  const secondOverrides = readYamlConfig(secondOverlay).overrides;
  writeProjectConfig(second, {
    ...secondOverrides,
    project: { ...(secondOverrides.project ?? {}), name: path.basename(first) },
  });
  writeFile(secondReport, render(path.basename(first), "ACSF-xjmate-20260718-b24f93d2", "PRIVATE-BODY-SECOND"));
  const duplicateIdentity = run("node", [cli, "feedback", "--projects", `${first},${second}`, "--json"], { check: false });
  assert(duplicateIdentity.status !== 0 && duplicateIdentity.stderr.includes("distinct") && duplicateIdentity.stderr.includes("project.name"), "collector must not count two roots declaring one effective project identity as cross-project evidence");
  fs.writeFileSync(secondOverlay, secondOverlayContent);
  writeFile(secondReport, secondContent);

  const firstOverlay = projectConfigPath(first);
  const firstOverlayContent = fs.readFileSync(firstOverlay);
  fs.writeFileSync(firstOverlay, Buffer.alloc(128 * 1024 + 1, "a"));
  const oversizedConfig = run("node", [cli, "feedback", "--projects", first, "--json"], { check: false });
  assert(oversizedConfig.status !== 0 && oversizedConfig.stderr.includes("size limit"), "collector must bound project overlay reads");
  fs.writeFileSync(firstOverlay, firstOverlayContent);

  const implicit = run("node", [cli, "feedback", first, "--json"], { check: false });
  assert(implicit.status !== 0 && implicit.stderr.includes("requires explicit --projects"), "feedback collection must reject implicit or positional project scope");

  if (process.platform !== "win32") {
    const linked = path.join(first, "docs", "skill-feedback", "reports", "2026-07-18-linked-report-deadbeef.md");
    fs.symlinkSync(secondReport, linked);
    const unsafe = run("node", [cli, "feedback", "--projects", first, "--json"], { check: false });
    assert(unsafe.status !== 0 && unsafe.stderr.includes("regular non-symlink file"), "collector must reject feedback symlinks without following them");

    fs.rmSync(path.join(first, "docs", "skill-feedback"), { recursive: true, force: true });
    const externalFeedback = tmpdir("feedback-collector-parent-external");
    fs.mkdirSync(path.join(externalFeedback, "reports"), { recursive: true });
    writeFile(path.join(externalFeedback, "reports", path.basename(firstReport)), firstContent);
    fs.symlinkSync(externalFeedback, path.join(first, "docs", "skill-feedback"));
    const unsafeParent = run("node", [cli, "feedback", "--projects", first, "--json"], { check: false });
    assert(unsafeParent.status !== 0 && unsafeParent.stderr.includes("real directory"), "collector must reject a symlink in the feedback parent chain");
  }
}

function testReleaseVersionMarkersStayInSync() {
  const expected = "4.3.4";
  const pkg = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  const lock = JSON.parse(fs.readFileSync(path.join(repoRoot, "package-lock.json"), "utf8"));
  const policy = JSON.parse(fs.readFileSync(
    path.join(repoRoot, "src", "auto-coding-skill", "data", "policies", "workflow-migrations-v1.json"),
    "utf8",
  ));
  assert(pkg.version === expected, "package version must match the 4.3.4 release");
  assert(lock.version === expected && lock.packages[""].version === expected, "package-lock versions must match");
  assert(policy.managed_versions.engineering === expected && policy.managed_versions.agents === expected, "managed workflow versions must match");
  const manifest = JSON.parse(fs.readFileSync(path.join(repoRoot, "cli", "assets", "managed-install.json"), "utf8"));
  assert(manifest.skill_version === expected && manifest.schema_version === 1, "managed install manifest version/schema must match");
  assert(manifest.entries.every(entry => entry.version === expected && /^[0-9a-f]{64}$/.test(entry.sha256)), "managed install entries must carry release hashes and versions");
  assert(manifest.entries.find(entry => entry.path === "docs/ENGINEERING.md")?.ownership === "exact", "managed ENGINEERING must be installed as an exact default layer");
  assert(!manifest.entries.some(entry => entry.path === "docs/architecture/structure-standard.md"), "project structure standard must not be exact-managed");
  assert(manifest.preserved.includes("docs/architecture/structure-standard.md"), "manifest must declare the project structure standard preserved");
  assert(manifest.entries.some(entry => entry.path === "docs/skill-feedback/README.md"), "feedback README must be exact-managed");
  assert(manifest.entries.some(entry => entry.path === "docs/skill-feedback/_TEMPLATE-SKILL-FEEDBACK.md"), "feedback template must be exact-managed");
  assert(manifest.entries.some(entry => entry.path === ".agents/skills/auto-coding-skill/data/policies/feedback-resolutions-v1.json"), "feedback resolution catalog must be exact-managed");
  assert(manifest.preserved.includes("docs/skill-feedback/reports/*.md"), "manifest must declare project feedback reports preserved");
  assert(!manifest.managed_namespaces.some(item => item.path === "docs/skill-feedback"), "project feedback reports must stay outside managed namespaces");
  assert(manifest.preserved.includes("docs/project/auto-coding-skill.yaml"), "manifest must declare the project configuration overlay preserved");
  assert(!manifest.entries.some(entry => entry.path === "docs/project/auto-coding-skill.yaml"), "project configuration overlay must never be exact-managed");
  assert(!manifest.managed_namespaces.some(item => item.path === "docs/project"), "project configuration overlay must stay outside managed namespaces");
  for (const root of ["architecture", "bugs", "deployment", "design", "interfaces", "project", "reviews", "testing"]) {
    assert(manifest.preserved.includes(`docs/${root}/** (except exact-managed entries)`), `manifest must preserve recursive project-owned ${root} assets`);
  }
  const resolutionCatalog = JSON.parse(fs.readFileSync(
    path.join(repoRoot, "src", "auto-coding-skill", "data", "policies", "feedback-resolutions-v1.json"),
    "utf8",
  ));
  assert(resolutionCatalog.schema === "auto-coding-skill-feedback-resolutions/v1", "feedback resolution catalog schema must be stable");
  const resolutionSignatures = resolutionCatalog.entries.map(item => item.signature);
  assert(JSON.stringify(resolutionSignatures) === JSON.stringify([...new Set(resolutionSignatures)].sort()), "feedback resolution signatures must be unique and sorted");
  assert(resolutionCatalog.entries.every(item => /^\d+\.\d+\.\d+$/.test(item.effective_skill_version)), "feedback resolution releases must be stable SemVer");
  const publishWorkflow = fs.readFileSync(path.join(repoRoot, ".github", "workflows", "npm-publish.yml"), "utf8");
  const runtimeRequirements = fs.readFileSync(path.join(repoRoot, "src", "auto-coding-skill", "requirements.txt"), "utf8");
  assert(publishWorkflow.includes("tags:\n      - \"v*\""), "npm publish must run from version tag pushes");
  assert(publishWorkflow.includes("actions/setup-python@v6") && publishWorkflow.includes("src/auto-coding-skill/requirements.txt"), "npm publish must install the pinned Python runtime before verification");
  assert(publishWorkflow.includes("NPM_TOKEN_AVAILABLE") && publishWorkflow.includes("Require external publication"), "npm publish must support local-token publication when no GitHub secret exists");
  assert(runtimeRequirements.trim() === "PyYAML==6.0.3", "the runtime must have one pinned third-party dependency");
  assert(!runtimeRequirements.toLowerCase().includes("requests"), "HTTP checks must stay on the Python standard library");
  assert(publishWorkflow.includes("Verify release identity"), "npm publish must bind the tag to package version");
  assert(publishWorkflow.includes("Check npm registry") && publishWorkflow.includes("Verify npm publication"), "npm publish must be idempotent and registry-verified");
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
  // The project-overlay ownership boundary adds a small, measured protocol
  // contract without adding another workflow document.
  assert(totalLines <= 370, `shared protocol context budget exceeded: ${totalLines} lines`);
  assert(agents.includes("## Minimum mechanism budget") && agents.includes("## Bounded real validation"), "AGENTS must remain the behavioral protocol");
  assert(skill.includes("## Select the minimum mechanism set") && !skill.includes("## Authority"), "SKILL must remain invocation guidance");
  assert(engineering.includes("The frontmatter contract is:") && !engineering.includes("## Git and parallel work"), "ENGINEERING must remain project configuration/facts");
  assert(engineering.includes("docs/project/auto-coding-skill.yaml") && engineering.includes("project overlay"), "ENGINEERING must direct project specialization to the preserved overlay");
  assert(engineering.includes("owns this document byte-for-byte"), "ENGINEERING must identify itself as the managed default layer");
  assert(!engineering.includes("advisory architecture and no-new-debt policy"), "ENGINEERING policy summary must not hard-code template defaults");
}

testInitFullyConvergesExistingProject();
testStructureBlockWarningsDefaultsPreserveAndConverge();
testProjectDocumentationSpecialFilesFailBeforeWrites();
testManagedPolicySummaryPreservesProjectConfiguration();
testInitRejectsMissingPythonRuntimeBeforeWrites();
testDestVariants();
testLauncherFallsBackToGlobalRuntime();
testMinimalInitConvergesWithinBudget();
testSkillFeedbackTemplatesAndReportsSurviveSync();
testStatusRejectsLegacyIsolation();
testStatusRejectsLegacyGateEscalation();
testStatusAcceptsValidIndentlessYamlRoutes();
testOrdinaryNodeTestIsNotPromotedToAutomaticGate();
testAccessPasswordsAreRequiredButNeverPrintedByStatus();
testProjectConfigOverlayMigratesLegacyEngineeringAndStaysByteStable();
testProjectConfigOverlayMergeKeepsExplicitFalseZeroEmptyAndList();
testOversizedLegacyMigrationFailsBeforeCreatingAnInvalidOverlay();
testInvalidProjectConfigOverlayFailsBeforeAnyWrites();
testStatusRejectsManagedAgentSymlinksWithoutLeakingExternalContent();
testMultiProjectSyncRejectsManagedTargetSymlinksBeforeAnyProjectWrite();
testTamperedInstalledDefaultRejectsInitAndSyncWithoutWrites();
testExistingOverlayConflictRejectsInitAndSyncWithoutWrites();
testExistingOverlayLegacyDeletionRejectsInitAndSyncWithoutWrites();
testLiveInstallTransactionRejectsSecondInstallerWithoutWrites();
testStagedRuntimeTamperingIsRejectedBeforeExecution();
testInterruptedStagedInstallRecoversForInitAndSync();
testArchiveFallbackCollisionsNeverLosePreviousContent();
testProjectMutationAndInstallSwitchRejectParentSwap();
testNoChangeLightGateRejectsInvalidEffectiveContracts();
testStatusRejectsInvalidStructureEnforcementFromDoctorContract();
testProjectConfigOverlayIsHighRiskAndReviewRequired();
testStatusAndFeedbackUseEffectiveProjectConfigWithoutLeakingAccess();
testManagedAgentModelsInheritAndOverridesSurvive();
testForcePreservesCustomAgentsAndModelOverrides();
testInvalidManagedAgentModelsFailStatusAndAreDroppedOnSync();
testModelTextInsideInstructionsIsNotPromotedToOverride();
testCommandSpecificArgumentsAreRejectedBeforeWrites();
testBridgeIsGeneric();
testSyncCleansAllManagedSkillExtras();
testOptionalDocsAndLegacyToolsDoNotCauseDrift();
testOptionalScaffoldIsOnDemandAndIdempotent();
testTestingScaffoldMatchesCheckMatrixSchema();
testReviewScaffoldLeavesBaselineGenerationToBaselineCommand();
testBaselineUpdateConfigWritesOnlyProjectOverlay();
testSyncUsesPackagedAssetsAndIgnoresRetiredTemplates();
testInitInitializesNewEngineeringDefaults();
testInitMigratesLegacyAutomaticGateToFastDefault();
testRemovedVerificationFlagsFailFast();
testInstallBootstrapsRuntimeRequiredByLauncher();
testCliInstallArchivesFeedbackTemplatesAndPreservesReports();
testLegacyUpgradeWriteFailsWithoutAnyWrites();
testLedgerArchiveRecognizesSettledStatuses();
testLedgerArchiveUpdatesExistingPeriodIndex();
testManagedEngineeringInitIsAuthoritativeAndIdempotent();
testLegacyEngineeringMigrationPreservesExistingBody();
testOfficialLegacyEngineeringBodyIsReplacedWithoutDuplication();
testMalformedManagedMarkersFailClosed();
testPartialSkillSyncIsRejectedWithoutWrites();
testLegacyTaskPreflightRejectsWholeBatchAtomically();
testManagedAgentsMigrationReplacesWholeFileAndArchivesPreviousRules();
testUnknownWorkflowConflictFailsWholeBatchBeforeWrites();
testEngineeringMarkerBoundaryIsNormalized();
testEngineeringFrameworkRejectsAnyNonCanonicalWorkflowText();
testManagedInstallIntegrityIsBoundedAndRepairable();
testSkillFeedbackCollectionIsBoundedReadOnlyAndMetadataOnly();
testReleaseVersionMarkersStayInSync();
testProtocolResponsibilitiesStaySeparated();

console.log("cli-installer-regression-ok");
