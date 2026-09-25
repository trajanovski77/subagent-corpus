#!/bin/bash
# Build main_v2.pdf (the v2 manuscript; main.tex is the superseded v1) with Springer's svjour3 class (svjour3.cls, svglov3.clo, spbasic.bst ship in this folder).
# Usage: ./build.sh
# Overleaf: upload this folder as-is, set main_v2.tex as the main document, compiler pdfLaTeX.
cd "$(dirname "$0")"
if command -v latexmk >/dev/null 2>&1; then
  latexmk -pdf -bibtex -interaction=nonstopmode main_v2.tex 2>&1 | tail -20
elif command -v pdflatex >/dev/null 2>&1; then
  pdflatex -interaction=nonstopmode main_v2.tex >/dev/null && bibtex main_v2 >/dev/null && \
  pdflatex -interaction=nonstopmode main_v2.tex >/dev/null && pdflatex -interaction=nonstopmode main_v2.tex | tail -20
elif command -v tectonic >/dev/null 2>&1; then
  tectonic -X compile main_v2.tex --keep-logs --synctex 2>&1 | tail -20
else
  echo "No LaTeX engine found. Install TeX Live (pdflatex) or tectonic (brew install tectonic), or upload to Overleaf."; exit 1
fi
[ -f main_v2.pdf ] && echo "OK  main_v2.pdf  $(du -h main_v2.pdf | cut -f1)"
