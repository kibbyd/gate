package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
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
	Prompt    string `json:"prompt"`
	IsQuestion bool  `json:"is_question"`
	SaidStop   bool  `json:"said_stop"`
	HasAction  bool  `json:"has_action"`
	HasGo      bool  `json:"has_go"`
}

const stateFile = "C:/gate/gate-state.json"

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

	// --- Rule 3: STOP means freeze — block everything ---
	if state.SaidStop {
		deny("Rule 3: STOP — all actions frozen")
		return
	}

	// --- Rule 1: Questions require words only — block all tools ---
	if state.IsQuestion && !state.HasAction {
		deny("Rule 1: question detected — respond with words only")
		return
	}

	// --- Rule 12: Write/Edit — only with explicit "go" signal ---
	if input.ToolName == "Write" || input.ToolName == "Edit" {
		if !state.HasGo {
			deny("Rule 12: Edit/Write blocked — Commander did not say go")
			return
		}
	}

	// --- Rule 2: No action without explicit action signal ---
	if !state.HasAction {
		deny("Rule 2: no action signal detected — wait for explicit instruction")
		return
	}

	// --- Bash-specific checks ---
	if input.ToolName == "Bash" {
		cmd := strings.ToLower(input.ToolInput["command"])
		prompt := strings.ToLower(state.Prompt)

		// Rule 5: Destructive git — only if Commander said "revert"
		destructive := []string{
			"git checkout .",
			"git checkout --",
			"git reset --hard",
			"git clean",
			"git branch -d",
			"git branch -D",
			"git push --force",
			"git push -f",
			"git restore .",
		}
		for _, d := range destructive {
			if strings.Contains(cmd, strings.ToLower(d)) {
				if !strings.Contains(prompt, "revert") {
					deny(fmt.Sprintf("Rule 5: destructive git blocked — Commander did not say revert: %s", d))
					return
				}
			}
		}

		// Rule 6: Commit and push — only if Commander instructed it
		if strings.Contains(cmd, "git commit") {
			if !strings.Contains(prompt, "commit") {
				deny("Rule 6: git commit blocked — Commander did not instruct commit")
				return
			}
		}
		if strings.Contains(cmd, "git push") {
			if !strings.Contains(prompt, "push") {
				deny("Rule 6: git push blocked — Commander did not instruct push")
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

func deny(reason string) {
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
