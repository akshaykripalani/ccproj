# Assignment submission

**Cloud-Based Industrial Equipment Monitoring and Fault Detection**  
Prepared: 15 October 2026. Source baseline: Git `b31c746`, followed by documentation-only commits.

For the presentation, use the **[architecture PNG](diagrams/02-aws-components.png)** (3840 x 2160, 16:9) or **[editable SVG](diagrams/02-aws-components.svg)**. This single overview groups the implementation into nine blocks. Updated 15 October 2026; the PDF remains the earlier snapshot. Rebuild these images with `python build_architecture.py` from this folder using the document-authoring runtime. The full report builder will use this overview on its next rebuild.

Start with [Submission_Report.pdf](Submission_Report.pdf), the consolidated requirements, design, tools and implementation report. Editable source documents:

1. [Requirements.md](Requirements.md): problem, scope, users, functional and non-functional requirements, and acceptance traceability.
2. [Design_and_Implementation.md](Design_and_Implementation.md): architecture, data model, processing algorithms, authentication, dashboard, deployment, testing, costs and limitations.
3. [Tools_Used.md](Tools_Used.md): AWS services, development tools, libraries, versions and repository map.
4. [Diagrams.md](Diagrams.md): ten architecture/design diagrams, supplied as vector SVG, PNG and editable Mermaid source in `diagrams/`.
5. [Evidence.md](Evidence.md): evidence index, test scope, selected screenshots and submission readiness.

`assets/` contains copies of selected project screenshots. `evidence/` contains compact copies of recorded acceptance summaries and a checksum manifest. The original XML runs, detailed operational records and append-only AWS command log remain in the repository, linked from the evidence document. No account passwords, tokens or email screenshots are included.

The 40-page PDF was rendered for visual review. Local links, required report text, page text bounds and credential patterns were checked; [document-review.json](evidence/document-review.json) records the review scope. The original PRD and application code were unchanged during this submission task.

## Important submission status

The AWS platform and React dashboard are implemented and deployed in Sydney. Recorded automated AWS and browser scenarios passed. **The real initial account's first-password/recovery issue is still open**: the last read-only diagnostic showed `FORCE_CHANGE_PASSWORD`, despite the user reporting that a new password had been selected. Passing disposable-account login tests does not close that issue. Actual final AWS spend also remains to be reconciled after billing delay. Both are disclosed in the report.

This documentation was prepared from checked-in source and recorded deployment evidence. No new AWS deployment, fault injection, shutdown or live test was performed to generate it. Snapshot claims refer to their recorded runs, not continuous availability guarantees. The application remains subject to the existing keep-online instruction.

## Rebuild the report

Run `build_submission.py` with Python and ReportLab, Pillow, pdfplumber and pypdfium2 available. It builds the diagrams and consolidated PDF from the Markdown sources, copies selected evidence, checks links, and records hashes. The authoring environment used Codex's bundled document runtime; it is not an application runtime dependency. The script does not call AWS. Intermediate visual QA files are written to an ignored directory.

PRD.old.md remains the product scope; these documents describe its implemented design and evidence. This submission task does not edit PRD.old.md.

## Updated predictive maintenance manuscript

The current seven-device project report is in `updated/Cloud_Equipment_Monitoring_LNCS.docx` and its matching PDF. `updated/README.md` records format, source preservation and authorship status; older submission artifacts remain historical snapshots.
