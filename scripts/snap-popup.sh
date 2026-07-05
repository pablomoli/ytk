#!/bin/bash
# Keybind entry point for screenshot + spoken note. Clipboard image is saved
# instantly, the mic opens in ~0.2s, and python runs only in the background.

YTK="$HOME/.local/bin/ytk"
LOG="$HOME/.ytk/logs/memo.log"
TMPDIR_SNAP="$HOME/.ytk/audio/snaps"
STAMP="$(date +%Y%m%d-%H%M%S)"
IMG="$TMPDIR_SNAP/$STAMP.png"
WAV="$TMPDIR_SNAP/$STAMP.wav"
mkdir -p "$TMPDIR_SNAP" "$HOME/.ytk/logs"

mark() { echo "$(date '+%H:%M:%S.000') [sh]    +  0.00s SNAP_$1" >> "$LOG"; }

mark SH_START
if ! /opt/homebrew/bin/pngpaste "$IMG" 2>/dev/null || [ ! -s "$IMG" ]; then
  printf '\n \033[2mno image on the clipboard\033[0m'
  sleep 1.2
  exit 1
fi
mark IMAGE_SAVED

ffmpeg -hide_banner -loglevel error -y \
  -f avfoundation -i ":default" \
  -t 300 -ar 16000 -ac 1 "$WAV" </dev/null &
FFPID=$!
mark RECORDING
printf '\n \033[1;38;5;117m\xe2\x97\x8f snap\033[0m \033[2m\xc2\xb7 speak the note \xc2\xb7 enter saves \xc2\xb7 esc/q cancels\033[0m'
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
  rm -f "$WAV" "$IMG"
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
mark "RECORDED $STAMP.wav"

set -m
env -u TMUX nohup "$YTK" snap --file "$IMG" --note-audio "$WAV" <"/dev/null" >>"$HOME/.ytk/logs/worker.err" 2>&1 &
disown
mark BG_WORKER_SPAWNED
