"""Editable dossier sections based on the supplied investigation template."""

SECTIONS = [
    ("Report Details", [
        ("subject_name", "Subject name"), ("analyst", "Prepared by / analyst identifier"),
        ("reference", "External case reference"), ("summary", "Executive summary"),
    ]),
    ("Provided Bio Info", [
        ("posters", "Missing person poster / aggregation source references"),
        ("birthday", "Age / birthday"), ("aliases", "Provided aliases"),
        ("handles", "Provided social media handles"), ("phones", "Associated phone numbers"),
        ("relations", "Associated relatives / spouses / significant others"),
        ("addresses", "Provided addresses"), ("health", "Reported mental health context"),
        ("missing_history", "Previous missing persons history"),
        ("markers", "Provided physical markers: hair, eyes, height, scars, piercings, tattoos"),
        ("identity_context", "Other provided identity information"),
        ("context", "Other identifiers and context"),
    ]),
    ("Investigation Results", [
        ("result_aliases", "Aliases"), ("result_handles", "Social media handles"),
        ("result_phones", "Phone numbers"), ("result_relations", "Relatives / spouses / significant others"),
        ("result_addresses", "Addresses"), ("result_health", "Reported health context and supporting sources"),
        ("result_markers", "Additional physical markers"),
        ("result_identity", "Other identity information and supporting sources"),
        ("result_other", "Other identifiers and relevant results"),
    ]),
    ("Investigative Methodology", [
        ("methodology", "Methods and sources"), ("tasks", "Open tasks / help needed"),
        ("observations", "Miscellaneous notes and observations"),
        ("search_log", "External search log: tool/site, query, takeaways, raw data reference"),
    ]),
]


def dossier_values(case):
    stored = case.get("dossier", {})
    return {key: stored.get(key, "") for _, fields in SECTIONS for key, _ in fields}


def markdown_dossier(case):
    values = dossier_values(case)
    lines = []
    for title, fields in SECTIONS:
        lines.extend(["", "## " + title, ""])
        for key, label in fields:
            if values[key]:
                lines.extend(["### " + label, "", values[key], ""])
    return lines
