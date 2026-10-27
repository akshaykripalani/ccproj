# Updated Springer LNCS report

`Cloud_Equipment_Monitoring_LNCS.docx` is the edited manuscript; the matching PDF is its native Word render. The supplied Downloads document remains untouched. The report describes the final expanded system rather than the sequence of changes.

The manuscript follows the supplied LNCS layout: A4 page, 12.2 × 19.3 cm text area, Times New Roman body at 10 pt, 14 pt title, 12/10 pt section headings, 9 pt captions, numbered citations, table captions above and figure captions below. Three simple figures have editable SVG sources and high-resolution PNGs under `figures/`. Source guidance was checked against [Springer’s author instructions](https://link.springer.com/series/558/information-for-authors-and-editors).

The student authors are Akshay Kripalani, Joel Jacob, Kaivalya Joglekar, Kanish Jain and Manas Kulkarni, in alphabetical order by first name. Rama Varshney appears last and is identified as Assistant Professor. All share the Department of Computer Engineering, Mukesh Patel School of Technology Management and Engineering, NMIMS, Mumbai, India affiliation. Author order does not indicate contribution. The reproducible author block and all six confirmed emails are stored in `authors.json`. Emails appear in author order; no corresponding author has been designated.

Build with the bundled artifact Python:

```powershell
python assignment_docs/build_updated_report.py
python scripts/render_report.py assignment_docs/updated/Cloud_Equipment_Monitoring_LNCS.docx .runtime/report-final-preview
```

Use the runtime returned by Codex's workspace dependency loader. The Windows rendering fallback uses a dedicated hidden Word instance, opens the manuscript read-only, exports a PDF, closes without saving, and renders every page with Poppler. It was used because LibreOffice is not installed. Visual QA and artifact hashes are recorded in `report-review.json`.
