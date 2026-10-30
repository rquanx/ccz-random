"""Present the participants of a rule, independently of other captured units."""


def participating_members(detail):
    members = detail.get("members") or []
    eligible = (detail.get("metrics") or {}).get("eligibleMembers")
    if eligible is None:
        return members  # Older snapshots without selection metadata.
    by_name = {row["name"]: row for row in members if isinstance(row, dict) and "name" in row}
    return [by_name[name] for name in eligible if name in by_name]


def job_rule_report(evaluation, jobs, members, *, qualified):
    scores = evaluation.metrics.get("memberScores", [])
    detail = {
        "qualified": qualified,
        "reasons": [] if qualified else list(evaluation.reasons),
        "metrics": evaluation.metrics,
        "members": [
            {"name": member[0], "job": job["name"],
             "score": scores[index] if index < len(scores) else job["score"]}
            for index, (member, job) in enumerate(zip(members, jobs))
        ],
    }
    detail["members"] = participating_members(detail)
    return detail, [f'{row["name"]}:{row["job"]}' for row in detail["members"]]
