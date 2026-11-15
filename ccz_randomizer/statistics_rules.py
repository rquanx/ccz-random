"""Resolve historical snapshots to current rule names without rewriting observations."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ccz_randomizer.rules.config import load_rule_config, rule_file_path
from ccz_randomizer.rules.identity import filtering_fingerprint, rule_identity, statistics_revision


def rule_links(base, rows, *, profiles=None):
    if profiles is None:
        profiles = load_rule_config(base).config["profiles"] if rule_file_path(base).is_file() else {}
    identities = {rule_identity(name, profile): (name, profile) for name, profile in profiles.items()}
    aliases = {alias: (name, profile) for name, profile in profiles.items()
               for alias in (name, *profile.get("statisticsAliases", []))}
    groups = {}
    for revision, old_name, snapshot in rows:
        profile = json.loads(snapshot)
        current = identities.get(rule_identity(old_name, profile))
        if current is None and not profile.get("statisticsId"):
            current = aliases.get(old_name)
        if current:
            name, latest = current
            if profile.get("statisticsGeneration") != latest.get("statisticsGeneration"):
                continue
            if filtering_fingerprint(profile) != filtering_fingerprint(latest):
                continue
            key = statistics_revision(name, latest)
        elif profiles:
            # Removed rules remain in overall observations, without masquerading as a current rule.
            continue
        else:
            name, key = old_name, statistics_revision(old_name, profile)
        groups.setdefault(name, {}).setdefault(key, []).append(revision)
    links = {}
    for name, versions in groups.items():
        # Legacy databases may have several same-name filters. Only the most recently
        # recorded filter belongs to that rule; old observations are retained.
        key = next(reversed(versions))
        links[key] = (name, tuple(versions[key]))
    return links


def resolve_revision(links, revision):
    return links[revision][1] if revision in links else revision


def has_rule_statistics(base, config, changes):
    """Inspect existing associated observations without creating or upgrading a DB.

    None means the existing database could not be read, rather than no data.
    """
    path = Path(base).absolute() / "ccz_fast_data" / "statistics.sqlite3"
    if not path.is_file():
        return False
    profiles = {old_name: config["profiles"][old_name] for _, old_name in changes}
    if not profiles:
        return False
    try:
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=.2)) as db:
            rows = db.execute("SELECT revision,name,snapshot FROM rules r "
                              "WHERE EXISTS (SELECT 1 FROM attempts a WHERE a.revision=r.revision) "
                              "ORDER BY r.rowid").fetchall()
        return bool(rule_links(base, rows, profiles=profiles))
    except (sqlite3.Error, OSError, ValueError):
        return None
