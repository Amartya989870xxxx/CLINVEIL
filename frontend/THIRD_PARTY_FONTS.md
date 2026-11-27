# Bundled fonts

All fonts are installed from npm (Fontsource) and bundled into the build; nothing is loaded from a font CDN.
Each is licensed under the **SIL Open Font License 1.1**, which permits bundling and redistribution with
software. The full licence text ships inside each package (`node_modules/<package>/LICENSE`) and must
accompany any redistributed build.

| font | use | package | copyright |
|---|---|---|---|
| Geist (variable) | interface, body, tables, controls | `@fontsource-variable/geist` | The Geist Project Authors |
| Newsreader (variable, optical size) | editorial headings and statements | `@fontsource-variable/newsreader` | The Newsreader Project Authors |
| IBM Plex Mono | hashes, commits, identifiers | `@fontsource/ibm-plex-mono` | IBM Corp. |
| Noto Sans Devanagari (variable) | Hindi / Devanagari text | `@fontsource-variable/noto-sans-devanagari` | The Noto Project Authors |

The repository's root `THIRD_PARTY_NOTICES.md` was not modified (per instruction); the maintainers should add
these four entries there before release.
