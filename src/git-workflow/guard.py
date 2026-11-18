#!/usr/bin/env python3
"""Local Git policy: isolated codex worktrees, verified integration into dev.

Explicit opt-in per clone; never installed by CI. This is an accident guard,
not a security boundary against an owner disabling or rewriting local hooks.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

VERSION = 2
STATE_FILE = "state.json"
TASK_REF_PREFIX = "refs/heads/codex/"
DEV_REF = "refs/heads/dev"
REMOTE_DEV_REF = "refs/remotes/origin/dev"
HOOKS_PATH_KEY = "core.hooksPath"
HOOKS = {
    "pre-commit", "pre-applypatch", "pre-rebase", "post-commit",
    "post-applypatch", "post-merge", "post-rewrite", "pre-push", "reference-transaction",
}
OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class Rejected(Exception):
    pass


def git(*args, check=True, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise Rejected("Git inspection failed: " + " ".join(args[:2]))
    return result


def value(*args, **kwargs):
    return git(*args, **kwargs).stdout.strip()


def common_dir():
    return Path(value("rev-parse", "--git-common-dir")).resolve()


def state_dir():
    return common_dir() / "codex-workflow-guard"


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def config():
    return json.loads((state_dir() / STATE_FILE).read_text())


def ancestor(old, new):
    return bool(old and new) and git("merge-base", "--is-ancestor", old, new,
                                    check=False).returncode == 0


def task_context():
    directory = Path(value("rev-parse", "--absolute-git-dir")).resolve()
    if directory == common_dir():
        return None
    branch = value("symbolic-ref", "--quiet", "HEAD", check=False)
    if not branch:
        for folder in ("rebase-merge", "rebase-apply"):
            head_name = directory / folder / "head-name"
            if head_name.is_file():
                branch = head_name.read_text().strip()
                break
    if not branch.startswith(TASK_REF_PREFIX) or branch == TASK_REF_PREFIX:
        return None
    return {"branch": branch, "git_dir": str(directory),
            "worktree": value("rev-parse", "--show-toplevel")}


def require_task():
    task = task_context()
    if not task:
        raise Rejected("Develop in a linked worktree on codex/<task>, not dev or "
                       "the primary checkout. Create an independent worktree from "
                       "current dev; do not switch/stash another conversation's files.")
    return task


def receipt_path(sha):
    if not OID.fullmatch(sha):
        raise Rejected("Invalid commit identity")
    return state_dir() / "commits" / (sha + ".json")


def record(sha, context, kind="task"):
    atomic_json(receipt_path(sha), {"commit": sha, "kind": kind, **context})


def certified(sha):
    path = receipt_path(sha)
    if not path.is_file():
        return False
    data = json.loads(path.read_text())
    return data.get("commit") == sha and data.get("kind") in {
        "task", "integration", "existing-isolated-task", "rewrite",
    }


def verify_commits(tip, base, include_remote=False):
    exclusions = [config()["baseline"]]
    if base and set(base) != {"0"}:
        exclusions.append(base)
    if include_remote:
        remote = value("rev-parse", "--verify", REMOTE_DEV_REF, check=False)
        if remote:
            exclusions.append(remote)
    commits = value("rev-list", tip, *("^" + x for x in exclusions)).splitlines()
    missing = [sha for sha in commits if not certified(sha)]
    if missing:
        raise Rejected("Unverified commit origin: " + ", ".join(x[:12] for x in missing[:4])
                       + ". Commit/reconcile in the task's codex worktree first.")


def merge_tree(left, right):
    result = git("merge-tree", "--write-tree", left, right, check=False)
    if result.returncode or not result.stdout.splitlines():
        raise Rejected("Resolve merge conflicts in the independent codex worktree, "
                       "not in the shared dev checkout.")
    return result.stdout.splitlines()[0]


def safe_merge_commit(old, new):
    parents = value("show", "-s", "--format=%P", new).split()
    if len(parents) != 2 or parents[0] != old:
        return False
    try:
        verify_commits(parents[1], old, include_remote=True)
        if not certified(parents[1]):
            return False
        if value("show", "-s", "--format=%T", new) != merge_tree(*parents):
            return False
    except Rejected:
        return False
    record(new, {"parents": parents}, "integration")
    return True


def commit_check():
    if task_context():
        return
    # A pure integration commit is not development on dev. Any manual content
    # change or conflicted merge must instead be resolved in the task worktree.
    if value("symbolic-ref", "--quiet", "HEAD", check=False) == DEV_REF:
        merge_head = Path(value("rev-parse", "--git-path", "MERGE_HEAD"))
        if merge_head.is_file():
            parents = merge_head.read_text().split()
            if len(parents) == 1 and certified(parents[0]):
                old = value("rev-parse", "HEAD")
                verify_commits(parents[0], old, include_remote=True)
                if value("write-tree") == merge_tree(old, parents[0]):
                    return
    require_task()


def prunes_only_loose_dev(old):
    """In the files backend a real packed deletion must lock packed-refs.

    At 'prepared', pack-refs has already committed the identical packed value
    and holds only the loose ref lock. Unknown layouts or zero OIDs fail closed.
    """
    if not OID.fullmatch(old) or set(old) == {"0"}:
        return False
    root = common_dir()
    loose = root / DEV_REF
    if (root / "packed-refs.lock").exists() or not Path(str(loose) + ".lock").is_file():
        return False
    try:
        if loose.is_symlink() or loose.read_bytes().strip() != old.encode():
            return False
        entry = (old + " " + DEV_REF).encode()
        with (root / "packed-refs").open("rb") as refs:
            return any(line.rstrip(b"\n") == entry for line in refs)
    except OSError:
        return False


def check_dev_reference(old, new, ref):
    if set(new) == {"0"} and prunes_only_loose_dev(old):
        return
    current = value("rev-parse", "--verify", ref, check=False)
    before = current if set(old) == {"0"} else old
    if set(new) == {"0"} or (before and not ancestor(before, new)):
        raise Rejected("dev deletion/history rewriting is blocked; integrate without force.")
    remote = value("rev-parse", "--verify", REMOTE_DEV_REF, check=False)
    if remote and ancestor(new, remote):
        return  # A clean fetch/fast-forward from the integration remote.
    if certified(new):
        verify_commits(new, before, include_remote=True)
        return
    if before and safe_merge_commit(before, new):
        return
    raise Rejected("Direct development on dev is blocked. Complete the codex worktree "
                   "change, reconcile latest dev, then fast-forward or make a pure merge.")


def reference_check(data):
    task = task_context()
    for line in data.splitlines():
        old, new, ref = line.split()
        if not ref.startswith("refs/heads/") or (old == new and set(new) != {"0"}):
            continue
        if ref == DEV_REF:
            check_dev_reference(old, new, ref)
        elif set(old) != {"0"} and set(new) != {"0"} and (not task or task["branch"] != ref):
            raise Rejected("Branch updates require that branch's independent codex worktree.")


def push_check(data, remote_name):
    for line in data.splitlines():
        _, tip, target, remote = line.split()
        if target != DEV_REF and not target.startswith(TASK_REF_PREFIX):
            continue
        if set(tip) == {"0"}:
            if target == DEV_REF:
                raise Rejected("Deleting remote dev is blocked.")
            continue
        if set(remote) != {"0"} and not ancestor(remote, tip):
            raise Rejected("Fetch and reconcile the latest remote branch in the task "
                           "worktree before pushing; non-fast-forward updates are blocked.")
        # For task pushes to the integration remote, its fetched dev history
        # was already accepted there. No such exemption for dev or other remotes.
        verify_commits(tip, remote, include_remote=remote_name == "origin"
                       and target.startswith(TASK_REF_PREFIX))


def previous_hook(name, args, data):
    saved = config()["previous_hooks"]
    hook = Path(saved) / name
    if not hook.is_absolute():
        hook = Path(value("rev-parse", "--show-toplevel")) / hook
    if hook.is_file() and os.access(hook, os.X_OK):
        return subprocess.run([str(hook), *args], input=data, text=True).returncode
    return 0


def record_rewritten_commits(data):
    task = require_task()
    for line in data.splitlines():
        old, new = line.split()[:2]
        if not certified(old) and not ancestor(old, config()["baseline"]):
            raise Rejected("Rewritten commit lacks isolated-worktree provenance.")
        record(new, task, "rewrite")


def dispatch(name, args):
    data = sys.stdin.read() if name in {"pre-push", "post-rewrite", "reference-transaction"} else ""
    if name in {"pre-commit", "pre-applypatch"}:
        commit_check()
    elif name == "pre-rebase":
        task = require_task()
        if len(args) > 1 and args[1] not in {task["branch"], task["branch"].removeprefix("refs/heads/")}:
            raise Rejected("Rebase only the branch owned by this worktree.")
    elif name == "reference-transaction" and args == ["prepared"]:
        reference_check(data)
    elif name == "pre-push":
        push_check(data, args[0] if args else None)
    elif name in {"post-commit", "post-applypatch", "post-merge"} and task_context():
        record(value("rev-parse", "HEAD"), require_task())
    elif name == "post-rewrite":
        record_rewritten_commits(data)
    return previous_hook(name, args, data)


def worktree_fields(entry):
    pairs = (line.split(" ", 1) for line in entry.splitlines() if " " in line)
    return dict(pairs)


def check_worktree_overrides():
    # A per-worktree override would silently defeat shared activation.
    for entry in value("worktree", "list", "--porcelain").split("\n\n"):
        path = worktree_fields(entry).get("worktree", "")
        if not path or not Path(path).is_dir():
            continue
        directory = Path(value("rev-parse", "--absolute-git-dir", cwd=path))
        cfg = directory / "config.worktree"
        if cfg.is_file() and value("config", "--file", str(cfg), "--get", HOOKS_PATH_KEY, check=False):
            raise Rejected("Existing worktree-specific hooksPath requires manual review.")


def replace_bytes(target, data, mode):
    if target.is_file() and target.read_bytes() == data and target.stat().st_mode & 0o777 == mode:
        return
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def hook_script(interpreter, name):
    # Preserve the selected interpreter; a package-manager upgrade can remove
    # its versioned path. A missing fallback still fails the Git operation.
    return ("#!/bin/sh\npy=" + shlex.quote(interpreter) + '\n[ -x "$py" ] || py=python3\n'
            'exec "$py" "${0%/*}/../guard.py" hook ' + name + ' "$@"\n').encode()


def install_hooks(root, state):
    payload = Path(__file__).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    runtime = root / ("runtime-" + digest[:16])
    hooks = runtime / "hooks"
    hooks.mkdir(parents=True, exist_ok=True, mode=0o700)
    replace_bytes(runtime / "guard.py", payload, 0o600)
    old_dir = Path(state["previous_hooks"])
    if not old_dir.is_absolute():
        old_dir = Path(value("rev-parse", "--show-toplevel")) / old_dir
    names = HOOKS | ({path.name for path in old_dir.iterdir() if path.is_file()
                      and os.access(path, os.X_OK) and not path.name.endswith(".sample")}
                     if old_dir.is_dir() else set())
    for name in names:
        if not re.fullmatch(r"[a-z][a-z-]*", name):
            raise Rejected("Unexpected existing hook name; manual chaining required")
        replace_bytes(hooks / name, hook_script(sys.executable, name), 0o700)
    state.update(hooks_path=str(hooks), source_sha256=digest, version=VERSION,
                 interpreter=sys.executable, hook_names=sorted(names))
    atomic_json(root / STATE_FILE, state)
    return hooks


def record_existing_tasks(common, baseline):
    # Preserve already-running isolated tasks without rewriting their commits.
    for entry in value("worktree", "list", "--porcelain").split("\n\n"):
        fields = worktree_fields(entry)
        branch, path = fields.get("branch", ""), fields.get("worktree", "")
        if not branch.startswith(TASK_REF_PREFIX) or not Path(path).is_dir():
            continue
        directory = Path(value("rev-parse", "--absolute-git-dir", cwd=path)).resolve()
        if directory == common:
            continue
        for sha in value("rev-list", fields["HEAD"], "^" + baseline).splitlines():
            record(sha, {"branch": branch, "worktree": path, "git_dir": str(directory)},
                   "existing-isolated-task")


def install():
    version = re.match(r"git version (\d+)\.(\d+)", value("--version"))
    if not version or tuple(map(int, version.groups())) < (2, 38):
        raise Rejected("Git 2.38+ is required for reference checks and safe merge verification")
    if sys.version_info < (3, 9):
        raise Rejected("Python 3.9+ is required")
    root = state_dir()
    common = common_dir()
    check_worktree_overrides()
    effective = value("config", "--get", HOOKS_PATH_KEY, check=False)
    local = git("config", "--local", "--get", HOOKS_PATH_KEY, check=False)
    prior = config() if (root / STATE_FILE).is_file() else None
    if prior and effective != prior["hooks_path"]:
        raise Rejected("hooksPath changed since installation; preserve it and review before updating.")
    if prior:
        state = prior
    else:
        state = {"version": VERSION, "baseline": value("rev-parse", REMOTE_DEV_REF),
                 "previous_local": local.stdout.strip() if local.returncode == 0 else None,
                 "previous_hooks": effective or str(common / "hooks")}
    hooks = install_hooks(root, state)
    if not prior:
        record_existing_tasks(common, state["baseline"])
    git("config", "--local", HOOKS_PATH_KEY, str(hooks))
    print(json.dumps({"installed": True, "version": VERSION, "hooks_path": str(hooks),
                      "chained_hooks": state["previous_hooks"]}))


def status():
    state = config()
    actual = value("config", "--get", HOOKS_PATH_KEY, check=False)
    runtime = Path(state["hooks_path"]).parent / "guard.py"
    version_ok = state["version"] == VERSION
    source_ok = hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == state["source_sha256"]
    runtime_ok = runtime.is_file() and hashlib.sha256(runtime.read_bytes()).hexdigest() == state["source_sha256"]
    pinned = state.get("interpreter", "")
    interpreter = "pinned" if pinned and os.access(pinned, os.X_OK) else (
        "path-fallback" if version_ok and shutil.which("python3") else "unknown-or-missing")
    hooks_ok = version_ok and all(
        re.fullmatch(r"[a-z][a-z-]*", h) and (Path(actual) / h).is_file()
        and os.access(Path(actual) / h, os.X_OK)
        and (Path(actual) / h).read_bytes() == hook_script(pinned, h)
        for h in HOOKS | set(state.get("hook_names", [])))
    ok = (actual == state["hooks_path"] and version_ok and source_ok and runtime_ok
          and hooks_ok and interpreter != "unknown-or-missing")
    print(json.dumps({"ok": ok, "version": state["version"], "hooks_path": actual,
                      "expected_version": VERSION, "source_matches": source_ok,
                      "runtime_matches": runtime_ok, "hooks_match": hooks_ok,
                      "interpreter": interpreter,
                      "chained_hooks": state["previous_hooks"]}))
    return 0 if ok else 1


def uninstall():
    state = config()
    if value("config", "--get", HOOKS_PATH_KEY, check=False) != state["hooks_path"]:
        raise Rejected("hooksPath changed; refusing to overwrite another configuration")
    if state["previous_local"] is None:
        git("config", "--local", "--unset", HOOKS_PATH_KEY)
    else:
        git("config", "--local", HOOKS_PATH_KEY, state["previous_local"])
    # Keep receipts/runtime available for recovery; no files or branches removed.
    (state_dir() / STATE_FILE).rename(state_dir() / "uninstalled-state.json")
    print("Previous hooks configuration restored; recovery data retained.")


def main():
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else "status"
        if command == "hook":
            return dispatch(sys.argv[2], sys.argv[3:])
        if command == "install":
            install()
        elif command == "status":
            return status()
        elif command == "uninstall":
            uninstall()
        elif command == "check":
            commit_check()
        else:
            raise Rejected("Use install, status, check or uninstall")
        return 0
    except (Rejected, OSError, ValueError, KeyError) as error:
        print("[codex-workflow-guard] " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
