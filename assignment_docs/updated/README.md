# Final Springer two-column paper

Use `Cloud_Equipment_Monitoring_Springer_TwoColumn.docx` and its matching PDF for the final submission. The six-page paper describes the completed system, including the three/two/two default fleet profiles, current outlooks separated from history, 86 backend tests, 40 controlled browser scenarios and 14 live automatic recoveries. The supplied Downloads document remains untouched. The earlier `Cloud_Equipment_Monitoring_LNCS` pair is retained as the previous single-column revision.

The requested two-column layout uses a Word adaptation of Springer Nature's journal `sn-jnl` template with its `iicol` option, checked against the [official author-support page](https://www.springernature.com/gp/authors/campaigns/latex-author-support) and the class file in its [official template package](https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/18782940/data/v12). LNCS is a separate single-column proceedings format; this revision follows the user's explicit two-column request. No particular journal was specified.

The paper uses A4 pages with a 160 × 216 mm text area, two 76 mm columns and an 8 mm gap. Times New Roman body text is 10 pt with 12 pt leading; the title is 17 pt, author names 12 pt, affiliation 11 pt, section/subsection headings 14/12 pt, captions and tables 8 pt, and references 9 pt. Title, author block and abstract span the text width. Three simple full-width diagrams remain readable; tables fit a single column and stay intact. Captions are above tables and below figures, references are numbered, and the final page is balanced. Editable SVG sources and high-resolution PNGs are under `figures/`.

The student authors are Akshay Kripalani, Joel Jacob, Kaivalya Joglekar, Kanish Jain and Manas Kulkarni, in alphabetical order by first name. Rama Varshney appears last and is identified as Assistant Professor. All share the Department of Computer Engineering, Mukesh Patel School of Technology Management and Engineering, NMIMS, Mumbai, India affiliation. Author order does not indicate contribution. The reproducible author block and all six confirmed emails are stored in `authors.json`. Emails appear in author order; no corresponding author has been designated.

Build with the bundled artifact Python:

```powershell
python assignment_docs/build_updated_report.py
python scripts/render_report.py assignment_docs/updated/Cloud_Equipment_Monitoring_Springer_TwoColumn.docx .runtime/report-two-column-preview
```

Use the runtime returned by Codex's workspace dependency loader. The Windows rendering fallback uses a dedicated hidden Word instance, opens the manuscript read-only, exports a PDF, closes without saving, and renders every page with Poppler. It was used because LibreOffice is not installed. Visual QA and artifact hashes are recorded in `report-review.json`.
