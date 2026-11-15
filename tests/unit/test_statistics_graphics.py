import unittest

from ccz_randomizer.ui.statistics_graphics import ChartGraphics


class StatisticsGraphicsTests(unittest.TestCase):
    def test_ring_keeps_correct_segment_orientation_and_smooth_edges(self):
        graphics = ChartGraphics(100, 100)
        region = graphics.arc(10, 10, 90, 90, start=90, extent=90, fill="#5B8DEF")
        graphics.oval(21.2, 21.2, 78.8, 78.8, fill="white")
        image = graphics.render()
        self.assertEqual((100, 100), image.size)
        self.assertEqual((255, 255, 255), image.getpixel((50, 50)))
        self.assertEqual((255, 255, 255), image.getpixel((76, 24)))
        blue = image.getpixel((24, 24))
        self.assertGreater(blue[2], blue[0])
        # Curved boundaries need partial pixel coverage, not only solid colors.
        self.assertGreater(len(image.getcolors(10000)), 10)
        self.assertTrue(region.contains(24, 24))
        self.assertFalse(region.contains(50, 50))
        self.assertFalse(region.contains(76, 24))
        self.assertFalse(region.contains(10, 10))

    def test_rounded_bars_and_diagonal_lines_have_smoothed_edges(self):
        graphics = ChartGraphics(120, 80)
        bar = graphics.rectangle(10, 10, 100, 24, fill="#50B8A9")
        graphics.line(10, 70, 100, 35, fill="#5B8DEF", width=2)
        graphics.oval(96, 31, 104, 39, fill="#5B8DEF", outline="white")
        image = graphics.render()
        self.assertEqual((80, 184, 169), image.getpixel((50, 16)))
        self.assertTrue(bar.contains(50, 16))
        self.assertFalse(bar.contains(50, 30))
        colors = image.crop((8, 30, 107, 77)).getcolors(10000)
        self.assertGreater(len(colors), 10)

    def test_full_circle_and_zero_size_bar_render_without_seam_or_failure(self):
        graphics = ChartGraphics(80, 80)
        graphics.arc(10, 10, 70, 70, start=90, extent=360, fill="#50B8A9", outline="")
        graphics.rectangle(20, 20, 20, 40, fill="#5B8DEF")
        image = graphics.render()
        self.assertEqual((80, 184, 169), image.getpixel((40, 20)))


if __name__ == "__main__":
    unittest.main()
