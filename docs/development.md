# Development workflow

## Repositories and remotes

The parent is `cheerioskun/ldb`, normally on `main`; its `origin` is our public
repository. The LLVM submodule's `origin` is `llvm/llvm-project`. There is no
compiler fork, no published compiler-development branch, and no published
patch-only branch.

The submodule Git link and `toolchain.json` both identify the unmodified upstream
commit. Setup verifies they agree. Compiler changes live in `patches/llvm/`,
on the same project branch as LDB runtime/tests.

## Automatic export

`make setup` installs two native hooks:

- LLVM's local `post-commit` exports and stages only `patches/llvm/`. Thus a
  compiler-only change is already staged before the parent commit starts.
- The parent's `pre-commit` rechecks and exports the series, guards the upstream
  pin, and preserves unrelated staged/unstaged parent files.

The additional post-commit hook handles a Git edge case: if the parent initially
has no staged changes, Git can reject a commit even if pre-commit adds files.
It also means normal compiler edits need no manual export command.

Export uses `git format-patch`, with stable zeroed commit headers, and verifies
that applying the result to the upstream baseline reconstructs the exact local
LLVM tree. It rejects merge commits, uncommitted/untracked LLVM files, and
manual edits to generated patches that would be overwritten. Each normal LLVM
commit becomes one patch; use local amend/rebase/squash to refine the series.

`scripts/export-llvm-patches.sh` remains available for recovery/manual use, but
is not a routine required step. Stage its output if using it manually.

Git does not clone hook activation. Run setup in each new clone. Hooks can be
bypassed; CI independently reconstructs the staged patch series. Do not use
`git commit --only <paths>` for compiler changes: use ordinary index-based
staging so generated patch files can join the commit.

## Setup and branch switching

On a fresh clone, setup initializes the submodule at its recorded commit and
applies the series as local Git commits. It stores preparation metadata inside
the submodule's Git directory, not tracked project files. Sparse checkout keeps
the selected LLVM project directories in the working tree.

On a prepared checkout, setup is idempotent and leaves in-progress source edits
alone. If the parent pin/patch series changes and LLVM has unexported development
commits or dirty source, setup refuses to overwrite them. Commit/export or save
that work first. A clean, recognized generated checkout may be replaced with
the newly selected pinned series.

Before switching parent branches, commit the LLVM development changes and the
resulting parent patch changes. Then switch the parent branch and run setup.
Avoid `git submodule update --force` and broad reset/clean commands on a checkout
containing development work.

## Upgrading the upstream pin

Treat this as an explicit change: save current compiler work, select the new
upstream revision, update the staged submodule Git link and `toolchain.json`
together, and adapt the patch series. The hook will reject accidentally staging
local compiler commits as the upstream pin. It will not silently decide that a
new compiler-development HEAD is a legitimate upstream upgrade.

Keep toolchain changes separate from shared behavioral tests. In particular,
the first `llvm-14` test commits should accept compiler/runtime paths and avoid
matching version-specific LLVM IR or entire assembly listings.
