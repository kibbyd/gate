# Agent Gate

A deterministic two-hook gating system for Claude Code that enforces permission rules by analyzing the user's message before allowing tool calls.

## How It Works

Two hooks work together through a shared state file:

1. **UserPromptSubmit hook** (`prompt-gate.sh`) — fires when the user sends a message. Analyzes the message and writes flags to `gate-state.json`:
   - Contains `?` → `is_question = true`
   - Contains `STOP` → `said_stop = true`
   - Contains an action signal (go, do it, proceed, fix it, commit, push, or starts with an imperative verb) → `has_action = true`

2. **PreToolUse hook** (`hook-gate.exe`) — fires before every Edit, Write, or Bash tool call. Reads the state file and enforces rules:

| Rule | Condition | Decision |
|------|-----------|----------|
| Rule 1 | Question detected, no action signal | **deny** — respond with words only |
| Rule 2 | No action signal in user's message | **deny** — wait for explicit instruction |
| Rule 3 | User said STOP | **deny** — all actions frozen |
| Rule 5 | Destructive git command without "revert" in message | **deny** |
| Rule 6 | git commit/push without "commit"/"push" in message | **deny** |
| Rule 12 | Any Write or Edit tool call | **ask** — prompts user for approval |

Read-only tools (Read, Glob, Grep, ToolSearch, Agent) always pass.

## Setup

### 1. Install Go

The gate binary is written in Go. Install from https://go.dev/dl/

### 2. Build the binary

```
cd C:\gate\hook-gate-src
go build -o C:\gate\hook-gate.exe .
```

### 3. Configure hooks

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"C:/gate/hook-gate-src/prompt-gate.sh\"",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "C:/gate/hook-gate.exe",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 4. Python dependency

`prompt-gate.sh` uses Python to parse the user's message. Python 3 must be on PATH.

## Files

```
C:\gate\
  hook-gate.exe          — compiled Go binary (PreToolUse hook)
  gate-state.json        — shared state file (auto-generated at runtime)
  README.md              — this file
  hook-gate-src\
    main.go              — Go source for the PreToolUse hook
    go.mod               — Go module file
    prompt-gate.sh       — UserPromptSubmit hook (analyzes user message)
```

## How Decisions Work

The gate is deterministic — no semantic matching, no vector databases, no fuzzy logic.

- **Hard deny**: destructive git and commit/push are blocked unless the user's message explicitly contains the relevant instruction ("revert", "commit", "push")
- **Ask**: all file writes and edits prompt the user for approval before proceeding
- **Conversation-aware**: the gate reads the user's actual message to determine intent, not just the tool call parameters

The user is always in control. The gate enforces that Claude acts only when explicitly instructed.

## Customization

### Adding action signals

Edit the `action_signals` list and `imperative_starts` list in `prompt-gate.sh`.

### Changing the state file path

Update `STATE_FILE` in `prompt-gate.sh` and `stateFile` in `main.go`, then rebuild.

### Adding new rules

Add new check functions in `main.go` and rebuild with `go build`.
