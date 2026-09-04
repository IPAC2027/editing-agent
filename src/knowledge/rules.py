"""Load and retrieve versioned JACoW editorial rule packs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_RULESETS_DIR = Path(__file__).with_name("rulesets")
_REQUIRED_PACK_FIELDS = {"schema_version", "id", "version", "title", "sources", "rules"}
_REQUIRED_RULE_FIELDS = {"id", "title", "category", "applies_to", "summary", "agent_guidance", "sources"}


class RulePackError(ValueError):
    """Raised when a requested rule pack is unavailable or invalid."""


def available_rule_packs() -> dict[str, list[str]]:
    """Return installed rule-pack IDs and their available versions."""
    packs: dict[str, list[str]] = {}
    for pack_dir in sorted(path for path in _RULESETS_DIR.iterdir() if path.is_dir()):
        versions = sorted(path.stem for path in pack_dir.glob("*.json"))
        if versions:
            packs[pack_dir.name] = versions
    return packs


def load_rule_pack(pack_id: str = "jacow", version: str | None = None) -> dict[str, Any]:
    """Load one validated JSON rule pack, defaulting to its latest version."""
    pack_dir = _RULESETS_DIR / pack_id
    if not pack_dir.is_dir():
        raise RulePackError(f"Unknown rule pack: {pack_id}")

    versions = sorted(path.stem for path in pack_dir.glob("*.json"))
    if not versions:
        raise RulePackError(f"Rule pack has no versions: {pack_id}")
    selected_version = version or versions[-1]
    path = pack_dir / f"{selected_version}.json"
    if not path.is_file():
        raise RulePackError(f"Rule pack {pack_id!r} has no version {selected_version!r}")

    data = json.loads(path.read_text(encoding="utf-8"))
    _validate_rule_pack(data, path)
    return data


def search_rules(
    query: str = "",
    *,
    categories: Iterable[str] | None = None,
    applies_to: str | None = None,
    pack_id: str = "jacow",
    version: str | None = None,
) -> list[dict[str, Any]]:
    """Return rules matching text, category, and source-format filters."""
    pack = load_rule_pack(pack_id, version)
    category_set = {category.lower() for category in categories or ()}
    tokens = [token for token in query.lower().split() if token]
    matches: list[dict[str, Any]] = []
    for rule in pack["rules"]:
        if category_set and rule["category"].lower() not in category_set:
            continue
        if applies_to and applies_to not in rule["applies_to"]:
            continue
        searchable = json.dumps(rule, ensure_ascii=False).lower()
        if all(token in searchable for token in tokens):
            matches.append(rule)
    return matches


def agent_context(
    query: str = "",
    *,
    categories: Iterable[str] | None = None,
    applies_to: str | None = None,
    limit: int = 12,
    pack_id: str = "jacow",
    version: str | None = None,
) -> str:
    """Build compact, sourced guidance suitable for an editor or LLM prompt."""
    pack = load_rule_pack(pack_id, version)
    rules = search_rules(
        query,
        categories=categories,
        applies_to=applies_to,
        pack_id=pack_id,
        version=pack["version"],
    )[:limit]
    source_urls = {source["id"]: source["url"] for source in pack["sources"]}
    lines = [f"Rule pack: {pack['title']} v{pack['version']}"]
    for rule in rules:
        source_labels = ", ".join(
            f"{source_id}: {source_urls.get(source_id, source_id)}"
            for source_id in rule["sources"]
        )
        guidance = rule["agent_guidance"]
        lines.extend([
            f"- {rule['id']} [{rule['category']}; {', '.join(rule['applies_to'])}]: {rule['summary']}",
            f"  Agent action: {guidance['action']}",
            f"  Automation: {guidance['automation']}; escalate when: {guidance['escalate_when']}",
            f"  Sources: {source_labels}",
        ])
    if not rules:
        lines.append("- No matching rules in this pack.")
    for decision in pack.get("common_editor_decisions", []):
        source_labels = ", ".join(
            f"{source_id}: {source_urls.get(source_id, source_id)}"
            for source_id in decision["sources"]
        )
        lines.extend([
            f"- {decision['id']} [editor policy]: {decision['decision']}",
            f"  Policy: {decision['policy']}",
            f"  Sources: {source_labels}",
        ])
    return "\n".join(lines)


def _validate_rule_pack(data: Any, path: Path) -> None:
    if not isinstance(data, dict) or not _REQUIRED_PACK_FIELDS <= data.keys():
        raise RulePackError(f"Invalid rule-pack schema: {path}")
    if not isinstance(data["rules"], list) or not data["rules"]:
        raise RulePackError(f"Rule pack must contain rules: {path}")
    rule_ids: set[str] = set()
    for rule in data["rules"]:
        if not isinstance(rule, dict) or not _REQUIRED_RULE_FIELDS <= rule.keys():
            raise RulePackError(f"Invalid rule in pack: {path}")
        if rule["id"] in rule_ids:
            raise RulePackError(f"Duplicate rule ID {rule['id']!r}: {path}")
        rule_ids.add(rule["id"])
