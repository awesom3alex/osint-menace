"""Generate editable Word reports from saved case data."""

from io import BytesIO
import json

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from dossier import SECTIONS, dossier_values


def clean_text(value):
    text = str(value)
    return "".join(char for char in text if char in "\n\r\t" or
                   0x20 <= ord(char) <= 0xD7FF or 0xE000 <= ord(char) <= 0xFFFD or
                   0x10000 <= ord(char) <= 0x10FFFF)


def build_word_report(case):
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.8)
    section.left_margin = section.right_margin = Inches(0.8)
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.color.rgb = RGBColor(0, 0, 0)
    document.styles["Normal"].font.size = Pt(11)
    document.styles["Normal"].paragraph_format.space_after = Pt(7)
    document.core_properties.title = clean_text(case["name"])
    document.core_properties.author = "OSINT Menace"

    document.add_paragraph("Investigation Dossier", "Title")
    document.add_paragraph(clean_text(case["name"]), "Subtitle")
    document.add_paragraph("OSINT Menace | A Defensive Thinking Project.")
    for label, key in (("Case ID", "id"), ("Created", "created_at"), ("Updated", "updated_at")):
        document.add_paragraph(label + ": " + clean_text(case.get(key, "")))
    if case.get("notes"):
        document.add_paragraph(clean_text(case["notes"]))

    values = dossier_values(case)
    for title, fields in SECTIONS:
        document.add_heading(title, level=1)
        filled = False
        for key, label in fields:
            if values[key]:
                filled = True
                document.add_heading(label, level=2)
                document.add_paragraph(clean_text(values[key]))
        if not filled:
            document.add_paragraph("Not recorded.")

    document.add_heading("Saved Evidence", level=1)
    for search in case.get("searches", []):
        document.add_heading(clean_text(search.get("query", "Saved record")), level=2)
        if search.get("review_status") or search.get("analyst_notes") or search.get("tags"):
            document.add_paragraph("Review status: " + clean_text(search.get("review_status", "unreviewed")))
            document.add_paragraph("Tags: " + clean_text(", ".join(search.get("tags", []))))
            if search.get("analyst_notes"):
                document.add_paragraph("Analyst notes: " + clean_text(search["analyst_notes"]))
        document.add_paragraph("Record: " + clean_text(search.get("id", "")) +
                               "\nSaved at: " + clean_text(search.get("created_at", "")) +
                               "\nModule: " + clean_text(search.get("search_type", "")))
        for result in search.get("results", []):
            document.add_heading(clean_text(result.get("name", "Result")), level=3)
            for finding in result.get("findings", []):
                paragraph = document.add_paragraph()
                paragraph.add_run(clean_text(finding.get("label", "Finding")) + ": ").bold = True
                value = finding.get("value", "")
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2, ensure_ascii=False)
                paragraph.add_run(clean_text(value))
                if finding.get("source"):
                    document.add_paragraph("Source: " + clean_text(finding["source"]))
            for link in result.get("links", []):
                document.add_paragraph(clean_text(link.get("label", "Source")) +
                                       "\n" + clean_text(link.get("value", "")))
            for note in result.get("notes", []):
                document.add_paragraph("Note: " + clean_text(note))
    if not case.get("searches"):
        document.add_paragraph("No saved evidence.")
    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output
