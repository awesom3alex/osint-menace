"""Paginated case reports from selected findings and locally attached evidence."""

import re
import textwrap
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from flask import Blueprint, Response
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

import case_features
import case_workflow
from readable_results import readable_text

bp = Blueprint("pdf_report", __name__)


def generate(case):
    case = case_workflow.report_case(case)
    import reportlab

    font_dir = Path("/usr/share/fonts/truetype/dejavu")
    normal = font_dir / "DejaVuSans.ttf"
    bold = font_dir / "DejaVuSans-Bold.ttf"
    if not normal.exists():
        font_dir = Path(reportlab.__file__).parent / "fonts"
        normal, bold = font_dir / "Vera.ttf", font_dir / "VeraBd.ttf"
    pdfmetrics.registerFont(TTFont("Menace", str(normal)))
    pdfmetrics.registerFont(TTFont("Menace-Bold", str(bold)))
    pdfmetrics.registerFontFamily(
        "Menace", normal="Menace", bold="Menace-Bold", italic="Menace", boldItalic="Menace-Bold"
    )
    styles = getSampleStyleSheet()
    base = dict(
        fontName="Menace",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#162938"),
        splitLongWords=True,
        spaceAfter=8,
    )
    body = ParagraphStyle("Body", **base)
    muted = ParagraphStyle(
        "Meta", parent=body, fontSize=8, leading=12, textColor=colors.HexColor("#506474")
    )
    title = ParagraphStyle(
        "CaseTitle", parent=body, fontName="Menace-Bold", fontSize=24, leading=30, spaceAfter=14
    )
    heading = ParagraphStyle(
        "SectionTitle",
        parent=body,
        fontName="Menace-Bold",
        fontSize=15,
        leading=20,
        spaceBefore=18,
        spaceAfter=10,
        keepWithNext=True,
    )
    finding_style = ParagraphStyle(
        "Finding",
        parent=body,
        fontName="Menace-Bold",
        fontSize=11,
        leading=16,
        spaceBefore=12,
        keepWithNext=True,
    )

    def paragraph(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(8.5 * inch, 11 * inch),
        rightMargin=50,
        leftMargin=50,
        topMargin=56,
        bottomMargin=52,
        title=str(case.get("name", "Case report")),
        author="OSINT Menace",
        allowSplitting=1,
    )
    selected = [
        f
        for search in case.get("searches", [])
        for section in search.get("results", [])
        for f in section.get("findings", [])
        if f.get("include_in_report", True)
    ]
    counts = {
        status: sum(f.get("verification_status", "Unverified") == status for f in selected)
        for status in ("Unverified", "Confirmed", "False positive")
    }
    story = [
        paragraph("OSINT MENACE  /  INVESTIGATION REPORT", muted),
        paragraph(case.get("name", "Untitled case"), title),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0d9488")),
        Spacer(1, 12),
        paragraph("Case ID: " + str(case["id"]), muted),
        paragraph(
            "Created: "
            + str(case.get("created_at", ""))
            + "\nUpdated: "
            + str(case.get("updated_at", "")),
            muted,
        ),
        paragraph(
            f"{len(selected)} selected findings | {counts['Confirmed']} confirmed | {counts['Unverified']} unverified | {counts['False positive']} false positives",
            body,
        ),
        paragraph(
            "Verification labels and notes are analyst assessments. Tool matches alone do not prove identity. Phone region and carrier metadata are not live location.",
            muted,
        ),
    ]
    if case.get("notes"):
        story.extend([paragraph("Case notes", heading), paragraph(case["notes"])])
    for search in case.get("searches", []):
        sections = [
            s
            for s in search.get("results", [])
            if any(f.get("include_in_report", True) for f in s.get("findings", []))
            or (not s.get("findings") and s.get("links"))
        ]
        if not sections:
            continue
        story.extend(
            [
                paragraph(search.get("query", "Search"), heading),
                paragraph(
                    "Search type: "
                    + str(search.get("search_type", ""))
                    + " | Retrieved: "
                    + str(search.get("created_at", "")),
                    muted,
                ),
            ]
        )
        for section in sections:
            story.append(paragraph(section.get("name", "Results"), finding_style))
            for finding in section.get("findings", []):
                if not finding.get("include_in_report", True):
                    continue
                status = finding.get("verification_status", "Unverified")
                story.append(
                    paragraph(
                        str(finding.get("label", "Finding")) + "  [" + status + "]", finding_style
                    )
                )
                story.append(
                    paragraph(
                        "Source: "
                        + str(
                            finding.get("source")
                            or section.get("module", {}).get("name", "OSINT Menace")
                        ),
                        muted,
                    )
                )
                if finding.get("collected_at"):
                    story.append(paragraph("Collected (UTC): " + finding["collected_at"], muted))
                if finding.get("source_url"):
                    story.append(paragraph("Source page: " + finding["source_url"], muted))
                for source in finding.get("merged_sources", []):
                    story.append(
                        paragraph(
                            "Merged source: "
                            + source["source"]
                            + " | "
                            + source["collected_at"]
                            + " | "
                            + source["verification_status"]
                            + "\n"
                            + source["source_url"]
                            + "\n"
                            + source["analyst_notes"],
                            muted,
                        )
                    )
                text = readable_text(finding.get("value"))
                if len(text) > 40000:
                    text = (
                        text[:40000]
                        + "\n[Excerpt limited to 40,000 characters. Full captured data is available in the case JSON export.]"
                    )
                # Small paragraphs split reliably over pages, including very long tool output.
                for chunk in textwrap.wrap(
                    text,
                    width=1500,
                    break_long_words=False,
                    break_on_hyphens=False,
                    replace_whitespace=False,
                ):
                    story.append(paragraph(chunk))
                if finding.get("analyst_notes"):
                    story.append(paragraph("Analyst notes: " + finding["analyst_notes"]))
                if finding.get("reviewed_at"):
                    story.append(paragraph("Reviewed: " + finding["reviewed_at"], muted))
                for evidence in finding.get("evidence", []):
                    eid = evidence.get("id", "")
                    if not re.fullmatch(r"[a-f0-9]{32}", eid):
                        continue
                    path = case_features.EVIDENCE_DIR / case["id"] / (eid + ".png")
                    if path.is_file():
                        image = Image(str(path))
                        scale = min(doc.width / image.imageWidth, 3.5 * inch / image.imageHeight, 1)
                        image.drawWidth = image.imageWidth * scale
                        image.drawHeight = image.imageHeight * scale
                        image.hAlign = "LEFT"
                        story.extend(
                            [
                                Spacer(1, 8),
                                image,
                                paragraph(
                                    "Evidence: "
                                    + evidence.get("caption", "Screenshot")
                                    + "\n"
                                    + case_workflow.evidence_text(evidence),
                                    muted,
                                ),
                            ]
                        )
                    else:
                        story.append(
                            paragraph(
                                "Screenshot file unavailable: " + evidence.get("caption", ""), muted
                            )
                        )
            if section.get("links"):
                source_block = [paragraph("Source links", finding_style)]
                for link in section["links"]:
                    url = str(link.get("value", ""))
                    if urlsplit(url).scheme not in ("http", "https"):
                        continue
                    source_block.append(
                        paragraph(str(link.get("label", "Source")) + "\n" + url, muted)
                    )
                source_block.extend(paragraph(note, muted) for note in section.get("notes", []))
                story.append(KeepTogether(source_block))
            else:
                for note in section.get("notes", []):
                    story.append(paragraph(note, muted))
    if not selected:
        story.append(
            paragraph(
                "No findings are selected for this report. Select findings in the case workspace.",
                body,
            )
        )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(50, 39, document.pagesize[0] - 50, 39)
        canvas.setFont("Menace", 8)
        canvas.setFillColor(colors.HexColor("#506474"))
        canvas.drawString(50, 25, "OSINT Menace | Analyst case report")
        canvas.drawRightString(document.pagesize[0] - 50, 25, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


@bp.get("/cases/<case_id>/report.pdf")
def export_pdf(case_id):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
    pdf = generate(case)
    filename = (
        re.sub(r"[^A-Za-z0-9_.-]+", "-", case.get("name", "case")).strip("-").lower() or "case"
    )
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}-report.pdf"'},
    )
