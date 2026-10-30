# Connected research tools (v0.4.0)

Open a case's **Case tools** menu to use these five features. They preserve existing findings, graphs, reports, and review workflows. All new case data is included in JSON exports and verified case ZIP backups. Internal research pages contain original case content; report redaction does not apply to them. The new research records are not automatically added to shareable reports.

## Cross-case connections

Choose **Cross-case connections**, select up to 20 other cases, and compare. Matches use explicitly typed email, phone, username, and domain values in findings and graph fields. They never use a shared name alone. Existing normalization ignores email/username case, username @ prefixes, phone punctuation, and domain trailing dots. No external queries run. At most 200 candidate pairs are displayed per comparison.

Review the two records, their recorded sources, and verification states. Record **unresolved**, **link for investigation**, or **dismiss match**, with required reasoning. The current case retains the comparison snapshot and decision timestamp; the other case and both original records remain intact. These decisions do not establish common identity or merge cases. If either case changed since the comparison, reload before recording the decision. Up to 1,000 decisions per case are retained.

## Evidence reader

Upload a PDF, PNG, JPEG, or WebP under **Evidence reader**, optionally associating it with a saved finding. Extraction runs locally. Embedded PDF text is preferred; image-only PDF pages and screenshots use Tesseract English OCR. Search all documents or a selected document. Each result gives the page number, text snippet, extraction method, full page text, and a link to the original at that page. PDF page fragments depend on the browser's PDF viewer.

Original uploaded bytes, SHA-256, upload time, file name, page text, and finding association remain in the case. Original downloads verify the stored hash. Case-wide search also finds extracted text. PDF text and OCR are imperfect; verify results against the original. Layout, handwriting, unusual fonts, and other languages can reduce accuracy. No uploaded image is submitted to an image-search service.

Limits: 5 MB per upload, 30 PDF pages, 20 documents per case, 60,000 extracted characters per page, 20-megapixel screenshots, bounded subprocess durations and an overall extraction deadline. Documents are embedded in the existing case JSON for portable backups; the existing 16 MB case limit also applies, including base64 overhead. A rejected upload does not partially save a document. Split large collections into smaller cases/documents.

Docker installs Poppler and Tesseract English automatically. Native web development needs `pdftotext`, `pdfinfo`, `pdftoppm`, and `tesseract` on PATH (macOS: `brew install poppler tesseract`). Missing tools produce an actionable reader error.

## Investigation questions

Choose **Investigation questions** to record a question, working answer, status, supporting findings, conflicting findings, unanswered points, and next steps. A finding cannot be both supporting and conflicting in one revision. Follow the source links to review the underlying finding. Marking a question Answered requires an answer; it remains the analyst's assessment. Each save retains a full revision. Limits are 100 questions, 100 revisions per question, and 5,000 characters per narrative field.

## Scheduled source monitoring

Choose **Source monitoring**, select a finding with a public source URL, and enable an hourly, six-hourly, daily, or weekly check. This explicitly authorizes future requests for that source while the web app is running. Up to 50 sources per case are supported. Pause and re-enable controls are provided.

The normal `start.sh` Gunicorn worker starts a background scheduler through `gunicorn.conf.py`. A host-local process lock prevents two workers from independently running the same scheduler. Due checks run approximately every 30 seconds, serially. Downtime is not replayed: an overdue source is checked once after restart and its next run is scheduled from that check. The development Flask server and terminal interface do not start the scheduler.

Checks reuse protected public-page text capture: public-address DNS validation pinned to connections, validated redirects, standard web ports, HTML/plain-text limits, and bounded network waits. They do not log in, execute scripts, render screenshots, or bypass access controls. If a finding's source URL changes, its monitor pauses for review.

The first successful check establishes a baseline. Only distinct consecutive text versions are retained. Changed versions appear in the existing review inbox; unchanged checks update last/next-check status without creating inbox items or activity events. The UI shows errors and pauses after three consecutive failures. A changed source reaching the 25-observation retention limit pauses instead of deleting history. Dynamic content may cause noisy changes. There are no email, push, or external notification deliveries.

Case backups retain monitor configuration and outcomes. Restored cases have a new case ID, so imported monitors remain inactive until explicitly re-enabled in the restored case. Merely viewing an import preview does not contact sources.

## Saved research workflows

Choose **Saved workflows** to save a title, target, identifier type, selected steps, and ordering. Steps are Public-source search, Archived page review, Related identifiers, and Review findings. Several ordering presets are available; omitted steps are skipped. Each step opens the corresponding existing tool with case context. Search and archive tools still require explicit launch. Domain archive steps prefill an HTTPS URL; for other identifier types enter the relevant public page URL before launching archive research.

Related identifiers lists typed identifiers already saved to this case, with source links and source-expansion previews, plus access to cross-case comparison. It does not infer relationships. Mark steps complete or reopen them with notes. Reuse a saved workflow with another target to create a fresh checklist with the same selected step order and empty progress. Up to 50 workflows per case are retained. Workflow steps never silently accept findings into a case.
