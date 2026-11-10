"""Read a supported game's title-state roster in an isolated copy, without saves."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from ccz_randomizer import app
from ccz_randomizer.entry_catalog import attach_fixed_entries
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.game_versions import activate_game_version
from ccz_randomizer.recruitment import parse_recruits
from ccz_randomizer.recruitment_catalog import attach_recruitment, load_catalog
from ccz_randomizer.runtime.game_sandbox import create_game_sandbox
from ccz_randomizer.runtime.personnel_memory import read_personnel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = args.game_dir.resolve()
    version = activate_game_version(source / 'Ekd5.exe')
    protected = [source / n for n in ('Ekd5.exe', 'Imsg.e5', 'RS/S_00.eex')]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    catalog = load_catalog(version=version)
    fixed = fixed_member_indices(version)
    with tempfile.TemporaryDirectory(prefix='ccz-version-probe-') as folder:
        sandbox = create_game_sandbox(source, root=Path(folder), save_names=())
        with app.HiddenGameSession(sandbox / 'Ekd5.exe', announce=False) as game:
            time.sleep(1)
            rows = read_personnel(game.pid, tuple(dict.fromkeys([
                *fixed.values(), *(p['recordIndex'] for p in catalog)])))
            payload = dict(schemaVersion=1, gameVersion=version, phase='title',
                           personnel=attach_recruitment(rows, catalog),
                           fixedPersonnel=attach_fixed_entries(rows, version=version))
            parse_recruits(dict(payload, personnel=payload['personnel']+payload['fixedPersonnel']))
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != digest for p, digest in before.items()):
        raise RuntimeError('探测期间源游戏文件发生变化')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"PASS: {version} 标题态读取 {len(catalog)} 名招募候选、{len(fixed)} 名剧情人物；未验证随机与存档")


if __name__ == '__main__':
    main()
