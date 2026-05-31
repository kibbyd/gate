package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"time"
)

// HookInput matches the JSON Claude Code sends to PreToolUse hooks.
type HookInput struct {
	ToolName  string            `json:"tool_name"`
	ToolInput map[string]string `json:"tool_input"`
}

// HookOutput is the JSON response the hook returns.
type HookOutput struct {
	HookSpecificOutput *HookDecision `json:"hookSpecificOutput,omitempty"`
}

type HookDecision struct {
	HookEventName            string `json:"hookEventName"`
	PermissionDecision       string `json:"permissionDecision"`
	PermissionDecisionReason string `json:"permissionDecisionReason"`
}

// GateState is written by the UserPromptSubmit hook.
type GateState struct {
	Prompt          string `json:"prompt"`
	HasTrigger      bool   `json:"has_trigger"`
	HaltLatch       bool   `json:"halt_latch"`
	DriftHalt       bool   `json:"drift_halt"`
	DriftScore      int    `json:"drift_score"`
	DriftBlockCount int    `json:"drift_block_count"`
}

const stateFile = "C:/gate/gate-state.json"
const incidentLog = "C:/gate/drift-incidents.log"
const driftBlockThreshold = 2

// gitWordRegex matches 'git' as a whole word anywhere in a command.
// Catches 'git status', 'cd foo && git push', '; git log', etc.
// Does NOT match 'github', 'digital', 'mygit'.
var gitWordRegex = regexp.MustCompile(`\bgit\b`)

func main() {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		allow()
		return
	}

	var input HookInput
	if err := json.Unmarshal(raw, &input); err != nil {
		allow()
		return
	}

	// Read-only tools always pass
	switch input.ToolName {
	case "Read", "Glob", "Grep", "ToolSearch", "Agent":
		allow()
		return
	}

	// Load state from UserPromptSubmit hook
	state := loadState()

	// --- Rule 2: Drift detected — either gate block count or analyzer phrase score ---
	// Checked before other rules so drift halt fires regardless of hao presence.
	// Uses writeDeny to avoid incrementing the counter for its own firing.
	if state.DriftBlockCount >= driftBlockThreshold || state.DriftHalt {
		reason := fmt.Sprintf("Rule 2: drift detected (blocks=%d) — rotate to a new instance", state.DriftBlockCount)
		if state.DriftHalt {
			reason = fmt.Sprintf("Rule 2: drift detected (blocks=%d, analyzer score=%d) — rotate to a new instance", state.DriftBlockCount, state.DriftScore)
		}
		logIncident(reason, input, state)
		writeDeny(reason)
		return
	}

	// --- Rule 1: Halt latch — blocks everything until cleared with hao ---
	if state.HaltLatch {
		logIncident("Rule 1: halt latch active", input, state)
		deny("Rule 1: halt latch active — say hao to unlock")
		return
	}

	// --- Rule 3: No hao — only read-only tools allowed ---
	if !state.HasTrigger {
		logIncident("Rule 3: no hao", input, state)
		deny("Rule 3: no hao in your message — only read-only tools allowed")
		return
	}

	// --- Rule 4: Git commands require "git" in the message (hao already verified by Rule 3) ---
	if input.ToolName == "Bash" {
		cmd := strings.TrimSpace(strings.ToLower(input.ToolInput["command"]))
		prompt := strings.ToLower(state.Prompt)

		if gitWordRegex.MatchString(cmd) {
			if !strings.Contains(prompt, "git") {
				logIncident("Rule 4: git without 'git' in message", input, state)
				deny("Rule 4: git command blocked — requires 'git' in your message")
				return
			}
		}
	}

	allow()
}

func loadState() GateState {
	data, err := os.ReadFile(stateFile)
	if err != nil {
		return GateState{}
	}
	var state GateState
	if err := json.Unmarshal(data, &state); err != nil {
		return GateState{}
	}
	return state
}

func allow() {
	fmt.Println("{}")
}

// deny increments the drift block count and writes a deny response.
// Used by rules that represent real failures (Rules 1, 3, 4).
func deny(reason string) {
	// Increment drift block count in gate-state.json
	state := loadState()
	state.DriftBlockCount++
	if data, err := json.Marshal(state); err == nil {
		_ = os.WriteFile(stateFile, data, 0644)
	}
	writeDeny(reason)
}

// writeDeny writes a deny response without incrementing the drift count.
// Used by Rule 2, which fires because of the count itself.
func writeDeny(reason string) {
	output := HookOutput{
		HookSpecificOutput: &HookDecision{
			HookEventName:            "PreToolUse",
			PermissionDecision:       "deny",
			PermissionDecisionReason: fmt.Sprintf("GATE BLOCKED — %s", reason),
		},
	}
	data, _ := json.Marshal(output)
	fmt.Println(string(data))
}

// logIncident appends a deny event to the drift incident log.
// Survives instance rotation so Commander or the next instance can review.
func logIncident(rule string, input HookInput, state GateState) {
	toolSummary := input.ToolName
	if input.ToolName == "Bash" {
		cmd := input.ToolInput["command"]
		if len(cmd) > 200 {
			cmd = cmd[:200]
		}
		toolSummary = fmt.Sprintf("Bash: %s", cmd)
	} else if input.ToolName == "Write" || input.ToolName == "Edit" {
		path := input.ToolInput["file_path"]
		toolSummary = fmt.Sprintf("%s: %s", input.ToolName, path)
	}
	prompt := state.Prompt
	if len(prompt) > 200 {
		prompt = prompt[:200]
	}
	entry := fmt.Sprintf("[%s] %s | %s | blocks=%d | prompt: %s\n",
		time.Now().Format("2006-01-02 15:04:05"),
		rule,
		toolSummary,
		state.DriftBlockCount,
		prompt,
	)
	f, err := os.OpenFile(incidentLog, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		f.WriteString(entry)
	}
}

func ask(reason string) {
	output := HookOutput{
		HookSpecificOutput: &HookDecision{
			HookEventName:            "PreToolUse",
			PermissionDecision:       "ask",
			PermissionDecisionReason: reason,
		},
	}
	data, _ := json.Marshal(output)
	fmt.Println(string(data))
}
