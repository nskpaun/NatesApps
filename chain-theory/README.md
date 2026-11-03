# Chain Theory Explorer (offline)

`chain-theory.html` is one self-contained offline app (about 12 MB) for exploring Alex Wissner-Gross's Chain Theory (October 2026):

- **Levels 1–4:** a 60-second summary, the big picture, the math of the α count, and a Part-by-Part map of the 754-page compendium.
- **Play:** three quiz decks, glossary flashcards, and a "chain" of 12 progress links.
- **α calculator:** change the counts and weights and watch 1/α move.
- **Library:** the full searchable text of the talk, the alpha Letter, and the compendium, with bookmarks and resume. The original PDFs are embedded too.

The app has no network dependencies. On Android, download the file and open it in Chrome.

Rebuild: `python3 chain-theory/src/build.py`. This needs `pdftotext` and `pypdf`. The source PDFs are in `pdfs/`, from alexwg.org/publications, and are copyright their author.
