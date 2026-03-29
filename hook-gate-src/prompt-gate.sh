#!/bin/bash
# UserPromptSubmit hook — reads Commander's message, writes flags to state file
INPUT=$(cat)
STATE_FILE="C:/gate/gate-state.json"

PROMPT=$(echo "$INPUT" | python -c "
import sys, json

d = json.load(sys.stdin)
prompt = d.get('prompt', '')

# Detect question
is_question = '?' in prompt

# Detect STOP
said_stop = 'STOP' in prompt.upper().split()

# Detect action signals
lower = prompt.lower()
action_signals = ['go on', 'go ahead', 'do it', 'proceed', 'fix it', 'fix this',
                  'build it', 'build this', 'write it', 'write this', 'update it',
                  'update this', 'remove', 'add ', 'delete', 'change ', 'edit ',
                  'create ', 'make ', 'run ', 'commit', 'push', 'test it',
                  'go on then', 'yes', 'do that', 'try it', 'now',
                  'can you write', 'can you update', 'can you fix', 'can you create',
                  'can you edit', 'can you remove', 'can you add', 'can you make',
                  'please', 'go', 'write a ', 'write to ']

has_action = any(sig in lower for sig in action_signals)

# Direct imperatives — starts with a verb
imperative_starts = ['remove', 'add', 'delete', 'change', 'edit', 'create', 'make',
                     'run', 'fix', 'update', 'write', 'build', 'commit', 'push',
                     'show', 'read', 'get', 'put', 'set', 'move', 'copy', 'rename',
                     'install', 'test', 'check', 'verify', 'confirm', 'try',
                     'familiarize', 'look', 'review', 'compare', 'search', 'find']
first_word = lower.strip().split()[0] if lower.strip() else ''
if first_word in imperative_starts:
    has_action = True

# Detect "go" signal — tight gate for Edit/Write
go_signals = ['go', 'go on', 'go ahead', 'do it', 'proceed']
words = lower.strip().split()
has_go = lower.strip() in go_signals or any(sig in lower for sig in go_signals)

state = {
    'prompt': prompt,
    'is_question': is_question,
    'said_stop': said_stop,
    'has_action': has_action,
    'has_go': has_go
}

print(json.dumps(state))
" 2>/dev/null)

if [ -n "$PROMPT" ]; then
    echo "$PROMPT" > "$STATE_FILE"
fi

echo "{}"
