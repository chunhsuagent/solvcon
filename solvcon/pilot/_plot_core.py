# Copyright (c) 2026, solvcon team <contact@solvcon.net>
# BSD 3-Clause License, see COPYING


"""Data model, geometry, and ticking for the native xy plot.

Pure Python on top of numpy: nothing here imports Qt, so the whole model
is testable without a display. The Qt half (widget and pilot feature)
lives in _plot.py.
"""

import numpy as np

__all__ = [  # noqa: F822
    'PlotSeries',
    'PlotModel',
    'AffineMap',
    'AxisTicker',
    'expand_range',
]


def expand_range(lo, hi, margin):
    """Return ``(lo, hi)`` widened by ``margin`` per side, nonsingular.

    A zero span expands by five percent of the magnitude or half a unit,
    whichever is larger, so a constant series still gets a drawable
    range. A non-finite input falls back to the unit range.

    :param lo: Low end of the raw range.
    :type lo: float
    :param hi: High end of the raw range.
    :type hi: float
    :param margin: Fraction of the span padded on each side.
    :type margin: float
    :return: The widened range.
    :rtype: tuple(float, float)
    """
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return 0.0, 1.0
    span = hi - lo
    if span == 0.0:
        pad = max(abs(lo) * margin, 0.5)
    else:
        pad = span * margin
    return lo - pad, hi + pad


class PlotSeries:
    """One xy data series with its display style.

    :ivar label: Legend label of the series.
    :vartype label: str
    :ivar color: RGB hex string like "#1f77b4"; the model assigns one
        from its color cycle when left None.
    :vartype color: str or None
    :ivar linewidth: Stroke width in device pixels.
    :vartype linewidth: float
    :ivar dirty: Set by :meth:`set_data`; the widget clears it once a
        repaint has picked the new data up.
    :vartype dirty: bool
    """

    def __init__(self, x=None, y=None, label="", color=None,
                 linewidth=1.5):
        self.label = label
        self.color = color
        self.linewidth = linewidth
        self.dirty = True
        self._x = np.empty(0, dtype=float)
        self._y = np.empty(0, dtype=float)
        if y is not None:
            self.set_data(x, y)

    @property
    def x(self):
        """The abscissa array (flat float; NaN allowed)."""
        return self._x

    @property
    def y(self):
        """The ordinate array (flat float; NaN marks a line gap)."""
        return self._y

    def set_data(self, x, y):
        """Store ``x`` and ``y`` as flat float arrays and mark dirty.

        :param x: Abscissa values; when None, ``arange(len(y))`` is
            synthesized.
        :type x: array-like or None
        :param y: Ordinate values.
        :type y: array-like
        :raises ValueError: When the lengths differ.
        """
        y = np.asarray(y, dtype=float).ravel()
        if x is None:
            x = np.arange(len(y), dtype=float)
        else:
            x = np.asarray(x, dtype=float).ravel()
        if len(x) != len(y):
            raise ValueError(
                "x and y must have the same length: %d != %d"
                % (len(x), len(y)))
        self._x = x
        self._y = y
        self.dirty = True

    def data_limits(self):
        """Return ``(xmin, xmax, ymin, ymax)`` over the finite points.

        A point counts only when both coordinates are finite, so a NaN
        gap cannot leak its finite partner into the limits.

        :return: The bounding box, or None when nothing is finite.
        :rtype: tuple or None
        """
        good = np.isfinite(self._x) & np.isfinite(self._y)
        if not good.any():
            return None
        x = self._x[good]
        y = self._y[good]
        return (float(x.min()), float(x.max()),
                float(y.min()), float(y.max()))


class PlotModel:
    """The plot document: series plus the view rectangle in data space.

    Interaction mutates only :attr:`xlim` and :attr:`ylim`; autoscale
    recomputes them from the data limits with a margin, following the
    matplotlib behavior in a reduced form.

    :ivar series: The plotted series, in add order.
    :vartype series: list[PlotSeries]
    :ivar xlim: View range ``(x0, x1)`` in data coordinates.
    :vartype xlim: tuple(float, float)
    :ivar ylim: View range ``(y0, y1)`` in data coordinates.
    :vartype ylim: tuple(float, float)
    """

    #: Fraction of the data span padded on each side by autoscale.
    MARGIN = 0.05

    #: The matplotlib default palette (C0 to C9).
    COLOR_CYCLE = (
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    )

    def __init__(self):
        self.series = []
        self._cycle = 0
        self.xlim = (0.0, 1.0)
        self.ylim = (0.0, 1.0)

    def add_series(self, series):
        """Register ``series``, assigning the next cycle color if unset.

        :param series: The series to add.
        :type series: PlotSeries
        :return: The same series, for chaining.
        :rtype: PlotSeries
        """
        if series.color is None:
            series.color = self.COLOR_CYCLE[
                self._cycle % len(self.COLOR_CYCLE)]
            self._cycle += 1
        self.series.append(series)
        return series

    def data_limits(self):
        """Union of every series' limits, or None without finite data.

        :rtype: tuple or None
        """
        boxes = [s.data_limits() for s in self.series]
        boxes = [b for b in boxes if b is not None]
        if not boxes:
            return None
        arr = np.array(boxes)
        return (float(arr[:, 0].min()), float(arr[:, 1].max()),
                float(arr[:, 2].min()), float(arr[:, 3].max()))

    def autoscale(self):
        """Fit the view to the data with a margin on each side.

        Without finite data the view falls back to the unit square.
        """
        box = self.data_limits()
        if box is None:
            self.xlim = (0.0, 1.0)
            self.ylim = (0.0, 1.0)
            return
        self.xlim = expand_range(box[0], box[1], self.MARGIN)
        self.ylim = expand_range(box[2], box[3], self.MARGIN)


class AffineMap:
    """Per-axis linear map from data coordinates to pixel coordinates.

    Composes "view range to unit interval" and "unit interval to pixel
    rectangle" into one scale and offset per axis, with y flipped for
    Qt's top-left origin. An optional pre-transform per axis is applied
    to the data first; that is the seam a log scale would plug into, and
    the identity default keeps the linear case one multiply-add.
    """

    def __init__(self, xlim, ylim, rect, xpre=None, ypre=None):
        """
        :param xlim: View range ``(x0, x1)`` in data coordinates.
        :type xlim: tuple(float, float)
        :param ylim: View range ``(y0, y1)``.
        :type ylim: tuple(float, float)
        :param rect: Pixel rectangle ``(left, top, width, height)`` with
            y growing downward.
        :type rect: tuple
        :param xpre: Optional callable applied to x data and the x view
            range before the linear map.
        :param ypre: Likewise for y.
        :raises ValueError: When a (pre-transformed) view range is
            singular.
        """
        left, top, width, height = (float(v) for v in rect)
        self._xpre = xpre
        self._ypre = ypre
        x0, x1 = xlim if xpre is None else (xpre(xlim[0]), xpre(xlim[1]))
        y0, y1 = ylim if ypre is None else (ypre(ylim[0]), ypre(ylim[1]))
        if x1 == x0 or y1 == y0:
            raise ValueError("view range is singular")
        self._ax = width / (x1 - x0)
        self._bx = left - x0 * self._ax
        # y flipped: the low view edge lands at the rectangle bottom.
        self._ay = -height / (y1 - y0)
        self._by = top + height - y0 * self._ay

    @property
    def x_scale(self):
        """Pixels per (pre-transformed) data unit along x."""
        return self._ax

    @property
    def y_scale(self):
        """Pixels per data unit along y; negative from the flip."""
        return self._ay

    def map(self, x, y):
        """Map data coordinates to pixel coordinates.

        :param x: Abscissa values (scalar or array).
        :param y: Ordinate values.
        :return: ``(px, py)`` float arrays.
        :rtype: tuple
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if self._xpre is not None:
            x = self._xpre(x)
        if self._ypre is not None:
            y = self._ypre(y)
        return self._ax * x + self._bx, self._ay * y + self._by

    def unmap(self, px, py):
        """Map pixel coordinates back to data coordinates.

        Only the linear case inverts here; inverting a pre-transform is
        the job of the scale that installed it.

        :raises ValueError: When a pre-transform is set.
        """
        if self._xpre is not None or self._ypre is not None:
            raise ValueError("unmap requires linear axes")
        px = np.asarray(px, dtype=float)
        py = np.asarray(py, dtype=float)
        return (px - self._bx) / self._ax, (py - self._by) / self._ay


class AxisTicker:
    """Nice-number tick locator and formatter.

    Follows matplotlib's MaxNLocator in a reduced form: candidate steps
    are the 1, 2, 2.5, 5, 10 staircase scaled to the decade of the raw
    step, and the ticks are the integer multiples of the chosen step
    inside the view range.
    """

    STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)

    def __init__(self, nbins=6):
        """
        :param nbins: Target upper bound on the number of intervals.
        :type nbins: int
        """
        self.nbins = nbins

    def step(self, vmin, vmax):
        """The nice step: the smallest candidate at least the raw step.

        :rtype: float
        """
        raw = abs(vmax - vmin) / self.nbins
        mag = 10.0 ** np.floor(np.log10(raw))
        for s in self.STEPS:
            step = s * mag
            # The tolerance keeps an exact multiple (raw == 2*mag) from
            # being skipped over by float rounding.
            if step >= raw * (1.0 - 1e-12):
                return step
        return 10.0 * mag

    def ticks(self, vmin, vmax):
        """Tick positions inside ``[vmin, vmax]``, given in either order.

        Positions are computed as integer multiples of the step, not by
        accumulation, so they carry no cumulative float drift. A
        degenerate or non-finite range gives an empty array.

        :rtype: numpy.ndarray
        """
        if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmin == vmax:
            return np.empty(0, dtype=float)
        lo, hi = (vmin, vmax) if vmin < vmax else (vmax, vmin)
        step = self.step(lo, hi)
        first = np.ceil(lo / step - 1e-9)
        last = np.floor(hi / step + 1e-9)
        return np.arange(first, last + 1.0) * step

    def labels(self, ticks):
        """Plain ``%g`` labels for ``ticks``.

        The ticks are nice multiples already, so ``%g`` renders them
        cleanly; adding positive zero first keeps ``-0`` out.

        :rtype: list[str]
        """
        return ["%g" % (t + 0.0) for t in ticks]

# vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
