.PHONY: all setup compiler runtime check-patches test-tooling test-behavior

all: runtime

setup:
	./scripts/setup-llvm.sh

compiler:
	./scripts/build-llvm.sh

runtime: compiler
	$(MAKE) -C runtime LLVM_BUILD="$(CURDIR)/build/llvm"

check-patches:
	./scripts/check-llvm-patches.sh

test-tooling:
	python3 -m unittest discover -s tests/tooling -v

# Uses an already built compiler/runtime; does not hide a rebuild in a test run.
test-behavior:
	python3 tests/behavior/run.py
