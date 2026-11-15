#!/usr/bin/env python3
"""Prepare the LLVM submodule and round-trip its local commits as parent patches."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "third_party/llvm"
PATCHES = ROOT / "patches/llvm"
REPO_ENV = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_PREFIX",
    "GIT_INTERNAL_SUPER_PREFIX", "GIT_SHALLOW_FILE",
)


class Error(Exception):
    pass


def git(*args, sub=False, data=None, env_extra=None, check=True):
    env = os.environ.copy()
    if sub:
        for key in REPO_ENV:
            env.pop(key, None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git", "-C", str(SUB if sub else ROOT), *args], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if check and proc.returncode:
        detail = proc.stderr.decode(errors="replace").strip()
        raise Error(f"git {' '.join(args)}: {detail}")
    return proc


def out(*args, **kwargs):
    return git(*args, **kwargs).stdout.decode().strip()


def metadata(staged=False):
    raw = git("show", ":toolchain.json").stdout if staged else (ROOT / "toolchain.json").read_bytes()
    info = json.loads(raw)
    base = info["upstream_revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise Error("toolchain.json must identify a full upstream commit SHA")
    entry = out("ls-files", "--stage", "--", "third_party/llvm").split()
    if len(entry) != 4 or entry[0] != "160000" or entry[2] != "0":
        raise Error("third_party/llvm must be an initialized, conflict-free Git submodule entry")
    if entry[1] != base:
        raise Error("Staged LLVM submodule pin differs from toolchain.json. Do not stage local LLVM commits as the upstream pin.")
    return info


def indexed_patches():
    paths = git("ls-files", "-z", "--", "patches/llvm/").stdout.split(b"\0")
    result = {}
    for path in paths:
        if path:
            name = path.decode().removeprefix("patches/llvm/")
            result[name] = git("show", ":" + path.decode()).stdout
    return result


def head_patches():
    if git("rev-parse", "--verify", "HEAD", check=False).returncode:
        return {}
    names = out("ls-tree", "-r", "--name-only", "HEAD", "--", "patches/llvm").splitlines()
    return {name.removeprefix("patches/llvm/"): git("show", "HEAD:" + name).stdout for name in names}


def disk_patches():
    if not PATCHES.exists():
        return {}
    result = {}
    for path in PATCHES.iterdir():
        if path.is_symlink() or not path.is_file():
            raise Error(f"Unexpected entry in generated patch directory: {path.name}")
        result[path.name] = path.read_bytes()
    return result


def series(files):
    if "series" not in files:
        raise Error("patches/llvm/series is missing")
    names = files["series"].decode().splitlines()
    if len(names) != len(set(names)):
        raise Error("Duplicate patch in series")
    for name in names:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.patch", name) or name not in files:
            raise Error(f"Invalid or missing patch in series: {name!r}")
    if set(files) != {"series", *names}:
        raise Error("Unlisted/stale files in patches/llvm; this directory is generated")
    return names


def fingerprint(base, files):
    digest = hashlib.sha256(base.encode())
    for name in ["series", *series(files)]:
        digest.update(name.encode() + b"\0" + files[name] + b"\0")
    return digest.hexdigest()


def available():
    return (SUB / ".git").exists()


def clean_submodule():
    if out("status", "--porcelain", "--untracked-files=normal", sub=True):
        raise Error("LLVM has uncommitted or untracked edits. Commit them inside third_party/llvm before exporting; nothing was reset or staged there.")


def state_path():
    path = Path(out("rev-parse", "--absolute-git-dir", sub=True))
    return path / "ldb-prepared.json"


def save_state(base, files, head):
    state_path().write_text(json.dumps({"base": base, "fingerprint": fingerprint(base, files), "head": head}, indent=2) + "\n")


def reconstructed_tree(base, files):
    """Replay in a temporary Git index: no source checkout or developer index changes."""
    names = series(files)
    with tempfile.TemporaryDirectory(prefix="ldb-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git("read-tree", base, sub=True, env_extra=env)
        for name in names:
            git("apply", "--cached", "--whitespace=nowarn", "-", sub=True, data=files[name], env_extra=env)
        return out("write-tree", sub=True, env_extra=env)


def install_hooks():
    git("config", "--local", "core.hooksPath", ".githooks")
    if available():
        git("config", "--local", "core.hooksPath", str(ROOT / ".githooks/llvm"), sub=True)


def setup():
    info = metadata()
    files = disk_patches()
    series(files)
    base = info["upstream_revision"]
    # Do not let `submodule update` detach or move an existing developer checkout.
    if not available():
        git("submodule", "update", "--init", "--filter=blob:none", "--", "third_party/llvm")
    if git("cat-file", "-e", base + "^{commit}", sub=True, check=False).returncode:
        git("fetch", "--no-tags", "--filter=blob:none", "origin", base, sub=True)
    head = out("rev-parse", "HEAD", sub=True)
    path = state_path()
    previous = json.loads(path.read_text()) if path.exists() else None
    wanted = fingerprint(base, files)
    if previous and previous["base"] == base and previous["fingerprint"] == wanted:
        if not git("merge-base", "--is-ancestor", previous["head"], head, sub=True, check=False).returncode:
            install_hooks()
            print("LLVM is already prepared; local development commits/edits were preserved.")
            return
    clean_submodule()
    expected = reconstructed_tree(base, files)
    if head != base:
        if out("rev-parse", "HEAD^{tree}", sub=True) == expected:
            save_state(base, files, head)
            install_hooks()
            print("Recognized existing LLVM patch series; hook installed.")
            return
        if not previous or previous["head"] != head:
            raise Error("LLVM contains local commits not recorded as a prepared series. Preserve them on a local branch and export them before changing toolchains.")
    # Only a pristine baseline or a known, clean, generated checkout reaches here.
    git("checkout", "--detach", base, sub=True)
    paths = info.get("sparse_paths", ["llvm", "clang", "cmake"])
    git("sparse-checkout", "set", "--cone", *paths, sub=True)
    names = series(files)
    if names:
        proc = git(
            "-c", "core.hooksPath=/dev/null", "-c", "user.name=LDB setup",
            "-c", "user.email=ldb-setup@localhost", "am", "--whitespace=nowarn",
            *[str(PATCHES / name) for name in names], sub=True, check=False,
        )
        if proc.returncode:
            git("am", "--abort", sub=True, check=False)
            raise Error("Patch application failed: " + proc.stderr.decode(errors="replace"))
    head = out("rev-parse", "HEAD", sub=True)
    if out("rev-parse", "HEAD^{tree}", sub=True) != expected:
        raise Error("Applied LLVM tree differs from independently reconstructed patches")
    save_state(base, files, head)
    # A repo-local identity in the parent should also work for local submodule development.
    for key in ("user.name", "user.email"):
        value = out("config", "--get", key, check=False)
        if value and not out("config", "--get", key, sub=True, check=False):
            git("config", "--local", key, value, sub=True)
    install_hooks()
    print(f"Prepared LLVM {info['llvm_major']} with {len(names)} patches; pre-commit hook installed.")


def export(hook=False):
    info = metadata(staged=hook)
    if hook and (ROOT / "toolchain.json").read_bytes() != git("show", ":toolchain.json").stdout:
        raise Error("Stage toolchain.json as a whole before exporting a toolchain change")
    base = info["upstream_revision"]
    old = indexed_patches()
    series(old)
    if not available():
        if hook:
            print("LLVM submodule absent: patch export skipped; CI checks reconstruction.")
            return
        raise Error("Run scripts/setup-llvm.sh before editing LLVM")
    clean_submodule()
    head = out("rev-parse", "HEAD", sub=True)
    if head == base and series(old):
        if disk_patches() != old:
            raise Error("LLVM is unprepared and patch files have unstaged changes; prepare LLVM first")
        reconstructed_tree(base, old)
        print("LLVM is at the upstream pin; existing patches verified and preserved. Run setup before editing LLVM.")
        return
    git("merge-base", "--is-ancestor", base, head, sub=True)
    if out("rev-list", "--merges", f"{base}..{head}", sub=True):
        raise Error("Local LLVM patch commits must be linear (no merge commits)")
    with tempfile.TemporaryDirectory(prefix="ldb-export-") as tmp:
        paths = out(
            "format-patch", "--zero-commit", "--no-signature", "--full-index", "--binary",
            "--output-directory", tmp, f"{base}..{head}", sub=True,
        ).splitlines()
        new = {Path(path).name: Path(path).read_bytes() for path in paths}
        new["series"] = "".join(Path(path).name + "\n" for path in paths).encode()
    working = disk_patches()
    committed = head_patches()
    if git("rev-parse", "--verify", "HEAD", check=False).returncode:
        committed = old
    previous_path = state_path()
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    for name, candidate in (("working", working), ("staged", old)):
        if candidate != committed and candidate != new:
            # Several LLVM commits may precede one parent commit. Recognize
            # files produced by our previous export, not only parent HEAD.
            known_export = (
                previous.get("base") == base
                and fingerprint(base, candidate) == previous.get("fingerprint")
            )
            if not known_export:
                raise Error(f"The {name} generated patches contain manual edits. Refusing to overwrite them; apply those changes inside LLVM first.")
    expected = reconstructed_tree(base, new)
    if expected != out("rev-parse", "HEAD^{tree}", sub=True):
        raise Error("Exported patches do not reconstruct the development tree")
    PATCHES.mkdir(parents=True, exist_ok=True)
    for name in working.keys() - new.keys():
        (PATCHES / name).unlink()
    for name, contents in new.items():
        if working.get(name) != contents:
            (PATCHES / name).write_bytes(contents)
    if hook:
        git("add", "-A", "--", "patches/llvm")
    save_state(base, new, head)
    verb = "Exported and staged" if hook else "Exported"
    print(f"{verb} {len(series(new))} LLVM patches; upstream pin unchanged.")


def verify():
    info = metadata(staged=True)
    files = indexed_patches()
    if not available():
        raise Error("Initialize the LLVM submodule before verifying reconstruction")
    tree = reconstructed_tree(info["upstream_revision"], files)
    print(f"Verified {len(series(files))} patches against LLVM {info['llvm_major']}: tree {tree}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "export", "check", "hook", "post-commit", "install-hooks"])
    args = parser.parse_args()
    if args.command == "post-commit":
        # This hook starts inside the submodule. Parent Git operations must not
        # inherit its repository/index, unlike the parent's pre-commit hook.
        for key in REPO_ENV:
            os.environ.pop(key, None)
    try:
        if args.command == "setup":
            setup()
        elif args.command == "export":
            export()
        elif args.command == "check":
            verify()
        elif args.command in ("hook", "post-commit"):
            export(hook=True)
        else:
            install_hooks()
    except (Error, OSError, ValueError, KeyError) as exc:
        print(f"LDB: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
