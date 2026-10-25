#!/usr/bin/env bash
# Run one RetroBake agent on one task, headless. Logs go to coordination/logs/.
# Usage: coordination/run_agent.sh <agent-name> "<instruction>"
# Run several at once (each with & at the end) for parallel work; then: wait
set -euo pipefail
cd "$(dirname "$0")/.."
AGENT="$1"; shift
TASK="$*"
[ -f ".claude/agents/${AGENT}.md" ] || { echo "No such agent: $AGENT"; ls .claude/agents; exit 1; }
mkdir -p coordination/logs
LOG="coordination/logs/$(date +%Y%m%d-%H%M%S)-${AGENT}.log"
echo "[$AGENT] started -> $LOG"
CLAUDE_CONFIG_DIR="${RETROBAKE_CLAUDE_CONFIG:-$HOME/.claude-work}" "$HOME/.local/bin/claude" -p --agent "$AGENT" \
  --permission-mode acceptEdits \
  --allowedTools "Bash,Read,Write,Edit,Grep,Glob,WebSearch,WebFetch" \
  -w "agent-${AGENT}-$(date +%H%M%S)" \
  "$TASK
When finished: update the agent board (set-state, decide, contract, note) and commit your changes on a branch named agent/${AGENT}." \
  < /dev/null > "$LOG" 2>&1 && echo "[$AGENT] done" || echo "[$AGENT] FAILED - see $LOG"
