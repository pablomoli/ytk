# [plan-01] Todo / Calendar / Reminders — a time-based task subsystem for ytk

## Defect

ytk captures knowledge but has no notion of *time-bound personal tasks*. The user
repeatedly wants to track recurring, deadline-driven items (immigration paperwork,
laundry, chores) and be reminded of them. Eleven separate issues were filed for the
same feature; this is the single canonical home.

## Children

- #43 — calendar-aware todo system (master)
- #44 — daily todo list + calendar integration
- #50 — todo/calendar integration
- #52 — todo/calendar feature
- #53 — calendar and todo integration
- #56 — todo list with calendar and reminders
- #57 — todo list feature with calendar integration
- #58 — todo list feature with calendar integration
- #61 — daily todo list with calendar integration
- #62 — todo/calendar feature with Apple Reminders sync
- #65 — daily todo list feature

## Requirements (union of all children)

- A daily todo list surfaced in ytk (CLI + hub).
- Time-based / recurring reminders (e.g. "laundry weekly", "immigration deadline").
- Two-way sync with **Apple Reminders** (EventKit via a Swift/AppleScript bridge or
  `pyobjc`), and read access to Calendar for deadline context.
- Optional: link a task to a source note (e.g. an IoT/hardware project video) so a
  task can carry contextual learning material.

## Fix sequence

1. Data model: a `Task` type (title, due, recurrence, source-note link, done) and a
   store (start with a JSON/SQLite file under `~/.ytk/`, mirror into the vault as a
   daily note section for Obsidian visibility).
2. `ytk todo` CLI: add / list / done / defer, with natural-date parsing.
3. Apple Reminders bridge: one-way push first (ytk -> Reminders), then reconcile
   completions back. Isolate the macOS-specific code behind an interface so the core
   stays testable.
4. Calendar read: surface today's events alongside todos for a unified "today" view.
5. Hub surface (deferred — see UI track): a `/today` page. Not in scope until the UI
   pass is scheduled.

## Out of scope

- Hub UI styling for the todo view — belongs with the UI/UX track.
- Non-macOS reminder backends.

## Open questions (for remote review)

- Reminders sync: EventKit via pyobjc vs a tiny compiled Swift helper vs AppleScript?
- Is the vault the source of truth for tasks, or Apple Reminders? (Decides sync
  direction and conflict resolution.)
