# Copyright (c) 2026, solvcon team <contact@solvcon.net>
# BSD 3-Clause License, see COPYING


import os
import unittest

import numpy as np

import solvcon

try:
    from solvcon import pilot
    from solvcon import apputil
    from solvcon.pilot import _gui, _plot
    from solvcon.pilot._plot import PlotWidget, finite_runs
    from solvcon.pilot._plot_core import AffineMap
    from PySide6 import QtWidgets
except ImportError:
    pilot = None

GITHUB_ACTIONS = os.getenv('GITHUB_ACTIONS', False)


@unittest.skipUnless(solvcon.HAS_PILOT, "Qt pilot is not built")
class FiniteRunsTC(unittest.TestCase):
    def test_nan_breaks_the_line(self):
        x = np.arange(6.0)
        y = np.array([0.0, 1.0, np.nan, 3.0, 4.0, 5.0])
        runs = finite_runs(x, y)
        self.assertEqual(len(runs), 2)
        self.assertEqual(list(runs[0][0]), [0.0, 1.0])
        self.assertEqual(list(runs[1][0]), [3.0, 4.0, 5.0])

    def test_isolated_point_is_dropped(self):
        # A lone finite point cannot make a line segment.
        x = np.arange(3.0)
        y = np.array([np.nan, 1.0, np.nan])
        self.assertEqual(finite_runs(x, y), [])

    def test_all_finite_is_one_run(self):
        x = np.arange(4.0)
        runs = finite_runs(x, x ** 2)
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0][0]), 4)

    def test_empty_input(self):
        self.assertEqual(finite_runs(np.empty(0), np.empty(0)), [])


@unittest.skipIf(GITHUB_ACTIONS or not solvcon.HAS_PILOT,
                 "GUI is not available in GitHub Actions")
class PlotWidgetTC(unittest.TestCase):
    def setUp(self):
        self.mgr = pilot.RManager.instance.setUp()
        self.widget = PlotWidget()
        self.widget.resize(400, 300)

    def _amap(self):
        """The data-to-pixel map the widget paints with."""
        rect = self.widget.axes_rect()
        return AffineMap(
            self.widget.model.xlim, self.widget.model.ylim,
            (rect.left(), rect.top(), rect.width(), rect.height()))

    def test_axes_rect_sits_inside_the_widget(self):
        self.widget.add_series([0.0, 10.0], [0.0, 1.0])
        rect = self.widget.axes_rect()
        self.assertGreater(rect.left(), PlotWidget.PAD)  # label room
        self.assertAlmostEqual(rect.right(), 400 - PlotWidget.PAD)
        self.assertAlmostEqual(rect.top(), PlotWidget.PAD)
        self.assertLess(rect.bottom(), 300 - PlotWidget.PAD)

    def test_wide_labels_widen_the_left_margin(self):
        self.widget.add_series([0.0, 1.0], [0.0, 1.0])
        narrow = self.widget.axes_rect().left()
        self.widget.model.ylim = (2.7e8, 3.1e9)  # labels like 2.5e+09
        wide = self.widget.axes_rect().left()
        self.assertGreater(wide, narrow)

    def test_view_ticks_come_from_the_view(self):
        self.widget.add_series([0.0, 10.0], [0.0, 1.0])
        # Autoscale pads to (-0.5, 10.5); the nice ticks stay 0..10.
        xticks, _ = self.widget.view_ticks()
        self.assertEqual(list(xticks), [0.0, 2.0, 4.0, 6.0, 8.0, 10.0])

    def test_empty_widget_shows_placeholder(self):
        image = self.widget.grab().toImage()
        colors = {image.pixelColor(x, y).name()
                  for x in range(0, 400, 8) for y in range(0, 300, 8)}
        # The placeholder text puts non-white pixels on the canvas.
        self.assertIn("#ffffff", colors)
        self.assertGreater(len(colors), 1)

    def test_series_changes_the_render(self):
        before = self.widget.grab().toImage()
        self.widget.add_series([0.0, 1.0], [0.0, 1.0])
        after = self.widget.grab().toImage()
        self.assertNotEqual(before, after)

    def test_series_draws_in_its_color(self):
        self.widget.add_series(
            [0.0, 10.0], [2.0, 2.0], color="#ff0000", linewidth=3.0)
        self.widget.add_series(
            [0.0, 10.0], [4.0, 4.0], color="#0000ff", linewidth=3.0)
        image = self.widget.grab().toImage()
        amap = self._amap()
        px, py = amap.map([5.0, 5.0], [2.0, 4.0])
        red = image.pixelColor(round(px[0]), round(py[0]))
        blue = image.pixelColor(round(px[1]), round(py[1]))
        self.assertGreater(red.red(), 200)
        self.assertLess(red.blue(), 80)
        self.assertGreater(blue.blue(), 200)
        self.assertLess(blue.red(), 80)

    def test_nan_gap_leaves_background(self):
        # The middle segment is missing, so its midpoint keeps the
        # background while a finite segment's midpoint is stroked.
        y = np.array([2.0, 2.0, np.nan, 2.0])
        self.widget.add_series(
            [0.0, 4.0, 6.0, 10.0], y, color="#ff0000", linewidth=3.0)
        image = self.widget.grab().toImage()
        amap = self._amap()
        px, py = amap.map([2.0, 5.0], [2.0, 2.0])
        drawn = image.pixelColor(round(px[0]), round(py[0]))
        gap = image.pixelColor(round(px[1]), round(py[1]))
        self.assertGreater(drawn.red(), 200)
        self.assertLess(drawn.green(), 80)
        # The gap pixel may carry a gray grid line, so tell it from the
        # red stroke by the green channel instead of exact white.
        self.assertGreater(gap.green(), 200)

    def test_resize_recomputes_the_layout(self):
        self.widget.add_series([0.0, 1.0], [0.0, 1.0])
        first = self.widget.axes_rect()
        self.widget.resize(600, 400)
        second = self.widget.axes_rect()
        self.assertGreater(second.width(), first.width())
        self.assertGreater(second.height(), first.height())

    def test_paint_clears_the_dirty_flag(self):
        series = self.widget.add_series([0.0, 1.0], [0.0, 1.0])
        self.assertTrue(series.dirty)
        self.widget.grab()  # forces a paint pass
        self.assertFalse(series.dirty)


@unittest.skipIf(GITHUB_ACTIONS or not solvcon.HAS_PILOT,
                 "GUI is not available in GitHub Actions")
class PlotFeatureTC(unittest.TestCase):
    def setUp(self):
        self.mgr = pilot.RManager.instance.setUp()
        # Visibility tells live plot windows from closed ones, so the
        # manager must be shown and earlier tests' windows dropped.
        self.mgr.show()
        self.mgr.mdiArea.closeAllSubWindows()
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        self.mgr.mdiArea.closeAllSubWindows()
        QtWidgets.QApplication.processEvents()

    def _plot_subwins(self):
        return [s for s in self.mgr.mdiArea.subWindowList()
                if s.isVisible()
                and isinstance(s.widget(), _plot.PlotWidget)]

    def test_menu_action_opens_titled_window(self):
        feature = _plot.PlotFeature(mgr=self.mgr)
        feature.populate_menu()
        panel = self.mgr.menu_model.menu("Plot")
        self.assertIn(feature._action, panel.actions())
        feature._action.trigger()
        subs = self._plot_subwins()
        self.assertEqual(len(subs), 1)
        # The title makes the window listable from the Window menu.
        self.assertEqual(subs[0].windowTitle(), "XY plot")

    def test_console_plot_creates_a_window(self):
        handles, _ = apputil.build_pilot_namespace(self.mgr)
        series = handles['plot']([1.0, 2.0, 3.0])
        self.assertEqual(len(self._plot_subwins()), 1)
        self.assertEqual(series.color, "#1f77b4")  # C0
        self.assertEqual(list(series.x), [0.0, 1.0, 2.0])  # synthesized

    def test_console_plot_reuses_the_window(self):
        handles, _ = apputil.build_pilot_namespace(self.mgr)
        first = handles['plot']([1.0, 2.0, 3.0])
        second = handles['plot']([0.0, 1.0], [5.0, 6.0])
        subs = self._plot_subwins()
        self.assertEqual(len(subs), 1)
        model = subs[0].widget().model
        self.assertEqual(model.series, [first, second])
        # The palette cycles per window.
        self.assertEqual(second.color, "#ff7f0e")  # C1

    def test_console_plot_after_close_opens_anew(self):
        handles, _ = apputil.build_pilot_namespace(self.mgr)
        handles['plot']([1.0, 2.0, 3.0])
        self._plot_subwins()[0].close()
        QtWidgets.QApplication.processEvents()
        handles['plot']([4.0, 5.0])
        subs = self._plot_subwins()
        self.assertEqual(len(subs), 1)
        self.assertEqual(len(subs[0].widget().model.series), 1)

    def test_banner_lists_plot(self):
        _, entries = apputil.build_pilot_namespace(self.mgr)
        self.assertIn('plot(x, y)', [name for name, _ in entries])

    def test_controller_wires_the_feature(self):
        mgr = _gui.controller.build()
        self.assertIsNotNone(mgr.menu_model.action("plot.xy"))


# vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
