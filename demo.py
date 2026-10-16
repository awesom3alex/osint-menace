"""Synthetic case data for the public demo. No network lookups are performed."""

DEMO_ID = "00000000-0000-4000-8000-000000000001"


def demo_case():
    from dossier import SECTIONS

    dossier = {key: "Not recorded in this fictional training scenario."
               for _, fields in SECTIONS for key, _ in fields}
    dossier.update({
        "subject_name": "Jordan Example (fictional)",
        "analyst": "Training Analyst / DEMO-01",
        "reference": "TRAINING-001",
        "summary": "Fictional digital footprint review for a community volunteer. Two sample records demonstrate how source observations support a case. No real person was investigated.",
        "posters": "Training brief: https://example.com/training-brief",
        "birthday": "Adult; date of birth not provided.",
        "aliases": "Jordan E. (provided in the fictional brief)",
        "handles": "jordan_example_demo",
        "phones": "+1 202-555-0147 (fictional example number)",
        "relations": "No relationships provided.",
        "addresses": "No residential address provided.",
        "health": "No health information provided or inferred.",
        "missing_history": "Not a missing-person investigation.",
        "markers": "Not relevant to this training scenario.",
        "identity_context": "No additional identity details provided.",
        "context": "Demonstration data only. All source URLs use the example.com domain.",
        "result_aliases": "Jordan E. appears in the simulated volunteer listing. Identity association remains unverified.",
        "result_handles": "One simulated profile candidate: https://example.com/profiles/jordan_example_demo",
        "result_phones": "The supplied fictional number has not been associated with any account.",
        "result_relations": "No findings recorded.",
        "result_addresses": "No findings recorded.",
        "result_health": "No health conclusions recorded.",
        "result_markers": "No physical-marker conclusions recorded.",
        "result_identity": "No additional identity conclusions recorded.",
        "result_other": "A simulated community listing and profile share a display name. A name match alone is insufficient to confirm identity. See the supporting records below.",
        "methodology": "Reviewed a fictional intake brief and two synthetic source records. These records were prepared locally; no external searches were executed.",
        "tasks": "1. Obtain a second independent identifier.\n2. Review the candidate profile before marking it relevant.\n3. Document the basis for any identity association.",
        "observations": "This case illustrates the difference between provided background, source observations, and analyst conclusions.",
        "search_log": "Synthetic profile listing | jordan_example_demo | Candidate profile only | DEMO-E01\nSynthetic community listing | Jordan E. | Display-name overlap | DEMO-E02\nNo actual tools or sites were queried.",
    })
    searches = []
    for number, (label, url, observation) in enumerate([
        ("Candidate profile", "https://example.com/profiles/jordan_example_demo", "Simulated profile candidate; identity unverified."),
        ("Community volunteer listing", "https://example.com/community/volunteers", "Simulated listing uses the display name Jordan E.; association unverified."),
    ], 1):
        searches.append({
            "id": "DEMO-E0" + str(number), "created_at": "2026-10-14T12:00:00+00:00",
            "search_type": "demo:synthetic", "query": label,
            "summary": {"targets": 1, "findings": 1, "links": 1, "notes": 1},
            "results": [{"name": label, "findings": [
                {"label": "Observation", "value": observation, "source": "Synthetic training record"}],
                "links": [{"label": label, "value": url}],
                "notes": ["Fictional demo evidence. No live lookup performed."]}],
        })
    return {"id": DEMO_ID, "name": "Demo: Jordan Example", "is_demo": True,
            "notes": "Fictional training case. Read-only demonstration; no real person or live investigation.",
            "created_at": "2026-10-14T12:00:00+00:00", "updated_at": "2026-10-14T12:00:00+00:00",
            "dossier": dossier, "searches": searches,
            "summary": {"searches": 2, "findings": 2, "links": 2, "notes": 2}}
