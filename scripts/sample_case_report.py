"""Generate a fictional report fixture for PDF layout verification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw

import case_features
from pdf_reports import generate

case_id = "00000000-0000-4000-8000-000000000001"
case_features.EVIDENCE_DIR = Path("tmp/pdfs/evidence")
folder = case_features.EVIDENCE_DIR / case_id
folder.mkdir(parents=True, exist_ok=True)
eid = "0" * 31 + "1"
image = Image.new("RGB", (1200, 600), "#101c25")
draw = ImageDraw.Draw(image)
draw.text(
    (45, 50), "FICTIONAL EVIDENCE - OSINT Menace layout validation", fill="#5cf5d0", font_size=30
)
draw.text(
    (45, 130),
    "Username: example   |   Source: https://example.com/profile",
    fill="white",
    font_size=24,
)
draw.text(
    (45, 210),
    "Public profile candidate. Analyst verification is required.",
    fill="white",
    font_size=24,
)
image.save(folder / (eid + ".png"))
case = dict(
    id=case_id,
    name="Sample investigation - fictional data",
    created_at="2026-10-16T19:00:00Z",
    updated_at="2026-10-16T19:15:00Z",
    notes="This report uses fictional targets and generated evidence. It demonstrates report selection, verification labels, source attribution, notes, screenshots, long text, and pagination.",
    searches=[
        dict(
            id="sample",
            query="example",
            search_type="unified username",
            created_at="2026-10-16T19:05:00Z",
            results=[
                dict(
                    name="Public profile review",
                    module=dict(name="Sample tool"),
                    findings=[
                        dict(
                            label="Profile candidate",
                            value={
                                "username": "example",
                                "url": "https://example.com/profile",
                                "found": True,
                            },
                            source="Example platform",
                            verification_status="Confirmed",
                            analyst_notes="Confirmed for this fictional test fixture only. Real findings require independent verification.",
                            reviewed_at="2026-10-16T19:10:00Z",
                            evidence=[
                                dict(
                                    id=eid,
                                    caption="Generated screenshot for layout validation - https://example.com/profile",
                                    created_at="2026-10-16T19:08:00Z",
                                )
                            ],
                        ),
                        dict(
                            label="Rejected candidate",
                            value="THIS_FINDING_MUST_BE_EXCLUDED",
                            source="Sample",
                            include_in_report=False,
                        ),
                        dict(
                            label="Analyst context",
                            value="Long output wrapping test. "
                            + (
                                "This is fictional context retained to verify readable line wrapping and stable page breaks. "
                                * 75
                            ),
                            source="Analyst test fixture",
                            verification_status="Unverified",
                        ),
                    ],
                    links=[dict(label="Public source", value="https://example.com/profile")],
                    notes=["Retrieved at 2026-10-16T19:05:00Z; fictional source."],
                )
            ],
        )
    ],
)
Path("output/pdf/osint-menace-report-preview.pdf").write_bytes(generate(case))
print("Sample report generated with fictional data.")
