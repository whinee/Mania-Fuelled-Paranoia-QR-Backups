# Settings
set windows-shell := ['pwsh.exe', '-CommandWithArgs']
set positional-arguments

# Constants
source_folder := 'snapid_backend'

# Choose recipes
default:
    @ just -lu; printf '%s ' press Enter to continue; read; just --choose

[private]
nio:
    @ uv run no_implicit_optional dev/scripts/py {{source_folder}}; exit 0

[private]
ruff:
    @ uv run ruff check dev/scripts/py {{source_folder}} --fix; exit 0

# Set up development environment
[unix]
bootstrap:
    #!/usr/bin/env bash
    rm -rf .venv
    rm -f uv.lock
    uv venv
    source .venv/bin/activate
    uv sync

# Set up development environment
[windows]
bootstrap:
    Remove-Item -Recurse -Force .venv
    Remove-Item -Force uv.lock
    uv venv
    . .\.venv\Scripts\Activate.ps1
    uv sync

# Set up development environment for syncing weblate notes
[unix]
bootstrap_sync_weblate_notes:
    #!/usr/bin/env bash
    rm -rf .venv
    rm -f uv.lock
    uv venv
    source .venv/bin/activate
    uv sync --no-default-groups --only-group sync_weblate_notes

# Lint codebase
lint:
    @ just nio
    @ uv run black -q dev/scripts/py {{source_folder}}
    @ just ruff

[unix]
gen_config_dev:
    @ python3 -m dev.scripts.py.gen_config --env dev --os linux generate

[windows]
gen_config_dev:
    @ python3 -m dev.scripts.py.gen_config --env dev --os win generate

start:
    just gen_config_dev
    yarn start

start_backend:
    just gen_config_dev
