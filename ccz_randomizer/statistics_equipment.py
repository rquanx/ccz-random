"""Capture actual randomized equipment before a short-circuit rejection."""


def completed_equipment_records(read, *, clock, sleep, check_stop, report,
                                timeout=1.5):
    """Never decode an unconfirmed zero or a changing equipment snapshot.

    Job changes only confirm that the native roll started. In particular the
    accessory records can still contain zero effect IDs at that point. A zero
    is unconfirmed here, not a newly invented 'no effect' mapping.
    """
    deadline = clock() + timeout
    previous = None
    reads = 0
    while True:
        check_stop()
        records = read()
        reads += 1
        zero_indices = [i for i, record in enumerate(records)
                        if not record or record[0] == 0]
        if records and not zero_indices and records == previous:
            if reads > 2:
                report("statistics_equipment_settled", reads=reads)
            return records
        if clock() >= deadline:
            report("statistics_equipment_unconfirmed", reads=reads,
                   zero_indices=zero_indices,
                   records=[record.hex() for record in records])
            raise RuntimeError("宝物采样尚未完整或稳定，未计入本次宝物统计")
        previous = records if not zero_indices else None
        sleep(min(.05, max(0, deadline - clock())))


def capture_equipment_statistics(runner, collect, report_error):
    runner._statistics_equipment = []
    try:
        info = collect()
        runner._statistics_equipment = [
            {"name": name, "effect": effect}
            for items, _category in info for name, effect in items
        ]
    except Exception as error:
        # A statistics failure must not change qualification or save behavior.
        report_error(error)
