"""Capture every supported job's talents from the same random result."""
from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.runtime.skill_memory import (
    ProcessMemoryReader, read_skill_memory, job_rule_matches, SKILL_RULE_STRIDE,
)


def read_job_talents(pid, *, reader_factory=ProcessMemoryReader):
    snapshot = read_skill_memory(pid, [0], reader_factory=reader_factory)
    return [
        {"jobId": job_id, "name": values[0], "talents": [
            skill.display_name for skill in snapshot.catalog
            if job_rule_matches(snapshot.rule_table[skill.internal_id * SKILL_RULE_STRIDE + 6],
                                job_id, snapshot.direct_job_match)
        ]}
        for job_id, values in JOB_MAP.items()
    ]
