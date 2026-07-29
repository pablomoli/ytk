#!/usr/bin/env bash
# Compile the garden modules and dump a real skeleton to JSON, so the plots
# measure what the renderer builds instead of a reimplementation.
#
#   scripts/dump_skeleton.sh [port] [bucket] [out.json]
#
# tsc emits extensionless relative imports, which node's ESM loader rejects, so
# the specifiers are rewritten in place. Output lands in web/.gdump (ignored).
set -euo pipefail
port="${1:-6970}"; bucket="${2:-epicmap}"; out="${3:-/tmp/skeleton-$bucket.json}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/web"
rm -rf .gdump
npx tsc src/lib/garden/*.ts --outDir .gdump --module es2022 --target es2022 \
  --moduleResolution bundler --skipLibCheck --declaration false
for f in $(/usr/bin/find .gdump -name '*.js'); do
  sed -i '' -E 's/(from "\.\.?\/[^"]*)"/\1.js"/g' "$f"
done
cp "$root/scripts/dump_skeleton.mjs" .gdump/dump.mjs
node .gdump/dump.mjs "$port" "$bucket" "$out"
