"""Freeze the selected rule for one run and all its slot workers."""
from __future__ import annotations

import base64
import json
import zlib

from ccz_randomizer.rules.config import (
    RuleLoadResult, load_rule_config, validate_rule_config,
)

RUN_RULE_ENV = "CCZ_RUN_RULE_CONFIG"


def capture_run_rules(config, environment):
    config = validate_rule_config(config)
    name = config["activeProfile"]
    # Only the active profile is needed. Compression keeps Windows child
    # environment values small even for profiles with large score tables.
    selected = dict(version=config["version"], activeProfile=name,
                    profiles={name: config["profiles"][name]})
    data = json.dumps(selected, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    environment[RUN_RULE_ENV] = base64.b64encode(zlib.compress(data)).decode("ascii")


def load_run_rules(base, environment):
    encoded = environment.get(RUN_RULE_ENV)
    if not encoded:
        loaded = load_rule_config(base)
        return RuleLoadResult(validate_rule_config(loaded.config), loaded.source, loaded.warning)
    # A corrupt run snapshot must fail explicitly instead of silently using
    # another rule and associating its results with the original rule name.
    try:
        config = json.loads(zlib.decompress(base64.b64decode(encoded, validate=True)))
        return RuleLoadResult(validate_rule_config(config), "run")
    except Exception as error:
        raise ValueError("本次随机的规则快照无效，请重新开始随机") from error
