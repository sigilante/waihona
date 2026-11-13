# waihona

Archive every URL a manuscript cites on archive.org and print the snapshot beside it.
Stdlib Python 3 plus a small LaTeX package; works with BibTeX and biber.
Process and agent instructions: [INSTRUCTIONS.md](INSTRUCTIONS.md). Quick start: `waihona.py --help`.

    tex/waihona.sty             \aurl, \ahref
    tex/waihona.dbx, waihona-biblatex.tex   biber route
    bst/apalike-url-archive.bst             BibTeX route (urlbst + archiveurl)
