#!/bin/bash
# Keybind entry point for voice memos. Pure shell so the mic opens in ~0.2s;
# python (ytk memo --from-audio) only ever runs detached in the background.
# State marks go to the same log as ytk's StageLog.

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
printf '\n \033[1;38;5;203m\xe2\x97\x8f rec\033[0m \033[2m\xc2\xb7 enter saves \xc2\xb7 esc/q cancels\033[0m'
CANCEL=0
while :; do
  IFS= read -rsn1 key
  case "$key" in
    ""|$'\n') break ;;
    q|$'\e') CANCEL=1; break ;;
  esac
done
if [ "$CANCEL" = 1 ]; then
  kill -9 "$FFPID" 2>/dev/null
  wait "$FFPID" 2>/dev/null
  rm -f "$OUT"
  mark CANCELLED
  printf '\r \033[2m\xe2\x9c\x95 cancelled\033[0m                          '
  sleep 0.4
  exit 0
fi
kill -INT "$FFPID" 2>/dev/null
( sleep 3; kill -9 "$FFPID" 2>/dev/null ) &
WATCHDOG=$!
wait "$FFPID" 2>/dev/null
kill "$WATCHDOG" 2>/dev/null
wait "$WATCHDOG" 2>/dev/null
mark "RECORDED $(basename "$OUT")"

if [ ! -s "$OUT" ]; then
  echo "capture failed - no audio written. check mic permission."
  echo "[press Enter to close]"
  read -r _
  exit 1
fi

env -u TMUX nohup "$YTK" memo --from-audio "$OUT" >>$HOME/.ytk/logs/worker.err 2>&1 &
mark BG_WORKER_SPAWNED
