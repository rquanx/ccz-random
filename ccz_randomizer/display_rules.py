"""Bounded declarative display rules; packages contain data, never code."""
from string import Formatter


def render_skill(rules, tables, base, kind, value, strategy=""):
    rule = rules["formats"].get(str(kind))
    if rule is None:
        return base
    context = dict(base=base, value=value + rule.get("adjustment", 0), strategy=strategy)
    op = rule["op"]
    if op == "index":
        context["target"] = tables["ability_names"][value] if rule["minimum"] <= value <= rule["maximum"] else ""
    elif op in ("mask", "transfer"):
        short = tables["ability_short_names"]
        target = value
        if op == "transfer":
            source, target = divmod(value, rule["radix"])
            if target in rule["carryValues"]:
                source += rule["sourceAdjustment"]
                target += rule["carryAdjustment"]
            if not 0 <= source < rule["sourceCount"]:
                source = rule["sourceFallback"]
            context["source"] = short[source]
        mask = target & ((1 << rule["count"]) - 1)
        context["target"] = tables["all_ability_name"] if mask == (1 << rule["count"]) - 1 else "".join(
            short[i] for i in range(rule["count"]) if mask & (1 << i))
    return rule["template"].format_map(context).rstrip()


def render_equipment(data, tables, code, value):
    equipment = data["equipment"]
    rule = equipment["effects"].get(str(code))
    if rule is None:
        return None
    op = rule["op"]
    if op == "skill":
        text = render_skill(data, tables, rule["base"], rule["format"], value)
        separator = rule["separatorOverrides"].get(str(value), rule["separator"])
        return text.replace(" ", separator, 1)
    if op == "lookup" and str(value) in rule["values"]:
        return rule["values"][str(value)]
    strategy = equipment["STRATEGY_NAMES"].get(str(value), equipment["strategyFallback"].format(value=value))
    return rule["template"].format(value=value + rule.get("adjustment", 0), strategy=strategy)


def normalize_name(data, name):
    settings = data["normalization"]
    text = str(name).strip()
    for prefix, replacements in settings["prefixReplacements"].items():
        if text.startswith(prefix):
            for before, after in replacements.items():
                text = text.replace(before, after)
            break
    text = "".join(c for c in text if not c.isspace() and c not in settings["ignoredCharacters"])
    return data["aliases"].get(text, text)


def validate_display_rules(data, tables):
    def fail():
        raise ValueError("名称显示规则无效或需要更新工具引擎")

    def text(value):
        if not isinstance(value, str) or len(value) > 512: fail()

    def mapping(value):
        if not isinstance(value, dict) or len(value) > 2048: fail()
        return value

    def number(value, low, high):
        if type(value) is not int or not low <= value <= high: fail()

    def template(value, fields):
        text(value)
        for _, field, spec, conversion in Formatter().parse(value):
            if field is not None and (field not in fields or spec or conversion): fail()

    try:
        mapping(data)
        formats = mapping(data["formats"])
        for key, rule in formats.items():
            number(int(key), 0, 255)
            mapping(rule)
            op = rule["op"]
            fields = {"literal": {"base"}, "number": {"base", "value"},
                      "strategy": {"base", "strategy"}, "index": {"base", "target"},
                      "mask": {"base", "target"}, "transfer": {"base", "source", "target"}}
            if op not in fields: fail()
            extra = {"literal": set(), "number": {"adjustment"}, "strategy": set(),
                     "index": {"minimum", "maximum"}, "mask": {"count"},
                     "transfer": {"radix", "carryValues", "carryAdjustment", "sourceAdjustment",
                                  "sourceCount", "sourceFallback", "count"}}
            if set(rule) != {"op", "template"} | extra[op]: fail()
            template(rule["template"], fields[op])
            if op == "number": number(rule["adjustment"], -65536, 65536)
            if op == "index":
                number(rule["minimum"], 0, len(tables["ability_names"]) - 1)
                number(rule["maximum"], rule["minimum"], len(tables["ability_names"]) - 1)
            if op in ("mask", "transfer"): number(rule["count"], 1, len(tables["ability_short_names"]))
            if op == "transfer":
                number(rule["radix"], 1, 256)
                number(rule["sourceCount"], 1, len(tables["ability_short_names"]))
                number(rule["sourceFallback"], 0, rule["sourceCount"] - 1)
                number(rule["sourceAdjustment"], -256, 256)
                number(rule["carryAdjustment"], -256, 256)
                if not isinstance(rule["carryValues"], list) or len(rule["carryValues"]) > 256: fail()
                for value in rule["carryValues"]: number(value, 0, rule["radix"] - 1)
        for before, after in mapping(data["aliases"]).items(): text(before); text(after)
        for before, after in mapping(data["catalogOverrides"]).items(): text(before); text(after)
        settings = data["normalization"]
        text(settings["ignoredCharacters"])
        for prefix, replacements in mapping(settings["prefixReplacements"]).items():
            text(prefix)
            for before, after in mapping(replacements).items():
                text(before); text(after)
                if not before: fail()
        equipment = mapping(data["equipment"])
        template(equipment["strategyFallback"], {"value"})
        for name in ("EQUIPMENT_NAMES", "EQUIPMENT_CATEGORY_NAMES", "GOOD_EQUIPMENT_SKILL_MARKERS"):
            if not isinstance(equipment[name], list) or not equipment[name] or len(equipment[name]) > 1024: fail()
            for item in equipment[name]: text(item)
        categories = equipment["EQUIPMENT_CATEGORY_NAMES"]
        if equipment["defaultCategory"] not in categories: fail()
        for name, category in mapping(equipment["EQUIPMENT_CATEGORY_BY_NAME"]).items():
            if name not in equipment["EQUIPMENT_NAMES"] or category not in categories: fail()
        for title, members in equipment["EQUIPMENT_SETS"]:
            text(title)
            if not isinstance(members, list) or any(name not in equipment["EQUIPMENT_NAMES"] for name in members): fail()
        number(equipment["EQUIPMENT_OFFSET"], 0, 2**32 - 1)
        number(equipment["EQUIPMENT_SIZE"], 1, 65536)
        groups = equipment["recordGroups"]
        if not isinstance(groups, list) or not 1 <= len(groups) <= 32: fail()
        for group in groups:
            number(group["count"], 1, 1024); number(group["size"], 1, 256)
            number(group["parameterOffset"], 1, group["size"] - 1)
        if sum(g["count"] for g in groups) != len(equipment["EQUIPMENT_NAMES"]) or sum(g["count"] * g["size"] for g in groups) != equipment["EQUIPMENT_SIZE"]: fail()
        for key, value in mapping(equipment["STRATEGY_NAMES"]).items(): number(int(key), 0, 255); text(value)
        for key, rule in mapping(equipment["effects"]).items():
            number(int(key), 0, 255)
            op = rule["op"]
            if op == "skill":
                if set(rule) != {"op", "base", "format", "separator", "separatorOverrides"}: fail()
                text(rule["base"]); text(rule["separator"])
                if str(rule["format"]) not in formats: fail()
                for parameter, separator in mapping(rule["separatorOverrides"]).items(): number(int(parameter), 0, 255); text(separator)
            elif op in ("literal", "number", "strategy", "lookup"):
                extra = {"literal": set(), "number": {"adjustment"}, "strategy": set(), "lookup": {"values"}}
                if set(rule) != {"op", "template"} | extra[op]: fail()
                template(rule["template"], {"value", "strategy"})
                if op == "number": number(rule["adjustment"], -65536, 65536)
                if op == "lookup":
                    for parameter, value in mapping(rule["values"]).items(): number(int(parameter), 0, 255); text(value)
            else: fail()
    except (KeyError, TypeError, AttributeError, OverflowError):
        fail()
