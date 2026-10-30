from src.knowledge import agent_context, available_rule_packs, load_rule_pack, search_rules


def test_jacow_rule_pack_is_versioned_and_has_required_sections():
    packs = available_rule_packs()
    pack = load_rule_pack()

    assert packs["jacow"] == ["1.0.0", "1.1.0"]
    assert pack["id"] == "jacow"
    assert pack["version"] == "1.1.0"        # the latest pack loads by default
    assert {"template", "units", "references"} <= {rule["category"] for rule in pack["rules"]}
    assert len(pack["common_editor_decisions"]) >= 3


def test_rule_search_filters_by_category_format_and_text():
    rules = search_rules("doi", categories=("references",), applies_to="latex")

    assert "ANNEXB-DOI-01" in {rule["id"] for rule in rules}
    assert all(rule["category"] == "references" for rule in rules)
    assert all("latex" in rule["applies_to"] for rule in rules)


def test_agent_context_is_compact_and_includes_rule_provenance():
    context = agent_context(categories=("units",), applies_to="latex")

    assert "JACoW LaTeX and Annex B editorial rules v1.1.0" in context
    assert "JACOW-UNIT-01" in context
    assert "EDITOR-DECISION-01" in context
    assert "https://ipac-docs.jacow.org/Paper/Writing/latex/" in context
    assert "Automation:" in context


def test_every_shared_check_traces_back_to_a_rule():
    """The PDF, body-text and reference-form checks each name their rule."""
    pack = load_rule_pack()
    text = " ".join(rule["agent_guidance"]["action"] for rule in pack["rules"])
    for check_id in ("PDF-SIZE-01", "PDF-MARGIN-01", "PDF-PAGENUM-01", "PDF-FONT-01",
                     "PDF-FONT-02", "PDF-LINK-01", "TXT-TAB-01", "TXT-FIG-01",
                     "TXT-EQ-01", "TXT-ABS-01", "REF-FORM-01", "REF-FORM-02",
                     "REF-INT-01", "REF-INT-02", "REF-INT-03", "FMT-REF-02",
                     "PDF-DOI-01", "WORD-TITLE-01", "WORD-AUTH-02", "WORD-UNIT-01",
                     "WORD-UNIT-02"):
        assert check_id in text, f"{check_id} has no rule in the pack"
