# Copyright (c) 2026, solvcon team <contact@solvcon.net>
# BSD 3-Clause License, see COPYING


"""Qt widget rendering the native xy plot with QPainter.

The model, geometry, and ticking live in _plot_core; this module only
turns them into pixels. There is no rasterizer of our own: QPainter
already strokes antialiased polylines.
"""

import numpy as np

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import _gui_common
from ._plot_core import AffineMap, AxisTicker, PlotModel, PlotSeries

__all__ = [  # noqa: F822
    'PlotWidget',
    'PlotFeature',
]


def finite_runs(x, y):
    """Split ``(x, y)`` into runs where both coordinates are finite.

    A NaN (or infinity) in either array breaks the line there, matching
    the matplotlib gap behavior.

    :param x: Abscissa array.
    :param y: Ordinate array.
    :return: List of ``(x, y)`` array pairs, each a drawable run of at
        least two points.
    :rtype: list
    """
    good = np.isfinite(np.asarray(x)) & np.isfinite(np.asarray(y))
    idx = np.nonzero(good)[0]
    if not idx.size:
        return []
    breaks = np.nonzero(np.diff(idx) > 1)[0] + 1
    return [(x[run], y[run]) for run in np.split(idx, breaks)
            if run.size >= 2]


class PlotWidget(QWidget):
    """A QPainter-drawn xy plot of the series held by a PlotModel.

    :ivar model: The plot document; mutate it and call ``update()``, or
        use :meth:`add_series` which does both.
    :vartype model: PlotModel
    """

    #: Pixels between the widget edge and the axes box (top and right).
    PAD = 12

    #: Length of a tick mark in pixels.
    TICK = 4

    #: Gap between a tick mark and its label in pixels.
    GAP = 4

    FRAME_COLOR = QColor("#444444")
    GRID_COLOR = QColor("#d9d9d9")
    TEXT_COLOR = QColor("#222222")

    #: Zoom factor per wheel notch; forward shrinks the view around the
    #: cursor by this much.
    ZOOM = 0.8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = PlotModel()
        self.ticker = AxisTicker()
        self._drag = None
        self.setMinimumSize(120, 90)
        # The plot area is opaque white like a figure, not widget gray.
        self.setAutoFillBackground(False)

    def add_series(self, x, y, **kw):
        """Create a series, add it to the model, autoscale, and repaint.

        :param x: Abscissa values, or None to synthesize an index.
        :param y: Ordinate values.
        :param kw: Forwarded to :class:`PlotSeries` (label, color,
            linewidth).
        :return: The new series.
        :rtype: PlotSeries
        """
        series = self.model.add_series(PlotSeries(x, y, **kw))
        self.model.autoscale()
        self.update()
        return series

    def view_ticks(self):
        """The tick positions for the current view, per axis.

        :return: ``(xticks, yticks)`` arrays.
        :rtype: tuple
        """
        return (self.ticker.ticks(*self.model.xlim),
                self.ticker.ticks(*self.model.ylim))

    def data_map(self):
        """The data-to-pixel map for the current view and size.

        :rtype: AffineMap
        """
        rect = self.axes_rect()
        return AffineMap(
            self.model.xlim, self.model.ylim,
            (rect.left(), rect.top(), rect.width(), rect.height()))

    def wheelEvent(self, event):
        """Zoom about the cursor; the data under it stays put."""
        notches = event.angleDelta().y() / 120.0
        if notches == 0.0:
            return
        factor = self.ZOOM ** notches
        pos = event.position()
        ax, ay = self.data_map().unmap(pos.x(), pos.y())
        ax, ay = float(ax), float(ay)
        x0, x1 = self.model.xlim
        y0, y1 = self.model.ylim
        self.model.xlim = (ax + (x0 - ax) * factor,
                           ax + (x1 - ax) * factor)
        self.model.ylim = (ay + (y0 - ay) * factor,
                           ay + (y1 - ay) * factor)
        self._pin(pos, ax, ay)
        self.update()

    def _pin(self, pos, ax, ay):
        """Put the data point ``(ax, ay)`` back under ``pos``.

        The label gutter follows the view, so a zoom can re-lay the
        axes rectangle out and shift what sits under the cursor; one
        linear correction in the new layout pins the anchor again.
        """
        px, py = self.data_map().unmap(pos.x(), pos.y())
        dx = float(px) - ax
        dy = float(py) - ay
        x0, x1 = self.model.xlim
        y0, y1 = self.model.ylim
        self.model.xlim = (x0 - dx, x1 - dx)
        self.model.ylim = (y0 - dy, y1 - dy)

    def mousePressEvent(self, event):
        """Start a pan drag; the view limits follow the pointer."""
        if event.button() == Qt.LeftButton:
            self._drag = (event.position(),
                          self.model.xlim, self.model.ylim,
                          self.data_map())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Pan by the dragged distance, in data units."""
        if self._drag is None:
            super().mouseMoveEvent(event)
            return
        start, (x0, x1), (y0, y1), amap = self._drag
        delta = event.position() - start
        # The map is linear, so a pixel delta converts through the
        # scale alone; the y sign rides in the (negative) y scale.
        dx = delta.x() / amap.x_scale
        dy = delta.y() / amap.y_scale
        self.model.xlim = (x0 - dx, x1 - dx)
        self.model.ylim = (y0 - dy, y1 - dy)
        self.update()

    def mouseReleaseEvent(self, event):
        """End the pan drag."""
        if event.button() == Qt.LeftButton:
            self._drag = None
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Restore the autoscaled view."""
        if event.button() == Qt.LeftButton:
            self.model.autoscale()
            self.update()
        else:
            super().mouseDoubleClickEvent(event)

    def axes_rect(self):
        """The axes rectangle for the current size, as a QRectF.

        The left and bottom margins make room for the tick labels of the
        current view, measured with the widget font.

        :rtype: QRectF
        """
        fm = QFontMetricsF(self.font())
        xticks, yticks = self.view_ticks()
        ylabels = self.ticker.labels(yticks)
        ywidth = max([fm.horizontalAdvance(lab) for lab in ylabels],
                     default=fm.horizontalAdvance("0"))
        left = self.PAD + ywidth + self.GAP + self.TICK
        bottom = self.PAD + fm.height() + self.GAP + self.TICK
        rect = QRectF(left, self.PAD,
                      self.width() - left - self.PAD,
                      self.height() - bottom - self.PAD)
        return rect

    def paintEvent(self, _event):
        """Draw the frame, grid, ticks, labels, and every series."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.white)
        if self.model.data_limits() is None:
            self._draw_placeholder(painter)
            painter.end()
            return
        rect = self.axes_rect()
        if rect.width() < 10 or rect.height() < 10:
            painter.end()
            return
        amap = AffineMap(
            self.model.xlim, self.model.ylim,
            (rect.left(), rect.top(), rect.width(), rect.height()))
        self._draw_grid_and_ticks(painter, rect, amap)
        self._draw_series(painter, rect, amap)
        painter.setPen(QPen(self.FRAME_COLOR, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        painter.end()

    def _draw_placeholder(self, painter):
        """Tell an empty plot apart from a broken one."""
        painter.setPen(QPen(QColor("#888888")))
        painter.drawText(self.rect(), Qt.AlignCenter, "No data")

    def _draw_grid_and_ticks(self, painter, rect, amap):
        """Grid lines across the axes box, tick marks, and labels."""
        fm = QFontMetricsF(self.font())
        xticks, yticks = self.view_ticks()
        grid_pen = QPen(self.GRID_COLOR, 1.0)
        frame_pen = QPen(self.FRAME_COLOR, 1.0)
        text_pen = QPen(self.TEXT_COLOR)
        px, _ = amap.map(xticks, np.zeros_like(xticks))
        for tick, x in zip(xticks, px):
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(x, rect.top()),
                             QPointF(x, rect.bottom()))
            painter.setPen(frame_pen)
            painter.drawLine(QPointF(x, rect.bottom()),
                             QPointF(x, rect.bottom() + self.TICK))
            painter.setPen(text_pen)
            lab = self.ticker.labels([tick])[0]
            width = fm.horizontalAdvance(lab)
            painter.drawText(
                QPointF(x - width / 2.0,
                        rect.bottom() + self.TICK + self.GAP
                        + fm.ascent()),
                lab)
        _, py = amap.map(np.zeros_like(yticks), yticks)
        for tick, y in zip(yticks, py):
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(rect.left(), y),
                             QPointF(rect.right(), y))
            painter.setPen(frame_pen)
            painter.drawLine(QPointF(rect.left() - self.TICK, y),
                             QPointF(rect.left(), y))
            painter.setPen(text_pen)
            lab = self.ticker.labels([tick])[0]
            width = fm.horizontalAdvance(lab)
            painter.drawText(
                QPointF(rect.left() - self.TICK - self.GAP - width,
                        y + fm.ascent() / 2.0 - 1.0),
                lab)

    def _draw_series(self, painter, rect, amap):
        """Every series as antialiased polylines clipped to the box."""
        painter.save()
        painter.setClipRect(rect)
        for series in self.model.series:
            px, py = amap.map(series.x, series.y)
            pen = QPen(QColor(series.color), series.linewidth)
            painter.setPen(pen)
            for rx, ry in finite_runs(px, py):
                points = [QPointF(x, y) for x, y in zip(rx, ry)]
                painter.drawPolyline(QPolygonF(points))
            series.dirty = False
        painter.restore()


def open_plot_window(mgr):
    """Open a new xy-plot sub-window on ``mgr`` and return its widget.

    The sub-window carries a title so the Window menu can list it.

    :param mgr: The pilot manager (RManager).
    :return: The hosted plot widget.
    :rtype: PlotWidget
    """
    widget = PlotWidget()
    # Two steps like the 1D apps: addSubWindow crosses the pybind11
    # boundary, which loses the ownership transfer and lets Python
    # garbage-collect the widget; setWidget through PySide records it.
    subwin = mgr.addSubWindow(QWidget())
    subwin.setWidget(widget)
    subwin.setWindowTitle("XY plot")
    subwin.show()
    return widget


def find_plot_widget(mgr):
    """The plot widget the console should target, or None.

    Prefer the active sub-window when it hosts a plot; otherwise fall
    back to the most recently added visible plot window. Closed viewers
    linger hidden in the MDI list, so visibility tells them apart.

    :param mgr: The pilot manager (RManager).
    :rtype: PlotWidget or None
    """
    mdi = mgr.mdiArea
    active = mdi.activeSubWindow()
    if active is not None and isinstance(active.widget(), PlotWidget):
        return active.widget()
    for subwin in reversed(mdi.subWindowList()):
        if subwin.isVisible() and isinstance(subwin.widget(), PlotWidget):
            return subwin.widget()
    return None


def console_plot(mgr, x, y=None, **kw):
    """Plot arrays in the current plot window, creating one if needed.

    Mirrors the matplotlib call shapes: ``plot(y)`` synthesizes the
    abscissa, ``plot(x, y)`` uses both.

    :param mgr: The pilot manager (RManager).
    :param x: Abscissa values, or the ordinate when ``y`` is None.
    :param y: Ordinate values.
    :param kw: Forwarded to :class:`PlotSeries` (label, color,
        linewidth).
    :return: The new series.
    :rtype: PlotSeries
    """
    if y is None:
        x, y = None, x
    widget = find_plot_widget(mgr)
    if widget is None:
        widget = open_plot_window(mgr)
    return widget.add_series(x, y, **kw)


class PlotFeature(_gui_common.PilotFeature):
    """Menu entry that opens xy-plot sub-windows.

    Each activation opens a fresh plot window; the console ``plot``
    function reuses the current one instead.
    """

    def populate_menu(self):
        self._action = self.add_action(
            "Plot", "XY plot", "Open an xy plot window",
            self._on_open, id="plot.xy", weight=10)

    def _on_open(self):
        open_plot_window(self._mgr)

# vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
