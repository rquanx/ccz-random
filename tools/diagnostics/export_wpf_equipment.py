"""Development-only export of equipment definitions and reference decoder results."""
import gzip
import hashlib
import json
from pathlib import Path

from ccz_randomizer import app
from ccz_randomizer.equipment_snapshot import serialize_equipment


def main():
    root = Path(__file__).resolve().parents[2]
    definitions = {name: getattr(app, name) for name in (
        'EQUIPMENT_NAMES', 'EQUIPMENT_CATEGORY_NAMES', 'EQUIPMENT_CATEGORY_BY_NAME',
        'EQUIPMENT_SETS', 'GOOD_EQUIPMENT_SKILL_MARKERS', 'ABILITY_MASK_NAMES',
        'STRATEGY_NAMES', 'FIXED_EQUIPMENT_EFFECTS', 'FORMATTED_EQUIPMENT_EFFECTS')}
    target = root / 'resources/data/equipment/definitions_2.2.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(definitions, ensure_ascii=False, indent=2), encoding='utf-8')
    # Unknown effects are expected for an exhaustive byte-domain comparison, not runtime faults.
    app.UNKNOWN_EQUIPMENT_EFFECTS.update((c, p) for c in range(256) for p in range(256))
    text = ''.join(f'{c}/{p}:{app.decode_equipment_effect(c, p)}\n' for c in range(256) for p in range(256))
    state = gzip.decompress((root / 'tests/fixtures/runtime_22/source-state.bin.gz').read_bytes())
    raw = state[app.EQUIPMENT_OFFSET:app.EQUIPMENT_OFFSET+app.EQUIPMENT_SIZE]
    records = tuple([raw[i*4:(i+1)*4] for i in range(46)] + [raw[184+i*8:184+(i+1)*8] for i in range(24)])
    items, effects = app.decode_equipment_records(records)
    expected = dict(decoderSha256=hashlib.sha256(text.encode()).hexdigest(),
                    source=serialize_equipment(items, app.build_equipment_specials(effects)))
    (root / 'tests/fixtures/runtime_22/equipment-reference.json').write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
