# Copyright (c) 2026, solvcon team <contact@solvcon.net>
# BSD 3-Clause License, see COPYING


import unittest

import numpy as np

from solvcon.pilot import _plot_core


class ExpandRangeTC(unittest.TestCase):
    def test_margins_widen_both_sides(self):
        lo, hi = _plot_core.expand_range(0.0, 10.0, 0.05)
        self.assertAlmostEqual(lo, -0.5)
        self.assertAlmostEqual(hi, 10.5)

    def test_negative_range(self):
        lo, hi = _plot_core.expand_range(-3.0, -1.0, 0.5)
        self.assertAlmostEqual(lo, -4.0)
        self.assertAlmostEqual(hi, 0.0)

    def test_zero_span_gets_a_drawable_range(self):
        # A constant series must still produce lo < hi.
        lo, hi = _plot_core.expand_range(0.0, 0.0, 0.05)
        self.assertLess(lo, hi)
        self.assertAlmostEqual(lo, -0.5)
        self.assertAlmostEqual(hi, 0.5)

    def test_zero_span_scales_with_magnitude(self):
        # At large magnitude the five-percent pad wins over half a unit.
        lo, hi = _plot_core.expand_range(1000.0, 1000.0, 0.05)
        self.assertAlmostEqual(lo, 950.0)
        self.assertAlmostEqual(hi, 1050.0)

    def test_non_finite_falls_back_to_unit(self):
        self.assertEqual(_plot_core.expand_range(np.nan, 1.0, 0.05),
                         (0.0, 1.0))
        self.assertEqual(_plot_core.expand_range(0.0, np.inf, 0.05),
                         (0.0, 1.0))


class PlotSeriesTC(unittest.TestCase):
    def test_data_becomes_flat_float(self):
        s = _plot_core.PlotSeries([[1, 2], [3, 4]], [[5, 6], [7, 8]])
        self.assertEqual(s.x.dtype, np.float64)
        self.assertEqual(s.x.ndim, 1)
        self.assertEqual(list(s.x), [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(list(s.y), [5.0, 6.0, 7.0, 8.0])

    def test_x_synthesized_when_none(self):
        s = _plot_core.PlotSeries(None, [5.0, 6.0, 7.0])
        self.assertEqual(list(s.x), [0.0, 1.0, 2.0])

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            _plot_core.PlotSeries([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_set_data_marks_dirty(self):
        s = _plot_core.PlotSeries([1.0], [2.0])
        s.dirty = False
        s.set_data([1.0, 2.0], [3.0, 4.0])
        self.assertTrue(s.dirty)

    def test_limits_span_the_data(self):
        s = _plot_core.PlotSeries([1.0, 5.0, 3.0], [-2.0, 4.0, 0.0])
        self.assertEqual(s.data_limits(), (1.0, 5.0, -2.0, 4.0))

    def test_limits_skip_nan_points(self):
        # The finite x of a NaN-y point must not leak into the limits.
        s = _plot_core.PlotSeries([1.0, 100.0, 3.0], [2.0, np.nan, 4.0])
        self.assertEqual(s.data_limits(), (1.0, 3.0, 2.0, 4.0))

    def test_limits_none_without_finite_data(self):
        self.assertIsNone(_plot_core.PlotSeries().data_limits())
        s = _plot_core.PlotSeries([np.nan], [np.nan])
        self.assertIsNone(s.data_limits())

    def test_single_point_limits(self):
        s = _plot_core.PlotSeries([2.0], [3.0])
        self.assertEqual(s.data_limits(), (2.0, 2.0, 3.0, 3.0))


class PlotModelTC(unittest.TestCase):
    def test_colors_cycle_in_add_order(self):
        model = _plot_core.PlotModel()
        cycle = _plot_core.PlotModel.COLOR_CYCLE
        added = [model.add_series(_plot_core.PlotSeries([0.0], [0.0]))
                 for _ in range(len(cycle) + 1)]
        self.assertEqual([s.color for s in added[:len(cycle)]],
                         list(cycle))
        self.assertEqual(added[len(cycle)].color, cycle[0])  # wraps

    def test_explicit_color_is_kept(self):
        model = _plot_core.PlotModel()
        s = model.add_series(
            _plot_core.PlotSeries([0.0], [0.0], color="#123456"))
        self.assertEqual(s.color, "#123456")
        # The cycle must not advance for a series that brought a color.
        t = model.add_series(_plot_core.PlotSeries([0.0], [0.0]))
        self.assertEqual(t.color, _plot_core.PlotModel.COLOR_CYCLE[0])

    def test_data_limits_union(self):
        model = _plot_core.PlotModel()
        model.add_series(_plot_core.PlotSeries([0.0, 1.0], [5.0, 6.0]))
        model.add_series(_plot_core.PlotSeries([-2.0, 0.5], [7.0, 8.0]))
        self.assertEqual(model.data_limits(), (-2.0, 1.0, 5.0, 8.0))

    def test_autoscale_adds_margins(self):
        model = _plot_core.PlotModel()
        model.add_series(
            _plot_core.PlotSeries([0.0, 10.0], [0.0, 100.0]))
        model.autoscale()
        self.assertAlmostEqual(model.xlim[0], -0.5)
        self.assertAlmostEqual(model.xlim[1], 10.5)
        self.assertAlmostEqual(model.ylim[0], -5.0)
        self.assertAlmostEqual(model.ylim[1], 105.0)

    def test_autoscale_without_data_gives_unit_view(self):
        model = _plot_core.PlotModel()
        model.xlim = (3.0, 4.0)
        model.autoscale()
        self.assertEqual(model.xlim, (0.0, 1.0))
        self.assertEqual(model.ylim, (0.0, 1.0))

    def test_autoscale_follows_new_data(self):
        model = _plot_core.PlotModel()
        s = model.add_series(_plot_core.PlotSeries([0.0, 1.0], [0.0, 1.0]))
        model.autoscale()
        first = model.xlim
        s.set_data([0.0, 100.0], [0.0, 1.0])
        model.autoscale()
        self.assertNotEqual(model.xlim, first)
        self.assertAlmostEqual(model.xlim[1], 105.0)


class AffineMapTC(unittest.TestCase):
    RECT = (10.0, 20.0, 100.0, 50.0)  # left, top, width, height

    def test_corners_map_to_rect(self):
        m = _plot_core.AffineMap((0.0, 4.0), (0.0, 2.0), self.RECT)
        px, py = m.map([0.0, 4.0], [0.0, 2.0])
        # Low data corner lands at the rect's bottom-left (y grows down).
        self.assertAlmostEqual(px[0], 10.0)
        self.assertAlmostEqual(py[0], 70.0)
        self.assertAlmostEqual(px[1], 110.0)
        self.assertAlmostEqual(py[1], 20.0)

    def test_y_is_flipped(self):
        m = _plot_core.AffineMap((0.0, 1.0), (0.0, 1.0), self.RECT)
        _, py = m.map([0.0, 0.0], [0.25, 0.75])
        self.assertGreater(py[0], py[1])  # larger y sits higher on screen

    def test_round_trip(self):
        m = _plot_core.AffineMap((-3.0, 7.0), (2.0, 9.0), self.RECT)
        x = np.linspace(-3.0, 7.0, 11)
        y = np.linspace(2.0, 9.0, 11)
        rx, ry = m.unmap(*m.map(x, y))
        np.testing.assert_allclose(rx, x, atol=1e-12)
        np.testing.assert_allclose(ry, y, atol=1e-12)

    def test_reversed_view_flips_direction(self):
        # A reversed x view (x0 > x1) must mirror the axis, not raise.
        m = _plot_core.AffineMap((4.0, 0.0), (0.0, 1.0), self.RECT)
        px, _ = m.map([0.0, 4.0], [0.0, 0.0])
        self.assertAlmostEqual(px[0], 110.0)
        self.assertAlmostEqual(px[1], 10.0)

    def test_singular_view_raises(self):
        with self.assertRaises(ValueError):
            _plot_core.AffineMap((1.0, 1.0), (0.0, 1.0), self.RECT)

    def test_pre_transform_seam(self):
        # A log10 pre-transform maps decades to equal pixel spans.
        m = _plot_core.AffineMap((1.0, 100.0), (0.0, 1.0), self.RECT,
                                 xpre=np.log10)
        px, _ = m.map([1.0, 10.0, 100.0], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(px[0], 10.0)
        self.assertAlmostEqual(px[1], 60.0)
        self.assertAlmostEqual(px[2], 110.0)
        with self.assertRaises(ValueError):
            m.unmap([0.0], [0.0])


class AxisTickerTC(unittest.TestCase):
    def setUp(self):
        self.ticker = _plot_core.AxisTicker(nbins=6)

    def test_simple_decade(self):
        ticks = self.ticker.ticks(0.0, 10.0)
        np.testing.assert_allclose(ticks, [0.0, 2.0, 4.0, 6.0, 8.0, 10.0])

    def test_offset_range(self):
        ticks = self.ticker.ticks(0.3, 9.7)
        np.testing.assert_allclose(ticks, [2.0, 4.0, 6.0, 8.0])

    def test_negative_and_zero(self):
        ticks = self.ticker.ticks(-1.0, 1.0)
        self.assertIn(0.0, list(ticks))
        self.assertTrue((np.diff(ticks) > 0).all())

    def test_reversed_range_gives_same_ticks(self):
        fwd = self.ticker.ticks(0.0, 10.0)
        rev = self.ticker.ticks(10.0, 0.0)
        np.testing.assert_allclose(fwd, rev)

    def test_tiny_magnitude(self):
        ticks = self.ticker.ticks(0.0, 1e-9)
        self.assertGreaterEqual(len(ticks), 4)
        self.assertLessEqual(len(ticks), 7)
        self.assertAlmostEqual(ticks[0], 0.0)

    def test_huge_magnitude(self):
        ticks = self.ticker.ticks(0.0, 1e9)
        self.assertGreaterEqual(len(ticks), 4)
        self.assertLessEqual(len(ticks), 7)

    def test_tick_count_stays_near_target(self):
        # Whatever the span, the count stays within a sane band.
        rng = np.random.default_rng(7)
        for _ in range(200):
            lo = rng.uniform(-1e6, 1e6)
            hi = lo + 10.0 ** rng.uniform(-6, 6)
            n = len(self.ticker.ticks(lo, hi))
            self.assertGreaterEqual(n, 3)
            self.assertLessEqual(n, 8)

    def test_degenerate_ranges_are_empty(self):
        self.assertEqual(len(self.ticker.ticks(1.0, 1.0)), 0)
        self.assertEqual(len(self.ticker.ticks(np.nan, 1.0)), 0)
        self.assertEqual(len(self.ticker.ticks(0.0, np.inf)), 0)

    def test_step_picks_the_staircase(self):
        self.assertAlmostEqual(self.ticker.step(0.0, 12.0), 2.0)
        self.assertAlmostEqual(self.ticker.step(0.0, 60.0), 10.0)
        self.assertAlmostEqual(self.ticker.step(0.0, 1.2), 0.2)
        self.assertAlmostEqual(self.ticker.step(0.0, 13.0), 2.5)

    def test_labels_are_clean(self):
        ticks = self.ticker.ticks(0.0, 1.0)
        self.assertEqual(self.ticker.labels(ticks),
                         ["0", "0.2", "0.4", "0.6", "0.8", "1"])

    def test_labels_have_no_negative_zero(self):
        labels = self.ticker.labels(np.array([-0.0, 0.0]))
        self.assertEqual(labels, ["0", "0"])


# vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
