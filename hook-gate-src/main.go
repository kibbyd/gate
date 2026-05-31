package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"
)

// HookInput matches the JSON Claude Code sends to PreToolUse hooks.
type HookInput struct {
	ToolName  string            `json:"tool_name"`
	ToolInput map[string]interface{} `json:"tool_input"`
	Cwd       string            `json:"cwd"`
}

// Authorization is one entry of the frozen task-list grammar.
type Authorization struct {
	Action       string `json:"action"`
	ResourceType string `json:"resource_type"`
	Resource     string `json:"resource"`
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
	HasQuestion     bool   `json:"has_question"`
	HaltLatch       bool   `json:"halt_latch"`
	DriftHalt       bool   `json:"drift_halt"`
	DriftScore      int    `json:"drift_score"`
	DriftBlockCount int    `json:"drift_block_count"`
	Mode            int    `json:"mode"`
	GateOff         bool   `json:"gate_off"`
	HasTaskList     bool   `json:"has_tasklist"`
	Authorizations  []Authorization `json:"authorizations"`
	GateStrictRoots []string `json:"gate_strict_roots"`
}

const stateFile = "C:/gate/gate-state.json"
const incidentLog = "C:/gate/drift-incidents.log"
const driftBlockThreshold = 2

// gitWordRegex matches 'git' as a whole word anywhere in a command.
// Catches 'git status', 'cd foo && git push', '; git log', etc.
// Does NOT match 'github', 'digital', 'mygit'.
var gitWordRegex = regexp.MustCompile(`\bgit\b`)

// canon normalizes a path: Clean, resolve symlinks if possible, and case-fold
// on Windows (where the filesystem is case-insensitive).
// resolveExisting resolves symlinks on the longest existing ancestor and
// re-appends the non-existing tail, so not-yet-created files normalize the
// same way their parent directory does.
func resolveExisting(p string) string {
	if r, err := filepath.EvalSymlinks(p); err == nil {
		return r
	}
	dir := filepath.Dir(p)
	if dir == p {
		return p
	}
	return filepath.Join(resolveExisting(dir), filepath.Base(p))
}

func canon(p string) string {
	if p == "" {
		return ""
	}
	c := resolveExisting(filepath.Clean(p))
	if runtime.GOOS == "windows" {
		c = strings.ToLower(c)
	}
	return c
}

// canonAbs resolves a (possibly relative) path against root, then canonicalizes.
func canonAbs(p, root string) string {
	if p == "" {
		return ""
	}
	if !filepath.IsAbs(p) {
		p = filepath.Join(root, p)
	}
	return canon(p)
}

// normalizeCmd collapses whitespace so command_exact compares on content.
func normalizeCmd(s string) string {
	return strings.Join(strings.Fields(s), " ")
}

// strictApplies reports whether cwd sits inside any configured strict root.
func strictApplies(cwd string, roots []string) bool {
	if cwd == "" || len(roots) == 0 {
		return false
	}
	c := canon(cwd)
	for _, r := range roots {
		cr := canon(r)
		if cr == "" {
			continue
		}
		if c == cr || strings.HasPrefix(c, cr+string(filepath.Separator)) {
			return true
		}
	}
	return false
}

// authorized reports whether a Write/Edit/Bash call matches a frozen grant.
// Default deny: no grant, no execution.
func authorized(input HookInput, auths []Authorization, root string) bool {
	switch input.ToolName {
	case "Write", "Edit":
		target := canonAbs(toolStr(input.ToolInput, "file_path"), root)
		if target == "" {
			return false
		}
		for _, a := range auths {
			if a.Action != input.ToolName {
				continue
			}
			res := canonAbs(a.Resource, root)
			if res == "" {
				continue
			}
			if a.ResourceType == "file_exact" && target == res {
				return true
			}
			if a.ResourceType == "dir_recursive" {
				if target == res || strings.HasPrefix(target, res+string(filepath.Separator)) {
					return true
				}
			}
		}
		return false
	case "Bash":
		cmd := normalizeCmd(toolStr(input.ToolInput, "command"))
		for _, a := range auths {
			if a.Action == "Bash" && a.ResourceType == "command_exact" && normalizeCmd(a.Resource) == cmd {
				return true
			}
		}
		return false
	}
	return false
}

func main() {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		writeDeny("gate error — fail-safe deny (stdin read failed)")
		return
	}

	var input HookInput
	if err := json.Unmarshal(raw, &input); err != nil {
		writeDeny("gate error — fail-safe deny (JSON parse failed)")
		return
	}

	// Agent must use subagent_type: LISTEN
	if input.ToolName == "Agent" || input.ToolName == "Task" {
		if toolStr(input.ToolInput, "subagent_type") != "LISTEN" {
			writeDeny("AGENT RULE — must use subagent_type: LISTEN")
			return
		}
	}

	// Load state early — needed for redirect check before read-only bypass
	state := loadState()

	// Read-only tools always pass
	switch input.ToolName {
	case "Read", "Glob", "Grep", "ToolSearch", "Agent":
		allow()
		return
	}

	// --- Rule 0: Question mark — answer only, no actions ---
	if state.HasQuestion {
		logIncident("Rule 0: question mark detected", input, state)
		writeDeny("ANSWER THE QUESTION!!!!")
		return
	}

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
		deny("Rule 1: halt latch active — say hao to unlock", state)
		return
	}

	// --- Rule 3: hao + task list required — only read-only tools allowed otherwise ---
	// gate_off ("hao de") is a full override and bypasses both checks.
	if !state.GateOff {
		if !state.HasTrigger {
			logIncident("Rule 3: no hao", input, state)
			deny("Rule 3: no hao in your message — only read-only tools allowed", state)
			return
		}
		if !state.HasTaskList {
			logIncident("Rule 3: hao with no task list", input, state)
			deny("Rule 3: hao with no task list — produce a task list first", state)
			return
		}
	}

	// --- Rule 4: Git commands require "git" in the message (hao already verified by Rule 3) ---
	if input.ToolName == "Bash" {
		cmd := strings.TrimSpace(strings.ToLower(toolStr(input.ToolInput, "command")))
		prompt := strings.ToLower(state.Prompt)

		if gitWordRegex.MatchString(cmd) {
			if !strings.Contains(prompt, "git") {
				logIncident("Rule 4: git without 'git' in message", input, state)
				deny("Rule 4: git command blocked — requires 'git' in your message", state)
				return
			}
		}
	}

	// --- Rule 5: authorization grammar — strict roots only; gate_off overrides ---
	// In a strict root, Write/Edit/Bash must match a frozen task-list grant.
	// Outside strict roots, behaviour is unchanged (Rules 1–4 already passed).
	if !state.GateOff && strictApplies(input.Cwd, state.GateStrictRoots) {
		switch input.ToolName {
		case "Write", "Edit", "Bash":
			if !authorized(input, state.Authorizations, input.Cwd) {
				logIncident("Rule 5: action not in frozen authorization grammar", input, state)
				deny("Rule 5: not authorized by frozen task-list grammar — add an authorization entry", state)
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

func toolStr(m map[string]interface{}, key string) string {
	v, ok := m[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return fmt.Sprintf("%v", v)
	}
	return s
}

func allow() {
	fmt.Println("{}")
}

// deny increments the drift block count and writes a deny response.
// Used by rules that represent real failures (Rules 1, 3, 4).
// Accepts the already-loaded state to avoid a stale re-read.
func deny(reason string, state GateState) {
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
		cmd := toolStr(input.ToolInput, "command")
		if len(cmd) > 200 {
			cmd = cmd[:200]
		}
		toolSummary = fmt.Sprintf("Bash: %s", cmd)
	} else if input.ToolName == "Write" || input.ToolName == "Edit" {
		path := toolStr(input.ToolInput, "file_path")
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

