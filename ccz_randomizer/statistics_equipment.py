"""Capture actual randomized equipment before a short-circuit rejection."""


def capture_equipment_statistics(runner, collect, report_error):
    try:
        info = collect()
        runner._statistics_equipment = [
            {"name": name, "effect": effect}
            for items, _category in info for name, effect in items
        ]
    except Exception as error:
        # A statistics failure must not change qualification or save behavior.
        report_error(error)
