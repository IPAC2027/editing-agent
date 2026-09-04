from src.knowledge import agent_context, available_rule_packs, load_rule_pack, search_rules


def test_jacow_rule_pack_is_versioned_and_has_required_sections():
    packs = available_rule_packs()
    pack = load_rule_pack()

    assert packs["jacow"] == ["1.0.0"]
    assert pack["id"] == "jacow"
    assert pack["version"] == "1.0.0"
    assert {"template", "units", "references"} <= {rule["category"] for rule in pack["rules"]}
    assert len(pack["common_editor_decisions"]) >= 3


def test_rule_search_filters_by_category_format_and_text():
    rules = search_rules("doi", categories=("references",), applies_to="latex")

    assert "ANNEXB-DOI-01" in {rule["id"] for rule in rules}
    assert all(rule["category"] == "references" for rule in rules)
    assert all("latex" in rule["applies_to"] for rule in rules)


def test_agent_context_is_compact_and_includes_rule_provenance():
    context = agent_context(categories=("units",), applies_to="latex")

    assert "JACoW LaTeX and Annex B editorial rules v1.0.0" in context
    assert "JACOW-UNIT-01" in context
    assert "EDITOR-DECISION-01" in context
    assert "https://ipac-docs.jacow.org/Paper/Writing/latex/" in context
    assert "Automation:" in context
