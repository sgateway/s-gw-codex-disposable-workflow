#!/usr/bin/env python3
"""Exercise installed s-gw with a fixed fake credential and isolated local state."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent
FAKE_TOKEN = "demo-token-value"
DEMO_PASSPHRASE = "disposable-demo-only-passphrase-not-for-real-credentials"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_run(run_dir):
    run_dir = Path(run_dir).resolve()
    if run_dir.parent != ROOT / "runs" or not (run_dir / "run.json").is_file():
        raise ValueError("Use a run directory created by this script under ./runs/.")
    state = json.loads((run_dir / "run.json").read_text())
    if state["runDirectory"] != str(run_dir):
        raise ValueError("Run-directory identity does not match.")
    return run_dir, state


def command(run_dir, state, name, args, stdin=None, expect_ok=True):
    tmp_dir = run_dir / "state" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": state["safePath"],
        "TMPDIR": str(tmp_dir),
        "LANG": "en_US.UTF-8",
        "SGW_HOME": str(run_dir / "state" / "home"),
        "SGW_RECOVERY_HOME": str(run_dir / "state" / "recovery"),
        "SGW_MASTER_PASSPHRASE": DEMO_PASSPHRASE,
        "SGW_SECRET_BACKEND": "local",
        "SGW_DISABLE_KEYCHAIN": "1",
        "SGW_DISABLE_UPDATE_CHECK": "1",
    }
    cmd = [state["executable"], *args]
    started = utc_now()
    tick = time.monotonic()
    result = subprocess.run(cmd, input=stdin, text=True, capture_output=True,
                            env=env, cwd=run_dir, timeout=45)
    receipt = {
        "startedAtUtc": started,
        "elapsedSeconds": round(time.monotonic() - tick, 3),
        "argv": cmd,
        "stdin": "fixed fake token via stdin" if stdin is not None else None,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    save(run_dir / (name + ".json"), receipt)
    with (run_dir / "transcript.txt").open("a") as stream:
        stream.write("$ " + shlex.join(cmd) + "\n")
        stream.write(result.stdout + result.stderr)
        stream.write("[exit " + str(result.returncode) + "]\n\n")
    print(name + ": exit " + str(result.returncode), flush=True)
    if expect_ok and result.returncode != 0:
        raise RuntimeError(name + " failed. Read " + str(run_dir / (name + ".json")))
    if not expect_ok and result.returncode == 0:
        raise AssertionError(name + " unexpectedly succeeded.")
    return json.loads(result.stdout) if expect_ok else receipt


def prepare():
    executable = shutil.which("s-gw")
    printenv = shutil.which("printenv")
    node = shutil.which("node")
    if not all((executable, printenv, node)):
        raise RuntimeError("Install s-gw and Node.js 20+ first; printenv is also required.")
    package = Path(executable).resolve().parent.parent / "package.json"
    package_data = json.loads(package.read_text())
    if package_data.get("name") != "@s-gw/s-gw":
        raise RuntimeError("Expected the scoped npm s-gw installation.")
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    run_dir = runs / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(mode=0o700)
    state = {
        "runDirectory": str(run_dir),
        "startedAtUtc": utc_now(),
        "executable": executable,
        "resolvedExecutable": str(Path(executable).resolve()),
        "executableSha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
        "packageVersion": package_data["version"],
        "platform": platform.platform(),
        "safePath": os.pathsep.join(dict.fromkeys([
            str(Path(node).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"
        ])),
        "simulatedCredential": True,
        "approvalMode": "per-transaction",
    }
    save(run_dir / "run.json", state)
    command(run_dir, state, "01-init", ["init"])
    secret = command(run_dir, state, "02-enroll", [
        "secret", "add", "--name", "disposable-demo", "--type", "api-token",
        "--value-stdin", "--inject-env", "DEMO_TOKEN", "--allow-command", printenv
    ], stdin=FAKE_TOKEN)
    state["handle"] = secret["handle"]
    state["requestArgs"] = [
        "request", "env-command", state["handle"], "--command", printenv,
        "--arg", "DEMO_TOKEN", "--inject-env", "DEMO_TOKEN",
        "--reason", "Codex disposable-token tutorial"
    ]
    req = command(run_dir, state, "03-request", state["requestArgs"])
    if req["state"] != "pending":
        raise AssertionError("A new disposable request must be pending.")
    state["requestId"] = req["id"]
    save(run_dir / "run.json", state)
    refused = command(run_dir, state, "04-pending-refused", ["execute", req["id"]],
                      expect_ok=False)
    if "pending" not in refused["stderr"].lower():
        raise AssertionError("Expected refusal to identify the pending state.")
    save(ROOT / "latest.json", {"runDirectory": str(run_dir)})
    print("Prepared isolated run: " + str(run_dir))
    print("Local operator command: python3 " + shlex.quote(str(Path(__file__).resolve()))
          + " approve " + shlex.quote(str(run_dir)))
    return run_dir


def approve(run_dir):
    run_dir, state = load_run(run_dir)
    approval = command(run_dir, state, "05-local-approval", [
        "approve", state["requestId"], "--mode", "per-transaction"
    ])
    if approval["state"] != "approved":
        raise AssertionError("Expected approved request.")
    print("Approved once in this disposable store.")


def finish(run_dir):
    run_dir, state = load_run(run_dir)
    output = command(run_dir, state, "06-approved-execution", ["execute", state["requestId"]])
    if output.get("exitCode") != 0 or output.get("sanitized") is not True:
        raise AssertionError("Expected sanitized successful execution.")
    if FAKE_TOKEN in json.dumps(output) or "<<SGW_SECRET:" not in output.get("stdout", ""):
        raise AssertionError("The returned output did not replace the fake token with a handle.")
    if not output.get("proof", "").startswith("s-gw-proof:"):
        raise AssertionError("Expected an s-gw execution proof.")
    repeat = command(run_dir, state, "07-repeat-refused", ["execute", state["requestId"]],
                     expect_ok=False)
    if "executed" not in repeat["stderr"].lower():
        raise AssertionError("Expected refusal because the request is already executed.")
    next_req = command(run_dir, state, "08-next-request", state["requestArgs"])
    if next_req["state"] != "pending" or next_req["id"] == state["requestId"]:
        raise AssertionError("Per-transaction approval must not approve the next request.")
    summary = {
        "verifiedAtUtc": utc_now(),
        "packageVersion": state["packageVersion"],
        "simulatedCredential": True,
        "pendingExecutionRefused": True,
        "explicitLocalCliApproval": True,
        "approvalMode": "per-transaction",
        "approvedExecutionExitCode": output["exitCode"],
        "sanitized": output["sanitized"],
        "fakeValueAbsentFromReturnedOutput": True,
        "executedRequestCannotBeReused": True,
        "nextEquivalentRequestState": next_req["state"],
        "humanSetupTimeMeasured": False,
        "liveClientUiRecorded": False,
    }
    shutil.rmtree(run_dir / "state")
    summary["disposableStateRemoved"] = not (run_dir / "state").exists()
    save(run_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    print("Receipts: " + str(run_dir))


def cleanup(run_dir):
    run_dir, _ = load_run(run_dir)
    state_dir = run_dir / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    print("Disposable state removed: " + str(state_dir))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "prepare", "approve", "finish", "cleanup"])
    parser.add_argument("run_directory", nargs="?")
    args = parser.parse_args()
    if args.action in ("approve", "finish", "cleanup") and not args.run_directory:
        parser.error("approve, finish, and cleanup require a run directory")
    if args.action == "prepare":
        prepare()
    elif args.action == "approve":
        approve(args.run_directory)
    elif args.action == "finish":
        finish(args.run_directory)
    elif args.action == "cleanup":
        cleanup(args.run_directory)
    else:
        run_dir = prepare()
        print("Scripted demonstration: performing the explicit local CLI approval now.")
        approve(run_dir)
        finish(run_dir)


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
