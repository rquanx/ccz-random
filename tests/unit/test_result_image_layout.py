import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw

from ccz_randomizer.app import JOB_MAP, result_font
from ccz_randomizer.ui.result_image import report_members, render_result_image, pack_member_columns
from ccz_randomizer.ui.result_grid import compose_result_panels

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/personnel_22'


def recorded_runner(count):
    people = json.loads((FIXTURES / 'randomized-personnel.json').read_text(encoding='utf-8'))
    people += json.loads((FIXTURES / 'randomized-fixed-personnel.json').read_text(encoding='utf-8'))
    members = []
    for row in people[:count]:
        skills = [SimpleNamespace(name=name, memory_category=category)
                  for category, key in [('personal', 'personalTalents'), ('job', 'jobTalents')]
                  for name in row[key]]
        members.append(SimpleNamespace(name=row['name'], job=SimpleNamespace(name=JOB_MAP[row['jobId']][0]), skillList=skills))
    # The legacy initial team must not leak into a selection containing Zhang Bao only.
    return SimpleNamespace(_scored_members=members, _team_members=[SimpleNamespace(name='曹操')], _equip_specials=())


class ResultImageLayoutTests(unittest.TestCase):
    def test_single_selected_recruit_uses_own_job_and_all_talents(self):
        runner = recorded_runner(1)
        rows = report_members(runner)
        self.assertEqual(['张宝'], [row['name'] for row in rows])
        self.assertEqual(['攻击追加 诱惑'], rows[0]['personal'])
        self.assertEqual(['附加伤害 爆发 12%'], rows[0]['jobSkills'])
        image = render_result_image(runner, [], 1, result_font=result_font)
        self.addCleanup(image.close)
        self.assertEqual((740, 1028), image.size)

    def test_eighth_member_opens_another_column_and_full_roster_is_drawn(self):
        for count in (8, 130):
            with self.subTest(count=count):
                runner = recorded_runner(count)
                texts = []
                original = ImageDraw.ImageDraw.text
                def record(draw, xy, text, *args, **kwargs):
                    texts.append(text)
                    return original(draw, xy, text, *args, **kwargs)
                with patch.object(ImageDraw.ImageDraw, 'text', record):
                    image = render_result_image(runner, [], 15, result_font=result_font)
                try:
                    self.assertGreater(image.width, 740)
                    for person in runner._scored_members:
                        self.assertTrue(any(person.name + ' · ' in text for text in texts), person.name)
                    self.assertNotIn('人物信息', texts)
                    self.assertEqual(count, sum(' · ' in text for text in texts))
                    # Last character column has visible rendered glyphs too.
                    x = image.width - 202 - 406 - 132
                    crop = image.crop((x + 4, 25, x + 128, 150))
                    self.assertGreater(len(crop.getcolors(100000)), 1)
                finally:
                    image.close()

    def test_column_packing_keeps_each_complete_member_and_order(self):
        blocks = [(row['name'], [], 130) for row in report_members(recorded_runner(130))]
        columns = pack_member_columns(blocks, 984)
        self.assertEqual(19, len(columns))
        self.assertEqual(blocks, [block for column in columns for block in column])
        self.assertTrue(all(sum(block[2] for block in column) <= 984 for column in columns))

    def test_grid_keeps_actual_panel_pixels_without_resizing(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            paths = {}
            for slot, width, color in ((1, 872, 'red'), (2, 740, 'blue')):
                panel = Image.new('RGB', (width, 1028), color)
                panel.putpixel((width - 1, 1000), (1, 2, 3))
                paths[slot] = folder / f'{slot}.png'
                panel.save(paths[slot]); panel.close()
            output = folder / 'grid.png'
            compose_result_panels(paths, output)
            with Image.open(output) as grid:
                self.assertEqual((1, 2, 3), grid.getpixel((871, 1000)))
                self.assertEqual((1, 2, 3), grid.getpixel((872 + 739, 1000)))
                self.assertEqual((0, 0, 255), grid.getpixel((872, 0)))
