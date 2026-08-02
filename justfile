set shell := ["zsh", "-cu"]

repo := justfile_directory()

# List available recipes.
default:
    @just --list

# Install Python development dependencies and frontend packages.
setup:
    cd "{{ repo }}" && uv sync --extra dev
    cd "{{ repo }}/web" && vp install

# Run every supported quality gate.
check:
    "{{ repo }}/scripts/check-quality"

# Run complete Python and frontend lint checks.
lint:
    cd "{{ repo }}" && uv run --extra dev ruff check ytk scripts tests experiments labs
    cd "{{ repo }}/web" && vp lint

# Format supported Python and frontend source.
format:
    cd "{{ repo }}" && uv run --extra dev ruff format ytk scripts tests experiments labs
    cd "{{ repo }}/web" && vp fmt

# Run backend and frontend type checks.
typecheck:
    cd "{{ repo }}" && uv run --extra dev pyright
    cd "{{ repo }}/web" && vp exec tsc -b

# Run the fast Python and Chromium frontend suites.
test: test-python test-web

# Run the fast Python suite.
test-python:
    cd "{{ repo }}" && uv run --extra dev pytest

# Run the Chromium frontend suite.
test-web:
    cd "{{ repo }}/web" && vp exec vitest run

# Build the local frontend bundle (the wheel builds its own via hatch_build.py).
build-web:
    cd "{{ repo }}/web" && vp build

# Run the live retrieval evaluation.
eval:
    cd "{{ repo }}" && uv run ytk eval

# Run the hub in the foreground. Optional port frees :6969 for the live hub
# when testing a branch checkout: `just ui 8877`.
ui port="":
    cd "{{ repo }}" && uv run ytk ui {{ if port == "" { "" } else { "--port " + port } }}

# Restart the installed hub service.
ui-restart:
    ytk ui restart

# Show Chroma service and collection status.
chroma-status:
    ytk chroma status

# Reinstall the ytk tool from this checkout.
install-tool:
    cd "{{ repo }}" && uv tool install --reinstall .
