#!/usr/bin/env python3
"""Three executable contracts, with no dependency on LLVM version or Python packages."""
import argparse
from collections import Counter
import ctypes
import errno
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVENT = struct.Struct("<IIIIQQQ")  # type, seconds, nanoseconds, tid, arg1..3
FLAGS = ["-O3", "-g", "-gdwarf-3", "-fno-omit-frame-pointer",
         "-fno-optimize-sibling-calls", "-fno-pie"]


def run(args, **kwargs):
    result = subprocess.run([str(arg) for arg in args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=60, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args}\n{result.stdout}")
    return result.stdout


def symbolize(tool, executable, address):
    lines = run([tool, f"--obj={executable}", "--inlining=false", hex(address)]).splitlines()
    return lines[0], lines[1]


def compiler_tests(args, out):
    hooks, host = out / "hooks.o", out / "host.o"
    for source, target in [("hooks.c", hooks), ("host.c", host)]:
        run([args.host_cc, *FLAGS, "-c", HERE / source, "-o", target])
    for name, marker, objects in [("frame", "FRAME OK", [hooks]),
                                   ("abi", "ABI OK", [hooks, host])]:
        exe = out / name
        run([args.clang, *FLAGS, "-no-pie", HERE / f"{name}.c", *objects, "-o", exe])
        output = run([exe], cwd=out)
        (out / f"{name}.log").write_text(output)
        assert marker in output and output.count("HOOKS init=1 exit=1") == 1, output
        if name == "frame":
            sites = re.findall(r"FRAME_SITE=(0x[0-9a-f]+)", output)
            assert len(sites) == 2, output
            for site in sites:
                function, location = symbolize(args.symbolizer, exe, int(site, 16))
                assert function == "frame_parent" and "frame.c:" in location, (function, location)
        print(f"PASS {name}", flush=True)


def events(path):
    data = path.read_bytes() if path.exists() else b""
    return list(EVENT.iter_unpack(data[:len(data) // EVENT.size * EVENT.size]))


def runtime_test(args, out):
    exe = out / "events"
    run([args.clang, *FLAGS, "-no-pie", HERE / "events.c",
         "-I", args.runtime / "include", args.runtime / "libldb.a", "-pthread", "-o", exe])
    # Claim the inherited runtime's fixed key exclusively. Never reuse/delete
    # another process's segment. Runtime shmget accepts this larger segment.
    libc = ctypes.CDLL(None, use_errno=True)
    shmid = libc.shmget(401916, 4096, 0o1000 | 0o2000 | 0o600)  # CREAT | EXCL
    if shmid < 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise RuntimeError("Shared-memory key 401916 already exists; run serially in a clean IPC environment")
        raise OSError(error, os.strerror(error))
    process = None
    symbols = {}
    event_path = out / "ldb.data"
    log_path = out / "events.log"
    observed = None
    try:
        env = os.environ.copy()
        env["LD_PRELOAD"] = str(args.runtime / "libshim.so")
        with log_path.open("w") as log:
            process = subprocess.Popen([str(exe)], cwd=out, env=env, stdin=subprocess.PIPE,
                                       stdout=log, stderr=subprocess.STDOUT, text=True)

            def wait_for(predicate):
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    records = events(event_path)
                    value = predicate(records)
                    if value:
                        return value
                    if process.poll() is not None:
                        raise RuntimeError(f"Runtime exited early ({process.returncode})\n{log_path.read_text()}")
                    time.sleep(0.01)
                counts = Counter(record[0] for record in events(event_path))
                raise RuntimeError(f"Timed out waiting for LDB output; event types/counts={dict(counts)}\n"
                                   f"Symbols seen: {symbols}\n{log_path.read_text()}")

            def tagged_stack(records):
                tags = {r[3]: r[1] * 10**9 + r[2] for r in records if r[0] == 2 and r[4] == 42}
                created = {r[3] for r in records if r[0] == 11}
                for record in records:
                    kind, sec, ns, tid, latency, rip, gen = record
                    if kind != 1 or tid not in tags or tid not in created:
                        continue
                    if sec * 10**9 + ns < tags[tid]:
                        continue
                    if rip not in symbols:
                        symbols[rip] = symbolize(args.symbolizer, exe, rip)
                    function, location = symbols[rip]
                    if function == "request_handler" and "events.c:" in location:
                        assert latency > 0 and gen > 0, record
                        return record

            observed = wait_for(tagged_stack)
            tid = observed[3]
            process.stdin.write("q")
            process.stdin.flush()
            wait_for(lambda records: any(r[0] == 4 and r[3] == tid and r[4] == 42 for r in records))
            process.stdin.write("x")
            process.stdin.flush()
            process.communicate(timeout=args.timeout)
            assert process.returncode == 0, log_path.read_text()
        records = events(event_path)
        assert event_path.stat().st_size % EVENT.size == 0, "Truncated event record"
        assert all(1 <= r[0] <= 12 and r[2] < 10**9 and r[3] > 0 for r in records)
        output = log_path.read_text()
        assert f"WORKER_TID={observed[3]}" in output and "EVENTS OK" in output, output
        (out / "observed.txt").write_text(
            f"tag=42 tid={observed[3]} latency_ns={observed[4]} generation={observed[6]}\n"
            f"return_site={hex(observed[5])} {symbols[observed[5]]}\n"
            f"event_counts={dict(Counter(r[0] for r in records))}\n")
        print("PASS events (tag 42, worker identity, symbolized request_handler call site)", flush=True)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        if libc.shmctl(shmid, 0, None) < 0:  # IPC_RMID: exclusively owned above
            raise OSError(ctypes.get_errno(), "Cannot remove test shared memory")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", type=Path, default=ROOT / "build/llvm/bin/clang")
    parser.add_argument("--symbolizer", type=Path, default=ROOT / "build/llvm/bin/llvm-symbolizer")
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime")
    parser.add_argument("--host-cc", default="cc")
    parser.add_argument("--output", type=Path, default=ROOT / "build/behavior")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    for name in ["clang", "symbolizer", "runtime"]:
        setattr(args, name, getattr(args, name).resolve())
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    # Fresh per-run directory keeps an old trace from satisfying this run.
    out = Path(tempfile.mkdtemp(prefix="run-", dir=args.output))
    print(f"Artifacts: {out}", flush=True)
    (out / "toolchain.txt").write_text(run([args.clang, "--version"]) + run([args.host_cc, "--version"]))
    compiler_tests(args, out)
    runtime_test(args, out)
    print("PASS all 3 behavior contracts", flush=True)


if __name__ == "__main__":
    main()
