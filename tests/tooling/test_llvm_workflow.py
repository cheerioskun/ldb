"""Exercise real nested Git repositories without downloading or compiling LLVM."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[2]


class LLVMWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ldb-workflow-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.upstream = self.home / "upstream"
        self.root = self.home / "project"
        self.env = os.environ.copy()
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX"):
            self.env.pop(key, None)
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
            GIT_ALLOW_PROTOCOL="file", GIT_AUTHOR_NAME="LDB fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid", GIT_COMMITTER_NAME="LDB fixture",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
        )
        self.upstream.mkdir()
        self.git(self.upstream, "init", "-b", "main")
        (self.upstream / "llvm").mkdir()
        (self.upstream / "llvm/example.c").write_text("int example = 0;\n")
        self.git(self.upstream, "add", ".")
        self.git(self.upstream, "commit", "-m", "Upstream fixture")
        self.base = self.git(self.upstream, "rev-parse", "HEAD").stdout.strip()
        self.root.mkdir()
        self.git(self.root, "init", "-b", "main")
        shutil.copytree(PROJECT / "scripts", self.root / "scripts")
        shutil.copytree(PROJECT / ".githooks", self.root / ".githooks")
        self.git(self.root, "submodule", "add", str(self.upstream), "third_party/llvm")
        self.sub = self.root / "third_party/llvm"
        (self.root / "patches/llvm").mkdir(parents=True)
        (self.root / "patches/llvm/series").write_text("")
        (self.root / "README.md").write_text("baseline\n")
        (self.root / "toolchain.json").write_text(json.dumps({
            "llvm_major": 14, "upstream_revision": self.base, "sparse_paths": ["llvm"],
        }))
        self.git(self.root, "add", ".")
        self.git(self.root, "commit", "-m", "Initial project")
        self.tool("setup")

    def run_cmd(self, args, cwd, ok=True):
        result = subprocess.run(args, cwd=cwd, env=self.env, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, f"{args}\n{result.stdout}\n{result.stderr}")
        return result

    def git(self, cwd, *args, ok=True):
        return self.run_cmd(["git", *args], cwd, ok)

    def tool(self, command, ok=True, root=None):
        root = root or self.root
        return self.run_cmd([sys.executable, str(root / "scripts/llvm.py"), command], root, ok)

    def change(self, value=1):
        (self.sub / "llvm/example.c").write_text(f"int example = {value};\n")
        self.git(self.sub, "add", "llvm/example.c")
        self.git(self.sub, "commit", "-m", f"Change LLVM to {value}")

    def parent_commit(self):
        return self.git(self.root, "commit", "-m", "Record LLVM change")

    def test_hook_exports_only_generated_patches_and_preserves_partial_staging(self):
        self.change()
        readme = self.root / "README.md"
        readme.write_text("baseline\nstaged\n")
        self.git(self.root, "add", "README.md")
        readme.write_text("baseline\nstaged\nunstaged\n")
        (self.root / "unrelated.txt").write_text("leave me alone\n")
        self.parent_commit()
        self.assertEqual(self.git(self.root, "show", "HEAD:README.md").stdout, "baseline\nstaged\n")
        self.assertIn("unstaged", readme.read_text())
        self.assertIn("?? unrelated.txt", self.git(self.root, "status", "--short").stdout)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD:third_party/llvm").stdout.strip(), self.base)
        self.assertTrue(list((self.root / "patches/llvm").glob("*.patch")))
        self.tool("check")

    def test_parent_commit_can_contain_only_automatic_llvm_export(self):
        self.change()
        self.assertIn("patches/llvm", self.git(self.root, "diff", "--cached", "--name-only").stdout)
        self.parent_commit()
        self.assertIn("patches/llvm", self.git(self.root, "show", "--stat", "HEAD").stdout)

    def test_dirty_llvm_blocks_commit_without_changing_source_or_index(self):
        (self.sub / "llvm/example.c").write_text("uncommitted\n")
        (self.root / "README.md").write_text("stage this\n")
        self.git(self.root, "add", "README.md")
        before = self.git(self.root, "diff", "--cached").stdout
        result = self.git(self.root, "commit", "-m", "Must fail", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncommitted", result.stderr)
        self.assertEqual(self.git(self.root, "diff", "--cached").stdout, before)
        self.assertEqual((self.sub / "llvm/example.c").read_text(), "uncommitted\n")

    def test_untracked_llvm_source_is_not_silently_omitted(self):
        (self.sub / "llvm/new.c").write_text("int new_file;\n")
        self.assertNotEqual(self.tool("export", ok=False).returncode, 0)

    def test_accidentally_staged_development_pin_is_rejected(self):
        self.change()
        self.git(self.root, "add", "third_party/llvm")
        result = self.tool("hook", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pin differs", result.stderr)

    def test_manual_patch_edits_are_not_overwritten(self):
        self.change()
        self.parent_commit()
        patch = next((self.root / "patches/llvm").glob("*.patch"))
        patch.write_text(patch.read_text() + "manual edit\n")
        result = self.tool("export", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(patch.read_text().endswith("manual edit\n"))

    def test_stale_patch_files_are_removed_after_squashing(self):
        self.change(1)
        self.change(2)
        self.parent_commit()
        self.assertEqual(len(list((self.root / "patches/llvm").glob("*.patch"))), 2)
        self.git(self.sub, "reset", "--soft", self.base)
        self.git(self.sub, "commit", "-m", "Consolidate LLVM changes")
        self.parent_commit()
        self.assertEqual(len(list((self.root / "patches/llvm").glob("*.patch"))), 1)
        self.tool("check")

    def test_setup_is_idempotent_and_preserves_developer_edits(self):
        self.change()
        self.parent_commit()
        head = self.git(self.sub, "rev-parse", "HEAD").stdout
        (self.sub / "llvm/example.c").write_text("in progress\n")
        self.tool("setup")
        self.assertEqual(self.git(self.sub, "rev-parse", "HEAD").stdout, head)
        self.assertEqual((self.sub / "llvm/example.c").read_text(), "in progress\n")

    def test_fresh_clone_reconstructs_exact_source_tree(self):
        self.change()
        self.parent_commit()
        replica = self.home / "replica"
        self.git(self.home, "clone", str(self.root), str(replica))
        self.tool("setup", root=replica)
        expected = self.git(self.sub, "rev-parse", "HEAD^{tree}").stdout
        actual = self.git(replica / "third_party/llvm", "rev-parse", "HEAD^{tree}").stdout
        self.assertEqual(actual, expected)
        self.tool("check", root=replica)
        self.tool("hook", root=replica)
        self.assertEqual(self.git(replica, "diff", "--cached").stdout, "")
        self.assertEqual(self.git(replica, "config", "--get", "core.hooksPath").stdout.strip(), ".githooks")

    def test_corrupt_staged_patch_fails_reconstruction_without_source_changes(self):
        self.change()
        self.parent_commit()
        patch = next((self.root / "patches/llvm").glob("*.patch"))
        patch.write_text(patch.read_text().replace("-int example = 0;", "-int example = 999;"))
        self.git(self.root, "add", "patches/llvm")
        head = self.git(self.sub, "rev-parse", "HEAD").stdout
        self.assertNotEqual(self.tool("check", ok=False).returncode, 0)
        self.assertEqual(self.git(self.sub, "rev-parse", "HEAD").stdout, head)
        self.assertEqual(self.git(self.sub, "status", "--porcelain").stdout, "")


if __name__ == "__main__":
    unittest.main()
