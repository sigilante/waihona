#!/bin/sh
# Offline test: lockfile -> apply -> compile under BibTeX and biber. Needs xelatex, bibtex, biber.
set -e
D=$(mktemp -d); H=$(cd "$(dirname "$0")/.." && pwd); cd "$D"
cat > refs.bib <<'B'
@misc{A, author={A. B.}, title={T}, year={2026},
  url = {https://example.org/a}
}
B
printf '\\documentclass{article}\\usepackage{natbib,waihona}\\begin{document}\\href{https://example.org/a}{x}~\\citep{A}\\bibliographystyle{apalike-url-archive}\\bibliography{refs}\\end{document}\n' > m.tex
printf '{"https://example.org/a":{"id":"deadbeef","urldate":"2026-11-13","timestamp":"20261101000000","archive_url":"https://web.archive.org/web/20261101000000/https://example.org/a","how":"existing"}}' > waihona.lock.json
python3 "$H/waihona.py" apply --write
grep -q ahref m.tex && grep -q archiveurl refs.bib
export TEXINPUTS=".:$H/tex:" BSTINPUTS=".:$H/bst:"
xelatex -interaction=nonstopmode m >/dev/null; bibtex m >/dev/null; xelatex -interaction=nonstopmode m >/dev/null; xelatex -interaction=nonstopmode m >/dev/null
pdftotext m.pdf - | grep -q "archived 1 November 2026"
echo PASS
