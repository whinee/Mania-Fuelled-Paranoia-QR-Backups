#!/usr/bin/env bash
set -e

TEXFILE="$1"

# Render Mermaid diagrams only if needed
# for f in mermaid-diagrams/*.mmd; do
#   out="figures/$(basename "$f" .mmd).pdf"
#   if [[ ! -f "$out" || "$f" -nt "$out" ]]; then
#     echo "Rendering $f -> $out"
#     mmdc -i "$f" -o "$out"
#   else
#     echo "Skipping $f (already up-to-date)"
#   fi
# done

# Run LaTeX build
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
echo "SHIT"
latexmk -xelatex -synctex=1 -interaction=nonstopmode -file-line-error "$TEXFILE"
