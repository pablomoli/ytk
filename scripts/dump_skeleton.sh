#!/usr/bin/env bash
# Compile the garden modules and dump a real skeleton to JSON, so the plots
# measure what the renderer builds instead of a reimplementation.
#
#   scripts/dump_skeleton.sh [port] [bucket] [out.json] [git-ref]
#
# With a git-ref the garden sources come from that commit rather than the
# working tree, which is how a before/after baseline is produced without
# checking anything out.
#
# --ignoreConfig is required: tsc 6 errors rather than ignoring tsconfig.json
# when files are named on the command line. tsc also emits extensionless
# relative imports, which node's ESM loader rejects, so specifiers are
# rewritten in place. Output lands in web/.gdump (ignored).
set -euo pipefail
port="${1:-6970}"; bucket="${2:-epicmap}"; out="${3:-/tmp/skeleton-$bucket.json}"; ref="${4:-}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/web"
rm -rf .gdump .gdump-src

if [ -n "$ref" ]; then
  mkdir -p .gdump-src
  for f in $(git -C "$root" ls-tree --name-only "$ref" web/src/lib/garden/); do
    # scene.ts reaches outside the garden directory and the dump never calls it.
    case "$f" in
      *.test.ts | */scene.ts) continue ;;
      *.ts) git -C "$root" show "$ref:$f" > ".gdump-src/$(basename "$f")" ;;
    esac
  done
  src=".gdump-src"
else
  src="src/lib/garden"
fi

# shellcheck disable=SC2086
npx tsc $src/*.ts --outDir .gdump --module es2022 --target es2022 \
  --moduleResolution bundler --skipLibCheck --declaration false --ignoreConfig

for f in $(/usr/bin/find .gdump -name '*.js'); do
  sed -i '' -E 's/(from "\.\.?\/[^"]*)"/\1.js"/g' "$f"
done

# The ref path flattens the tree; the working-tree path nests under src/lib.
if [ -n "$ref" ]; then
  mkdir -p .gdump/garden
  for f in .gdump/*.js; do
    [ -e "$f" ] && mv "$f" .gdump/garden/
  done
fi

cp "$root/scripts/dump_skeleton.mjs" .gdump/dump.mjs
node .gdump/dump.mjs "$port" "$bucket" "$out"
