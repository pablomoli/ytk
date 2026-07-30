# Provenance note — history rewrite, 2026-07-30

The commit SHAs stamped in this directory's figure footers (and quoted in
the #149/#150 issue comments) predate a `git filter-repo` rewrite on
2026-07-30, which removed `.claude/settings.json` — local hook config that
had been tracked since before the `.gitignore` rule existed — from all
history and force-pushed master.

Every pre-rewrite SHA therefore no longer resolves. The figures themselves
are unchanged and remain the artifacts of record; to locate a figure's
source commit, match its commit *message* (unchanged by the rewrite) in
`git log` rather than the stamped hash. Figures rendered after this date
stamp post-rewrite SHAs and resolve normally.
