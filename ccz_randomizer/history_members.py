"""Resolve participants from each result's own saved selection and personnel."""
from ccz_randomizer.jobs import JOB_MAP


def history_members(snapshot):
    saved = snapshot.get("members") or []
    detail = snapshot.get("detail") or {}
    job = detail.get("job") or {}
    selected = (job.get("metrics") or {}).get("eligibleMembers")
    if selected is None:
        return saved  # Legacy records without selection evidence.
    by_name = {row["name"]: row for row in saved}
    jobs = {row["name"]: row for row in job.get("members", [])}
    personnel = {}
    for key in ("personnel", "fixedPersonnel"):
        for row in snapshot.get(key) or detail.get(key) or []:
            personnel[row["name"]] = row
    result = []
    for name in dict.fromkeys(selected):
        scores = jobs.get(name, {})
        if name in by_name:
            member = dict(by_name[name])
        else:
            row = personnel.get(name)
            member = {"name": name}
            if row is not None:
                member.update(
                    job=row.get("job") or JOB_MAP.get(row.get("jobId"), ("未知兵种",))[0],
                    personalSkills=[{"name": value} for value in row.get("personalTalents", [])],
                    jobSkills=[{"name": value} for value in row.get("jobTalents", [])],
                )
            else:
                # Never replace a missing selected person with an initial member.
                member.update(personalSkills=[{"name": "历史记录未保存"}],
                              jobSkills=[{"name": "历史记录未保存"}])
        if scores.get("job"):
            member["job"] = scores["job"]
        if "score" in scores:
            member["jobScore"] = scores["score"]
        result.append(member)
    return result
