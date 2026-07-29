#!/bin/bash
# Keybind entry point for voice memos. Native osascript dialog — no terminal,
# no tmux client required, so the keybind works with every app frontmost.
# Mic opens before the dialog draws; python (ytk memo --from-audio) only ever
# runs detached in the background. State marks go to the same log as StageLog.

YTK="$HOME/.local/bin/ytk"
LOG="$HOME/.ytk/logs/memo.log"
OUT="$HOME/.ytk/audio/memos/$(date +%Y%m%d-%H%M%S).wav"
mkdir -p "$HOME/.ytk/audio/memos" "$HOME/.ytk/logs"

mark() { echo "$(date '+%H:%M:%S.000') [sh]    +  0.00s $1" >> "$LOG"; }

mark SH_START
ffmpeg -hide_banner -loglevel error -y \
  -f avfoundation -i ":default" \
  -t 300 -ar 16000 -ac 1 "$OUT" </dev/null &
FFPID=$!
mark RECORDING

# No "tell System Events": that sends Apple Events, which Karabiner's server
# has no Automation permission for (fails -1743 before the dialog draws).
# Plain display dialog renders from osascript's own process, permission-free.
# "giving up" after 300s matches ffmpeg's -t cap; a timeout saves, and only a
# real user Cancel discards — any other dialog failure keeps the audio.
OSAERR=$(osascript -e 'display dialog "recording — Save when done" with title "memo" buttons {"Cancel", "Save"} default button "Save" with icon note giving up after 300' 2>&1 >/dev/null)
OSARC=$?
if [ $OSARC -ne 0 ] && echo "$OSAERR" | grep -q "User canceled"; then
  kill -9 "$FFPID" 2>/dev/null
  wait "$FFPID" 2>/dev/null
  rm -f "$OUT"
  mark CANCELLED
  exit 0
fi
[ $OSARC -ne 0 ] && mark "DIALOG_FAILED rc=$OSARC ${OSAERR//$'\n'/ }"
kill -INT "$FFPID" 2>/dev/null
( sleep 3; kill -9 "$FFPID" 2>/dev/null ) &
WATCHDOG=$!
wait "$FFPID" 2>/dev/null
kill "$WATCHDOG" 2>/dev/null
wait "$WATCHDOG" 2>/dev/null
mark "RECORDED $(basename "$OUT")"

if [ ! -s "$OUT" ]; then
  mark CAPTURE_FAILED
  osascript -e 'display notification "no audio written — check mic permission for Karabiner" with title "memo"' 2>/dev/null
  exit 1
fi

set -m
env -u TMUX nohup "$YTK" memo --from-audio "$OUT" <"/dev/null" >>"$HOME/.ytk/logs/worker.err" 2>&1 &
disown
mark BG_WORKER_SPAWNED
