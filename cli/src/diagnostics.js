import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

// Previously shipped source/test pairs. Unknown or mixed pairs are project-owned
// until reviewed. Do not silently replace a downstream fix on the next release.
const originalGuard = "7e47fce43263ae1cfa440565b1d56af0a865db36da3566e6cbac7a2de9cb4804";
const knownPairs = new Set([
  originalGuard + ":d593fa6aae02a31b0d148b90325b514565ed1661fc647f46f529a3bf980d8c3b",
  originalGuard + ":absent", // original single-file adoption, before fixtures were distributed
  "f654b2875e33670212bfdd365779ef9a87c6636daec57c4035eb7c1587798a2e:231b711228791209d9a1655f368f50d5032c8cfc0964c9c5013d765ddd91f4a3",
  "fb9b841b0edfaa778e4a58436d8b4f55b09bef08def333bf741276d33cd2019e:54064d4752da3a9a244dee8b1258286a01d56322ceadffda3dd0c7db44f37e67",
]);
const names = ["guard.py", "test_guard.py"];
const regular = file => file && fs.statSync(file, { throwIfNoEntry: false })?.isFile();
function cmd(cwd, binary, args) {
  const env = { ...process.env, GIT_OPTIONAL_LOCKS: "0", GIT_TERMINAL_PROMPT: "0" };
  // Diagnose the requested checkout, even when invoked from another Git hook.
  for (const key of ["GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"]) delete env[key];
  return spawnSync(binary, args, { cwd, env, encoding: "utf8", timeout: 10000 });
}
function git(cwd, ...args) {
  const r = cmd(cwd, "git", args);
  return r.status === 0 ? r.stdout.trim() : "";
}
function workspace(root) {
  const top = git(root, "rev-parse", "--show-toplevel");
  if (!top || fs.realpathSync(top) !== fs.realpathSync(root)) return { kind: "not-checkout-root" };
  const common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir");
  const dir = git(root, "rev-parse", "--absolute-git-dir");
  if (!common || !dir) return { kind: "unknown" };
  const linked = fs.realpathSync(common) !== fs.realpathSync(dir);
  const branch = git(root, "symbolic-ref", "-q", "--short", "HEAD") || null;
  return { kind: linked ? "linked" : "primary", branch, common,
    task_branch: linked && Boolean(branch?.startsWith("codex/")) };
}

export function diagnostics({ packageRoot, managedTarget, sha256 }) {
  const canonical = names.map(n => path.join(packageRoot, "src/git-workflow", n));
  function sources(root) {
    const targets = names.map(n => managedTarget(root, "config/git-workflow/" + n));
    if (targets.some(p => !p)) return { state: "unknown", targets };
    if (targets.every(p => !fs.existsSync(p))) return { state: "absent", targets };
    const pair = targets.map(p => regular(p) ? sha256(p) : fs.existsSync(p) ? "unknown" : "absent").join(":");
    const state = pair === canonical.map(sha256).join(":") ? "current" : knownPairs.has(pair) ? "known-older" : "unknown";
    return { state, targets };
  }

  function guardSync(root, dryRun) {
    const { state, targets } = sources(root);
    const result = { project: root, source: state, dry_run: dryRun, changed: false };
    if (state === "current") return { ...result, ok: true };
    if (state !== "known-older") return { ...result, ok: false,
      next: "No files changed. No recognized guard pair; review project ownership or downstream changes." };
    if (dryRun) return { ...result, ok: true, would_refresh: names };
    if (!workspace(root).task_branch) return { ...result, ok: false, next: "Use this task's linked codex/* worktree." };
    for (const [i, target] of targets.entries()) fs.copyFileSync(canonical[i], target);
    return { ...result, source: "current", changed: true, ok: true,
      next: "After verification, explicitly refresh the opted-in clone with python3 config/git-workflow/guard.py install." };
  }

  function guard(root, w) {
    const { state } = sources(root);
    const opted = Boolean(w.common && fs.existsSync(path.join(w.common, "codex-workflow-guard/state.json")));
    if (!opted && state === "absent") return { status: "not-configured", source: state, ok: true };
    if (!opted) return { status: "not-installed", source: state, ok: false,
      next: "Confirm clone opt-in before installing; no hook was changed." };
    // Execute the trusted, packaged checker, never a script from the project.
    const r = cmd(root, "python3", ["-I", "-B", canonical[0], "status"]);
    let detail;
    try { detail = JSON.parse(r.stdout); } catch { /* missing interpreter, invalid state, etc. */ }
    const ok = state === "current" && r.status === 0 && detail?.ok === true;
    const next = state === "unknown" || state === "absent" ? "Review the project's guard files; do not replace unknown changes."
      : state === "known-older" ? "Preview autocoding guard-sync --dry-run in this project."
      : !detail ? "Check Python 3.9+ and the clone's guard metadata; do not disable hooks."
      : "Inspect core.hooksPath and the chained hooks; refresh the verified guard with its install command.";
    return { status: ok ? "active" : "needs-review", source: state, ok, version: detail?.version ?? null,
      expected_version: detail?.expected_version ?? null, interpreter: detail?.interpreter ?? null,
      runtime_matches: detail?.runtime_matches ?? null, hooks_match: detail?.hooks_match ?? null,
      ...(!ok ? { next } : {}) };
  }

  function doctor(status) {
    if (status.mode === "source") return status;
    const root = status.project;
    const project = managedTarget(root, "docs/PROJECT.md");
    const bridge = managedTarget(root, "AGENTS.md");
    const bridgeText = regular(bridge) ? fs.readFileSync(bridge, "utf8") : "";
    const marker = /<!-- auto-coding-skill:managed-agents:start[^>]*-->[\s\S]*?<!-- auto-coding-skill:managed-agents:end -->/;
    const outside = marker.test(bridgeText) ? Boolean(bridgeText.replace(marker, "").trim()) : null;
    const agentDir = managedTarget(root, ".agents/agents");
    const overlays = [];
    if (agentDir && fs.statSync(agentDir, { throwIfNoEntry: false })?.isDirectory()) {
      for (const name of fs.readdirSync(agentDir).filter(n => n.endsWith(".toml")).sort()) {
        const relative = ".agents/agents/" + name;
        const file = managedTarget(root, relative);
        if (!regular(file)) continue;
        const content = fs.readFileSync(file, "utf8");
        overlays.push({ path: relative, pins_model: /^\s*model\s*=/m.test(content),
          pins_effort: /^\s*model_reasoning_effort\s*=/m.test(content) });
      }
    }
    const w = workspace(root);
    const g = guard(root, w);
    const contextPresent = Boolean(regular(project));
    const next = [];
    if (!status.integrity) next.push("Review modified managed files; migrate project facts before replacement.");
    if (!status.assets_current) next.push("Preview autocoding init --dry-run; project documents are preserved.");
    if (!contextPresent) next.push("Restore the project-owned docs/PROJECT.md; do not invent project facts.");
    if (outside) next.push("Review text outside the managed AGENTS.md block and move project-only constraints to docs/PROJECT.md.");
    if (overlays.length || status.legacy_files.length) next.push("Check consumers of local overlays before archiving; no profile was loaded or removed.");
    if (!g.ok) next.push(g.next);
    return { project: root, ok: status.ok && contextPresent && g.ok,
      managed: { integrity: status.integrity, current: status.assets_current, installed: status.version, cli: status.expected_version },
      context: { project_entry: contextPresent ? "present" : "missing-or-unsafe", ownership: "project",
        entry_bytes: contextPresent ? fs.statSync(project).size : null, outside_managed_bridge: outside, legacy_profiles: overlays,
        legacy_workflow: status.legacy_files }, worktree: { kind: w.kind, branch: w.branch ?? null, task_branch: w.task_branch ?? false },
      guard: g, next };
  }
  return { doctor, guardSync };
}
