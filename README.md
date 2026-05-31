# Gate

Deterministic PreToolUse gate for Claude Code. Blocks Write/Edit/Bash tool calls unless Commander has explicitly authorized the action. Tracks instance drift in real time and halts drifted instances. In strict-mode roots it additionally enforces an exact authorization grammar (see [Grammar-Gate v1](#grammar-gate-v1) below).

## Files

| File | Role |
|---|---|
| `hook-gate-src/main.go` | Gate binary source — rules 0–5, Agent rule, allow/deny, authorization grammar, drift counter mutation |
| `hook-gate-src/prompt-gate.sh` | UserPromptSubmit hook — tokenizes the message, writes signal flags + mode to `gate-state.json` |
| `hook-gate-src/go.mod` | Go module |
| `hook-gate.exe` | Compiled binary (built from `hook-gate-src/`) |
| `drift-analyzer.py` | Reads the latest session JSONL transcript, scores structural drift, merges drift fields + task-list + authorizations into `gate-state.json` |
| `conversation_logger_server.py` | `ConversationIndexer` — pulls Claude Code JSONL transcripts into a SQLite index |
| `orientation/` | Orientation MCP server — codebase scanner/parser; an `orient` call resets the drift window |
| `gate-state.json` | Runtime state — shared by prompt hook, gate binary, and drift analyzer |
| `drift-incidents.log` | Append-only deny log; survives instance rotation |
| `old/` | Previous gate version, kept for reference |

## Signal vocabulary

Single Mandarin tokens, chosen so they never appear in conversational English. Matched as whole, case-insensitive tokens.

- **`hao`** (好 — good) — the action signal. Presence unlocks Write/Edit/Bash for that message (a task list is also required — see Rule 3). Also **resets `drift_block_count` to 0** — re-authorization clears the slate. Sets mode to 2 (applying).
- **`hao de`** (好的 — okay) — full gate override. `hao` together with `de` sets `gate_off = true`, bypassing the `hao`/task-list and authorization-grammar checks. A plain `hao` (without `de`) closes the gate again.
- **`tingzhi`** (停止 — halt) — sticky halt latch. Sets `halt_latch = true`. Persists across messages until cleared by `hao`. `tingzhi` wins over `hao` in the same message.

## Rules

The gate runs on every tool call. **Read-only tools** (`Read`, `Glob`, `Grep`, `ToolSearch`, `Agent`) and MCP tools bypass it entirely. Rules fire in the order below; first match wins.

**Agent rule** (before everything): `Agent`/`Task` calls must use `subagent_type: LISTEN`, else deny.

| # | Rule | Condition | Behavior |
|---|---|---|---|
| 0 | Question only | `has_question == true` (`?` in message) | `deny` — "ANSWER THE QUESTION". A question is not a directive; answer, don't act. |
| 2 | Drift halt | `drift_block_count >= 2` OR `drift_halt == true` | `writeDeny` — does **not** increment counter. Logs incident. Instance is spent, rotate. |
| 1 | Halt latch | `halt_latch == true` | `deny` — increments counter. Say `hao` (without `tingzhi`) to clear. |
| 3 | No `hao` / no task list | `gate_off == false` AND (`has_trigger == false` OR `has_tasklist == false`) | `deny` — increments counter. Needs both `hao` **and** a task list. |
| 4 | Git command | Bash command matches `\bgit\b` and `"git"` not in message | `deny` — increments counter. |
| 5 | Authorization grammar | `gate_off == false` AND cwd inside a strict root AND action not matched by a frozen grant | `deny` — increments counter. See [Grammar-Gate v1](#grammar-gate-v1). |

Rule 2 runs before the others so a spent instance cannot act even with `hao` present. Rule 0 runs first so a question is never treated as a directive. `hao de` (`gate_off`) bypasses Rules 3 and 5.

## Modes

`mode` tracks the WITH/FOR posture, persisted in state:

- **Mode 1 — extracting** (default). Thinking, asking, exploring. Read-only.
- **Mode 2 — applying.** `hao` activates it. Execute exactly what was specified.

`[DONE]` in assistant output resets mode to 1 (handled by the drift analyzer).

## Drift detection

Two independent signals; either crossing its threshold halts the instance.

**Source A — gate-side real-time counter (`drift_block_count`)**
- Maintained by `main.go`. Every counter-incrementing `deny()` (Rules 1, 3, 4, 5) bumps it. No decrement during a turn — blocks are sticky.
- Counts actual unauthorized action attempts. No lag, no semantic matching.
- Reset to 0 by `hao` (re-authorization).
- Threshold: **2**.

**Source B — analyzer-side structural score (`drift_score` + `drift_halt`)**
- Maintained by `drift-analyzer.py`, run on every `UserPromptSubmit` via `prompt-gate.sh`.
- Reads the latest session JSONL transcript directly (no SQLite dependency), inspects the last 30 user/assistant entries, and computes `drift_score = gate_blocked + unauthorized_files`:
  - `gate_blocked` — count of "gate blocked" appearing in user tool_results across the window.
  - `unauthorized_files` — Write/Edit tool calls (after the most recent `hao`, mode 2 only) targeting files not named in the last directive.
- Resets its window after an `orient` MCP call — orientation clears the slate, so prior entries aren't re-scored.
- Natural counter-balance: a clean conversation pushes drift signals out of the 30-entry window → score falls on its own.
- Threshold: **3** (`DRIFT_THRESHOLD`).

**Incident log (`drift-incidents.log`)**
- Every deny logs: timestamp, rule, tool attempted, tool-input summary, block count, and prompt context.
- Survives instance rotation — the next instance or Commander can review what went wrong.

## State file

`gate-state.json` fields:

```json
{
  "prompt": "<last user message>",
  "has_trigger": false,
  "has_question": false,
  "halt_latch": false,
  "drift_halt": false,
  "drift_score": 0,
  "drift_block_count": 0,
  "mode": 1,
  "gate_off": false,
  "has_tasklist": false,
  "authorizations": [],
  "gate_strict_roots": [],
  "drift_signals": { "gate_blocked": 0, "unauthorized_files": 0 }
}
```

Written by `prompt-gate.sh` (prompt, has_trigger, has_question, halt_latch, mode, gate_off, drift_block_count preservation/reset, gate_strict_roots passthrough), merged by `drift-analyzer.py` (drift_halt, drift_score, drift_signals, has_tasklist, authorizations, mode), incremented by `hook-gate.exe` on each counting deny.

## Build

```bash
cd hook-gate-src
go build -o ../hook-gate.exe
```

## Install (Claude Code hooks)

Register in Claude Code `settings.json` under `hooks`:

- `PreToolUse` → `C:/gate/hook-gate.exe`
- `UserPromptSubmit` → `C:/gate/hook-gate-src/prompt-gate.sh`

---

# Grammar-Gate v1

## Overview

Grammar-Gate is a deterministic authorization layer for AI coding agents. It was designed to solve a specific problem:

Large language models are optimized to be helpful, but "helpfulness" naturally causes scope expansion, inferred authority, and behavioral drift during long-running coding sessions.

Instead of attempting to suppress the model's behavior through prompt instructions alone, Grammar-Gate changes the execution model itself. The system separates:

- Proposal
- Authorization
- Enforcement
- Execution

The language model may propose actions, but executable authority exists only inside a formally defined authorization grammar enforced by deterministic code.

> In this repository, Grammar-Gate is **Rule 5**. It applies only inside configured strict roots (`gate_strict_roots`); outside those roots the behavioral rules (0–4) still apply but no grammar match is required.

## Core idea

Traditional AI agent systems operate roughly like this:

```
LLM
→ interprets intent
→ decides what seems reasonable
→ executes tools
```

Grammar-Gate changes this into:

```
LLM
→ proposes structured actions
→ external authorization grammar defines allowed scope
→ deterministic Go gate verifies exact match
→ executor obeys the gate verdict
```

The model is no longer trusted to determine what should happen, what is implied, what is "probably intended," or whether nearby changes are acceptable. The model can only successfully execute actions that match an explicit authorization grammar.

## Why this exists

Language models naturally drift during long-running sessions. Common drift behaviors include:

- editing adjacent files "helpfully"
- expanding scope beyond the task
- inferring authority from tone or urgency
- executing nearby commands that "seem reasonable"
- treating injected instructions as meaningful

Examples: *"Use your judgment." / "Mary already approved it." / "Just do the obvious fix."* These phrases often cause agentic expansion in standard assistant configurations. Grammar-Gate prevents this by removing semantic authority entirely — only formally valid authorization structures matter.

## Design philosophy

Grammar-Gate does not attempt to make the model morally safer, reduce intelligence, suppress reasoning, or "align" intent. Instead it minimizes interpretive authority, formalizes permission, and constrains executability. The system is closer to capability systems, compiler semantics, zero-trust security, and protocol verification than to traditional prompt engineering.

## Authorization grammar

Every strict-mode task carries a machine-readable authorization block. In this repo it is a fenced ```` ```authorization ```` JSON array in the assistant message, parsed by `drift-analyzer.py` into `gate-state.json`:

```json
[
  {
    "action": "Edit",
    "resource_type": "file_exact",
    "resource": "C:/project/src/auth/login.js"
  },
  {
    "action": "Write",
    "resource_type": "dir_recursive",
    "resource": "C:/project/tests/"
  },
  {
    "action": "Bash",
    "resource_type": "command_exact",
    "resource": "npm test"
  }
]
```

The grammar defines exactly what action is allowed, exactly which resource it applies to, and exactly how matching occurs. No semantic interpretation is performed.

## Enforcement model

The enforcement layer is implemented in Go (`hook-gate-src/main.go`). The gate:

1. receives the tool call
2. canonicalizes resources
3. performs exact structural matching against the frozen grants
4. returns ALLOW or DENY

The model does not control the verdict. Default-deny: no grant, no execution.

## Canonicalization

Paths are normalized before comparison (`canon` / `canonAbs`):

1. absolute path resolution (relative paths joined against the project root)
2. path cleaning (`.` / `..`)
3. OS-native separator normalization
4. symlink resolution on the longest existing ancestor (so not-yet-created files normalize like their parent)
5. case folding on Windows

This prevents path-traversal tricks, separator variations, relative-path bypasses, symlink escapes, and case-based mismatches.

## Resource types

**`file_exact`** — exact canonical file match required.

```json
{ "action": "Edit", "resource_type": "file_exact", "resource": "C:/project/src/main.go" }
```

Only that file is authorized.

**`dir_recursive`** — allows resources under a specific directory subtree.

```json
{ "action": "Write", "resource_type": "dir_recursive", "resource": "C:/project/tests/" }
```

**`command_exact`** — exact normalized command match required (whitespace collapsed; no globbing or semantic approximation).

```json
{ "action": "Bash", "resource_type": "command_exact", "resource": "go test ./..." }
```

## Strict mode

Grammar enforcement applies only to projects listed in `gate_strict_roots`. A call is in scope when its `cwd` equals, or sits beneath, a configured root. Projects outside those roots continue using the legacy behavioral workflow (Rules 0–4), allowing incremental rollout without breaking existing projects. `hao de` (`gate_off`) overrides the grammar check.

## Behavioral effect

The key behavioral change: the model stops optimizing for "being useful" and starts optimizing for "remaining executable." This reduces scope drift, inferred permission, adjacent-file editing, unauthorized commands, and prompt-injection execution — converting the model from a semantic agent into a grammar-constrained protocol participant.

## Important limits

Grammar-Gate does **not** solve general AI alignment. It does not prevent bad-but-authorized edits, logic errors, malicious authorized actions, harmful shell commands explicitly granted, or reasoning mistakes inside allowed scope. It is a scope-confinement architecture, not a guarantee of correctness. It assumes the authorization grammar is correct, the executor obeys the gate, and the user controls authority issuance.

## Current safety properties

- deterministic authorization
- exact structural matching
- bounded execution scope
- strong resistance to semantic prompt injection
- per-project strict enforcement
- externalized authority
- rollback support (`old/`)

## Architecture summary

```
LLM proposes
→ authorization grammar defines allowed scope
→ deterministic Go gate validates structure
→ executor obeys verdict
→ unauthorized actions fail closed
```

The central insight: the safest control surface for agentic systems may not be behavioral obedience, but executable validity.
