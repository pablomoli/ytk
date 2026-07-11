#!/usr/bin/env bash
set -euo pipefail
# Run from the web/ project root regardless of the caller's cwd, so the
# pnpm workspace resolves and the output path is correct.
cd "$(dirname "$0")/../.."
pnpm exec openapi-typescript http://127.0.0.1:6969/openapi.json -o src/api/schema.ts
