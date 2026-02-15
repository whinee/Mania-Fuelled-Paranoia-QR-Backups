#!/bin/bash

# Set this to the root directory you wanna start from
ROOT_DIR="fonts"

# You need ttf2tfm and maybe ttf2pk installed
# If not: sudo dnf install texlive-utils

find "$ROOT_DIR" -type f -name "*.ttf" | while read -r ttf; do
    base="${ttf%.ttf}"
    tfm="${base}.tfm"

    if [[ -f "$tfm" ]]; then
        echo "✅ Skipping: $ttf (already done)"
        continue
    fi

    echo "⚙️ Converting: $ttf"
    ttf2tfm "$ttf" -q -w -T T1-WGL4.enc

    if [[ -f "$tfm" ]]; then
        echo "✅ Done: $base"
    else
        echo "❌ Failed or partial: $base"
    fi
done