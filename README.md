# Gate

Deterministic PreToolUse gate for Claude Code. Blocks Write/Edit/Bash tool calls unless Commander has explicitly authorized action. Counts instance drift in real time and halts drifted instances.

## Files

| File | Role |
|---|---|
| `hook-gate-src/main.go` | Gate binary source — rules 1–4, allow/deny, drift counter mutation |
| `hook-gate-src/prompt-gate.sh` | UserPromptSubmit hook — detects signal words, writes `gate-state.json` |
| `hook-gate-src/go.mod` | Go module |
| `hook-gate.exe` | Compiled binary (built from `hook-gate-src/`) |
| `drift-analyzer.py` | Reads `conversations.db`, scores drift phrases in last 10 messages, writes drift fields to `gate-state.json` |
| `conversation_logger_server.py` | `ConversationIndexer` — pulls Claude Code JSONL transcripts into `conversations.db` |
| `gate-state.json` | Runtime state — shared by prompt hook, gate binary, and drift analyzer |
| `conversations.db` | SQLite index of JSONL transcripts (runtime, regenerates) |

## Signal vocabulary

Single Mandarin tokens, chosen so they never appear in conversational English.

- **`hao`** (好 — good) — the only action signal. Presence as a whole token unlocks Write/Edit/Bash for that message. Without `hao`, only read-only tools work.
- **`tingzhi`** (停止 — halt) — sticky halt. Sets `halt_latch = true` in state. Persists across messages until cleared by `hao`.
- **`kaisuo`** (开锁 — unlock) — testing override. Resets `drift_block_count` to 0 for one turn and forces `drift_halt = false`. For test use only.

## Rules

The gate runs on every Write/Edit/Bash tool call. Read-only tools (`Read`, `Glob`, `Grep`, `ToolSearch`, `Agent`) and MCP tools bypass it entirely. Rules fire in order; first match wins.

| # | Rule | Condition | Behavior |
|---|---|---|---|
| 2 | Drift halt | `drift_block_count >= 5` OR `drift_halt == true` | `writeDeny` — does **not** increment counter. Instance is spent, rotate. |
| 1 | Halt latch | `halt_latch == true` | `deny` — increments counter. Say `hao` (without `tingzhi`) to clear. |
| 3 | No `hao` | `has_trigger == false` | `deny` — increments counter. |
| 4 | Git command | Bash command matches `\bgit\b` and `"git"` not in prompt | `deny` — increments counter. |

Rule 2 runs first so a spent instance cannot act even with `hao` present.

## Drift detection

Two independent signals, either crosses → block.

**Source A — gate-side real-time counter (`drift_block_count`)**
- Maintained by `main.go`. Every `deny()` increments. Every successful gated `allowWithCredit()` decrements (floor 0).
- Counts actual unauthorized action attempts. No lag, no semantic matching.
- Threshold: 5.

**Source B — analyzer-side phrase score (`drift_score` + `drift_halt`)**
- Maintained by `drift-analyzer.py`. Runs on every `UserPromptSubmit` via `prompt-gate.sh`.
- Indexes JSONL into `conversations.db` (via `ConversationIndexer`), reads last 10 messages of latest session, counts occurrences of entries in `DRIFT_PHRASES` across assistant messages plus `"gate blocked"` in user tool_results.
- Natural counter-balance: clean conversation pushes drift phrases out of the 10-message window → score drops on its own.
- Threshold: 5.

## State file

`gate-state.json` fields:

```json
{
  "prompt": "<last user message>",
  "has_trigger": false,
  "halt_latch": false,
  "drift_halt": false,
  "drift_score": 0,
  "drift_block_count": 0
}
```

Written by `prompt-gate.sh` (prompt, has_trigger, halt_latch, drift_block_count preservation), merged by `drift-analyzer.py` (drift_halt, drift_score, drift_signals), mutated by `hook-gate.exe` (drift_block_count ± on each gated call).

## Build

```bash
cd hook-gate-src
go build -o ../hook-gate.exe
```

## Install (Claude Code hooks)

Register in Claude Code `settings.json` under `hooks`:

- `PreToolUse` → `C:/gate/hook-gate.exe`
- `UserPromptSubmit` → `C:/gate/hook-gate-src/prompt-gate.sh`
