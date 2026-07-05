# ytk memo — keybind and notification setup

## Karabiner keybind (Mac)

Add to `~/.config/karabiner/karabiner.json` under `profiles[0].complex_modifications.rules`
(this binds right_option+m; change `key_code`/`modifiers` to taste):

```json
{
  "description": "ytk memo popup",
  "manipulators": [
    {
      "type": "basic",
      "from": { "key_code": "m", "modifiers": { "mandatory": ["right_option"] } },
      "to": [
        {
          "shell_command": "/opt/homebrew/bin/tmux display-popup -E -w 60% -h 30% 'ytk memo'"
        }
      ]
    }
  ]
}
```

A floating popup drops over the active tmux client, records until Enter, routes,
and closes. Non-tmux fallback: replace the shell_command with
`open -na Ghostty --args -e ytk memo`.

## sketchybar item (the pretty channel)

`ytk memo` fires `sketchybar --trigger ytk_memo RESULT="..." ROUTE="..."` after
every routed memo. Add to `~/.config/sketchybar/sketchybarrc`:

```bash
sketchybar --add item ytk_memo right \
           --set ytk_memo drawing=off label.max_chars=48 script="$PLUGIN_DIR/ytk_memo.sh" \
           --add event ytk_memo \
           --subscribe ytk_memo ytk_memo
```

And in the item script (or inline), show for 5 seconds on trigger:

```bash
# ~/.config/sketchybar/plugins/ytk_memo.sh
sketchybar --set ytk_memo drawing=on label="$ROUTE: $RESULT"
sleep 5
sketchybar --set ytk_memo drawing=off
```

Style it with your theme's colors/fonts — that is the point.

## macOS notifications (terminal hidden)

When AeroSpace reports Ghostty is not on a visible workspace, ytk uses
`terminal-notifier` (`brew install terminal-notifier`). Without it installed,
the notification is skipped silently.

## iOS Shortcut (once hosting exists, #24)

Shortcut: Record Audio -> Get Contents of URL (POST, multipart, field `file`)
to `http://<tailscale-host>:8765/api/memo`. Until then the endpoint works on
the local network.
