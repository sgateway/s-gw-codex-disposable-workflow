# Try a disposable s-gw credential workflow with Codex

This small macOS and Linux exercise lets Codex prepare a credential-backed command without using a real account or API token. A person reviews and approves the exact local command before execution.

[Watch the 56-second terminal replay](./s-gw-disposable-token-replay.mp4) or [open the interactive replay](./replay.html).

The replay uses selected output from an actual `@s-gw/s-gw@0.1.22` CLI run on macOS arm64. The credential value is simulated data. Reading time was edited, and the approval in the replay was performed by the demonstration script. It is not a recording of a person approving in the product UI.

## Prerequisites

- macOS or Linux
- Node.js 20 or newer
- Python 3 and `printenv`
- `@s-gw/s-gw@0.1.22` installed

```bash
npm install -g @s-gw/s-gw@0.1.22
```

Clone this repository and open Codex in the repository folder.

## 1. Ask Codex to prepare the request

Send this prompt:

> Run `python3 trust_loop.py prepare` using the terminal. Read the generated receipt for the refused pending execution, report the run directory, and stop for my local approval. Use only this script's disposable state. Do not run the `approve` or `run` actions.

The script creates an isolated store under `runs/`, enrolls the fixed fake value `demo-token-value`, permits local `printenv`, and confirms that execution is refused while the request is pending. It does not inherit existing `SGW_*` settings.

## 2. Approve from your own terminal

Review `03-request.json` in the printed run directory. Confirm the executable, the `DEMO_TOKEN` argument, the environment binding, and the fake-token handle.

Run the exact approval command printed by the script:

```bash
python3 /absolute/path/to/trust_loop.py approve /absolute/path/to/runs/YOUR_RUN
```

This approves one transaction in the disposable store.

## 3. Ask Codex to finish

Send this prompt:

> Run `python3 trust_loop.py finish /absolute/path/to/runs/YOUR_RUN`. Verify the approved execution, sanitized output, refused reuse, and next request's pending state. Report the summary and receipts path.

The checked workflow verifies that:

- execution is refused while pending;
- the approved command succeeds with sanitized output;
- the fake value is absent from the returned result;
- the one-time request cannot be reused;
- a new equivalent request is pending again; and
- the disposable ledger and recovery state are removed.

If the flow is interrupted, clean it up with:

```bash
python3 trust_loop.py cleanup /absolute/path/to/runs/YOUR_RUN
```

For a fully scripted demonstration, run `python3 trust_loop.py run`. Use the three-step flow above when testing the approval handoff with a person.

This exercise demonstrates the local brokered request and sanitized-output path with a trusted local executable. It does not test a remote API, a real credential, MCP registration, or a live Codex UI.

If you try it, open a repository discussion or issue with the first unclear step and your approximate setup time. Keep real credentials and account details out of reports.

## References

- [s-gw quickstart for v0.1.22](https://github.com/sgateway/s-gw/blob/v0.1.22/docs/quickstart.md)
- [Approval settings for v0.1.22](https://github.com/sgateway/s-gw/blob/v0.1.22/docs/deployment.md)
- [Codex and other agent support for v0.1.22](https://github.com/sgateway/s-gw/blob/v0.1.22/docs/agents.md)
