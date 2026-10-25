import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

// Exercise the documented integration protocol locally; this is not a project Gate/runtime.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "autocoding-parallel-"));
const remote = path.join(tmp, "remote.git");
const main = path.join(tmp, "main");
const a = path.join(tmp, "task-a");
const b = path.join(tmp, "task-b");
function git(cwd, args, expected = 0) {
  const result = spawnSync("git", args, { cwd, encoding: "utf8", env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: os.devNull } });
  assert.equal(result.status, expected, result.stderr || result.stdout);
  return result.stdout.trim();
}
function writeTask(cwd, value) {
  fs.writeFileSync(path.join(cwd, "behavior.json"), `${JSON.stringify(value)}\n`);
  git(cwd, ["add", "behavior.json"]);
  git(cwd, ["commit", "-m", "fixture: implement task"]);
  return git(cwd, ["rev-parse", "HEAD"]);
}
try {
  git(tmp, ["init", "--bare", "--initial-branch=dev", remote]);
  git(tmp, ["init", "--initial-branch=dev", main]);
  git(main, ["config", "user.name", "Skill fixture"]);
  git(main, ["config", "user.email", "fixture@example.invalid"]);
  git(main, ["config", "commit.gpgsign", "false"]);
  const base = writeTask(main, { alpha: false, beta: false });
  git(main, ["remote", "add", "origin", remote]);
  git(main, ["push", "-u", "origin", "dev"]);
  git(main, ["worktree", "add", "-b", "codex/task-a", a, "origin/dev"]);
  git(main, ["worktree", "add", "-b", "codex/task-b", b, "origin/dev"]);
  const commitA = writeTask(a, { alpha: true, beta: false });
  const commitB = writeTask(b, { alpha: false, beta: true });
  assert.equal(git(main, ["rev-parse", "HEAD"]), base);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(main, "behavior.json"))), { alpha: false, beta: false });
  git(a, ["push", "origin", "HEAD:refs/heads/dev"]);
  git(b, ["push", "origin", "HEAD:refs/heads/dev"], 1);
  git(b, ["fetch", "origin", "dev"]);
  git(b, ["merge", "--no-edit", "origin/dev"], 1);
  assert.equal(git(b, ["diff", "--name-only", "--diff-filter=U"]), "behavior.json");
  // Resolve the actual conflict by preserving both independent requirements.
  fs.writeFileSync(path.join(b, "behavior.json"), `${JSON.stringify({ alpha: true, beta: true })}\n`);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(b, "behavior.json"))), { alpha: true, beta: true });
  git(b, ["add", "behavior.json"]);
  git(b, ["commit", "-m", "fixture: reconcile both task behaviors"]);
  git(b, ["merge-base", "--is-ancestor", commitA, "HEAD"]);
  git(b, ["merge-base", "--is-ancestor", commitB, "HEAD"]);
  git(b, ["push", "origin", "HEAD:refs/heads/dev"]);
  const integrated = git(b, ["rev-parse", "HEAD"]);
  assert.equal(git(tmp, ["--git-dir", remote, "rev-parse", "refs/heads/dev"]), integrated);
  assert.equal(git(main, ["rev-parse", "HEAD"]), base, "integration must not switch or edit the shared checkout");
  assert.equal(git(main, ["status", "--porcelain"]), "");
  console.log("Parallel regression passed: independent worktrees, stale push rejection, real conflict, both behaviors retained, non-force dev integration");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
