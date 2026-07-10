#!/usr/bin/env bash
set -euo pipefail
pnpm exec openapi-typescript http://127.0.0.1:6969/openapi.json -o src/api/schema.ts
