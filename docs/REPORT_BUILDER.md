# Report builder

Open a case and choose **Export & backup → Build report**. Existing exports keep their previous behavior until the builder is first saved.

1. Write the investigation purpose, key findings, and outstanding questions. The application does not invent conclusions.
2. Select findings, screenshots, case notes, filled dossier sections, and graphs. Use **Move up** and **Move down** to choose the reading order. Graphs retain their configured report view.
3. Choose **Save and preview**. Missing summary sections, missing screenshot files, and empty graph views are flagged for review. Expand **View exact PDF layout** to inspect the actual paginated PDF before downloading.
4. Download PDF or Word. The HTML report and Markdown exports also use the saved composition. JSON remains a complete case export.

Evidence numbers are assigned in reading order and reused for the finding, its screenshots, graph connections, graph objects, and source appendix. Selected graphs automatically include their linked sources in the appendix even if the corresponding finding is not separately selected. Existing finding exclusions are respected, including graph objects and connections linked to excluded evidence. Internal case references appear in the source appendix for traceability.

Report settings are saved in the case and carried in backups. Moving or excluding a report item does not alter the original evidence. After the first save, newly added case content is available in the builder but remains unselected. Deleted content is omitted automatically. If the case changes while the builder is open, saving is refused until the builder is reloaded to prevent overwriting newer work.

The report preview is a content preview; the embedded PDF shows the exact PDF pagination. Word pagination can differ by editor.
