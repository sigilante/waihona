# Archive-link citation styles

Decided 2026-11-13: **option 1**, with dates always written `13 November 2026`.
The others are recorded in case a venue or a print edition needs them. Same entry rendered each way:

1. **One parenthetical, same inline and in the bibliography (current).**
   `URL: https://algassert.com/post/2602 (accessed 13 November 2026; archived 18 October 2026).`
   "archived 18 October 2026" is the link. Implemented in `waihona.sty`, `bst/apalike-url-archive.bst`, `tex/waihona-biblatex.tex`.
2. **ISO dates, compact.** `… (accessed 2026-11-13; archived 2026-10-18)`. Shorter, more technical; suits a paper, not a trade book. Contradicts the house date standard, so not for general use.
3. **Say where, not when.** `… (accessed 13 November 2026; Wayback Machine)`, with "Wayback Machine" as the link. Least clutter; show the snapshot date only for stale snapshots.
4. **Print the full snapshot URL.** `Available at <url> (accessed 13 November 2026). Archived at https://web.archive.org/web/20261018…/<url>.`
   The only form that works for a reader holding paper; long, and doubles every URL.
5. **Appendix of archived sources.** The bibliography keeps URL and access date plus a pointer (`[A12]`); a back-of-book table maps A12 to the full snapshot URL.
   Clean body, works in print, more machinery. Pairs well with option 1 for a print edition (ZKP, Network Press).

Open question for print: if the book ships on paper, consider option 1 plus option 5.
