#!/bin/bash
# UserPromptSubmit hook — reads Commander's message, writes flags to state file
INPUT=$(cat)
STATE_FILE="C:/gate/gate-state.json"

PROMPT=$(echo "$INPUT" | python -c "
import sys, json, re, os

STATE_FILE = 'C:/gate/gate-state.json'

d = json.load(sys.stdin)
prompt = d.get('prompt', '')

# Read previous state to preserve halt_latch and drift_block_count across messages
previous_halt = False
previous_block_count = 0
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, 'r') as f:
            previous_state = json.load(f)
            previous_halt = previous_state.get('halt_latch', False)
            previous_block_count = previous_state.get('drift_block_count', 0)
    except:
        pass

# Tokenize (whole-word tokens, case-insensitive)
tokens = set(re.findall(r'\b\w+\b', prompt.lower()))

# --- Trigger and halt detection ---
# 'hao' = proceed, 'tingzhi' = halt, 'kaisuo' = testing override.
has_trigger = 'hao' in tokens
has_halt = 'tingzhi' in tokens
has_kaisuo = 'kaisuo' in tokens

# Halt latch resolution — tingzhi wins over hao
if has_halt:
    halt_latch = True
elif has_trigger:
    halt_latch = False
else:
    halt_latch = previous_halt

# Kaisuo override — testing-only escape hatch, resets drift block count
if has_kaisuo:
    previous_block_count = 0

state = {
    'prompt': prompt,
    'has_trigger': has_trigger,
    'halt_latch': halt_latch,
    'drift_block_count': previous_block_count
}

print(json.dumps(state))
" 2>/dev/null)

if [ -n "$PROMPT" ]; then
    echo "$PROMPT" > "$STATE_FILE"
fi

# Run drift analyzer to merge drift fields into gate-state.json
python "C:/gate/drift-analyzer.py" 2>/dev/null

echo "{}"
