from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def normalized(value: str) -> str:
    return (
        re.sub(r"\s+", "", value)
        .replace("→", "-")
        .replace("P-", "-")
        .replace("HF", "HP")
    )


def main() -> int:
    root = Path(__file__).resolve().parent
    canonical = [
        line.strip()
        for line in (root / "equip_skill_names.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    canonical_by_normalized = {
        normalized(name): name for name in canonical
    }
    observations = json.loads(
        (root / "equip_ground_truth.json").read_text(encoding="utf-8")
    )
    votes: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    low_matches = []
    for observation in observations:
        source = normalized(observation["effect"])
        if source in canonical_by_normalized:
            target = canonical_by_normalized[source]
            score = 1.0
        else:
            target, score = max(
                (
                    (
                        name,
                        SequenceMatcher(
                            None, source, normalized(name)
                        ).ratio(),
                    )
                    for name in canonical
                ),
                key=lambda pair: pair[1],
            )
        raw = observation["bytes"]
        parameter = raw[2] if observation["index"] <= 46 else raw[4]
        votes[(raw[0], parameter)][target] += 1
        if score < 0.7:
            low_matches.append(
                {
                    "source": observation["effect"],
                    "target": target,
                    "score": round(score, 3),
                    "code": raw[0],
                    "parameter": parameter,
                }
            )

    mapping = {}
    conflicts = []
    for (code, parameter), counter in sorted(votes.items()):
        target, count = counter.most_common(1)[0]
        key = f"{code:02x}:{parameter:02x}"
        mapping[key] = target
        if len(counter) > 1:
            conflicts.append(
                {
                    "key": key,
                    "votes": dict(counter.most_common()),
                }
            )

    (root / "equip_effect_map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "equip_effect_map_audit.json").write_text(
        json.dumps(
            {
                "mapping_count": len(mapping),
                "conflicts": conflicts,
                "low_matches": low_matches,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"mapping={len(mapping)} conflicts={len(conflicts)} "
        f"low_matches={len(low_matches)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
