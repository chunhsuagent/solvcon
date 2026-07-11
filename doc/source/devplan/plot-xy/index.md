# Native xy plot

Give the pilot a native `plot(x, y)`: a reusable QPainter-drawn xy-plot
window that any feature or the embedded console can open, so plotting an
array no longer means reaching into the one-dimensional solver
applications and no longer pulls matplotlib into the GUI.

## Goal

1. **A reusable plot window.** A QPainter-rendered widget, hosted in an
   MDI sub-window with a title the Window menu can list, that draws any
   number of xy series and is independent of the solver applications and
   of matplotlib.
2. **Plotting from the console.** `plot(x, y)` in the embedded Python
   console adds a series to the plot window under focus, or opens one
   when none exists. The pilot ships a console dock so the GUI can be
   scripted; plotting an array should be part of that.
3. **A display-free, testable core.** The data model, the data-to-pixel
   geometry, and the tick placement are pure Python with no Qt import, so
   limits, the affine map, and the locator are unit-tested with no
   display at all.
4. **No matplotlib in the plot path.** QPainter already rasterizes
   antialiased, dashed, joined polylines, so the plot window carries no
   rasterizer and no matplotlib dependency of its own.

The planned steps come right below. Every section after them exists to
support the steps: what the pilot has today and the gaps that remain, the
matplotlib study the design borrows from, the design the steps build, and
how the result is tested.

## Planned steps

Each step is one pull request against the `feat/plot_xy` integration
branch: one concern, lint-clean, independently reviewable, and leaving
the full pilot suite green. Diffs stay within roughly 300 to 600 lines
(the size the user set for this feature). Later steps build strictly on
earlier ones, so review order equals merge order, and this plan lands
first as its own pull request. The vocabulary used here (`PlotSeries`,
`PlotModel`, `AffineMap`, `AxisTicker`, `PlotWidget`) is defined in
"Target design"; the evidence for each step is in "What the pilot has
today".

1. **Step 1. The plot core.** Add `solvcon/pilot/_plot_core.py` with
   `PlotSeries`, `PlotModel`, `AffineMap`, and `AxisTicker`, and its unit
   tests. Pure Python, no Qt, so the tests need no display. This is the
   load-bearing step; every later step is small because it exists.
2. **Step 2. The widget.** Add `solvcon/pilot/_plot.py` with `PlotWidget`
   rendering the model with QPainter, and its GUI tests. No feature
   wiring yet; the widget is exercised in isolation under a virtual
   display.
3. **Step 3. Pilot integration.** Add `PlotFeature` and the console
   entry: the "Plot / XY plot" menu action, `console_plot` wired through
   `solvcon/apputil.py`, and the controller wiring in
   `solvcon/pilot/_gui.py`.
4. **Step 4. Mouse interaction.** Wheel zoom about the cursor, drag pan,
   and double-click autoscale on `PlotWidget`, plus the per-axis scale
   accessors the pan needs; each only rewrites the view limits.
5. **Follow-up A. Format strings and markers.** The matplotlib-style
   subset (colors `rgbcmykw`; line styles `-`, `--`, `:`, `-.`; markers
   `o`, `s`, `+`, `x`), marker stamping at data points, and the `fmt`
   argument of the console `plot`.
6. **Follow-up B. Legend.** A simple legend box, one row per series with
   a line-and-marker swatch, toggled on and off.

Steps 1 and 2 are the load-bearing ones; steps 3 and 4 are small because
they exist. The two follow-ups ride after the train so no single review
in the train inflates.

## What the pilot has today

This section records the machinery the steps build on and the gaps that
remain; each gap names the step that fills it.

The pilot cannot plot an array. The only data plotting in the code base
is matplotlib embedded inside the one-dimensional solver applications.
`OneDimBaseApp.run` builds a `PlotArea` inside an MDI sub-window
(`solvcon/pilot/_base_app.py`), and `PlotArea` is a
`backend_qtagg.FigureCanvas`:

```python
self._subwin = self._mgr.addSubWindow(QWidget())
self._subwin.setWidget(PlotArea(self))
```

That plotting is welded to the solver apps: it is created only by
`OneDimBaseApp`, it reads the solver's `plot_data`, and nothing else can
reuse it. The dependency also pulls the whole matplotlib and Agg stack
into the GUI process for what is, on screen, a set of antialiased
polylines.

The seams a native plot needs are already in place. Features derive from
`PilotFeature` (`solvcon/pilot/_gui_common.py`) and place actions on the
bar with `menu_model` and `add_action`. Sub-windows come from
`RManager.addSubWindow`, and the Window menu lists them by their
`windowTitle` (`solvcon/pilot/_window_manager.py`), so a plot window must
set one. The embedded console's namespace is curated in
`build_pilot_namespace` (`solvcon/apputil.py`), which is where a `plot`
handle belongs, next to `show_mesh` and `viewers`. And the precedent for
painting straight onto a widget already exists in C++: `R2DWidget`
(`cpp/solvcon/pilot/R2DWidget.*`) draws the 2D world with QPainter, so a
QPainter-drawn plot is an established style here, not a new one.

### Gaps

- **No reusable plotting** (steps 1 to 3). Plotting exists only as
  matplotlib bound to `OneDimBaseApp`; there is no widget or model a
  second caller can open. Steps 1 and 2 build the model and the widget,
  step 3 exposes them.
- **The console cannot plot arrays** (step 3). `build_pilot_namespace`
  seeds `mgr`, `show_mesh`, `viewers`, and more, but nothing to plot two
  arrays. Step 3 adds the `plot` handle.
- **matplotlib is a GUI dependency** (whole train). It is imported for
  on-screen polylines that QPainter draws natively; once the widget
  exists the plot path needs none of it. (Migrating the 1D apps off
  matplotlib is a later plan, listed under "Out of scope".)
- **Handing a Python widget to `addSubWindow` loses it** (step 3).
  `RManager::addSubWindow` crosses the pybind11 boundary, which does not
  carry the parent-ownership transfer, so a widget created in Python and
  passed straight in is garbage-collected out of the live window. The 1D
  apps already dodge this with the two-step
  `addSubWindow(QWidget())` then `setWidget(...)`; step 3's
  `open_plot_window` does the same and records why.

## Reference study: matplotlib

The design borrows from a source study of matplotlib v3.10.8, the locally
installed version, read top to bottom for how `plot(x, y)` becomes
pixels. Its stack has six layers: the pyplot state machine; the artist
tree with lazy dirty-flag storage; the geometry core, where a `Path` of
vertices plus codes is mapped by a transform tree whose
`transData = transScale + (transLimits + transAxes)` collapses to one
affine matrix for linear axes; a renderer abstraction whose only
essential primitive is `draw_path`; the Agg C++ rasterizer; and the Qt
shell that blits Agg's RGBA buffer onto the widget.

Four of its decisions are adopted here.

- **Lazy, dirty-flag storage.** Setters store data and mark it stale;
  everything recomputes at paint time. `Line2D` keeps raw `_xorig` and
  `_yorig` with `_invalid` flags and rebuilds its `Path` in `recache`
  only on demand.
- **Nonlinearity in one early stage.** matplotlib isolates all
  nonlinearity in `transScale`, so the linear case reduces to a single
  affine from data to pixels. The plot core keeps the same seam.
- **Nice-number ticks from the view.** The default `MaxNLocator` picks a
  step from the staircase over 1, 2, 2.5, 5, 10 and places ticks as
  integer multiples of it. `AxisTicker` reimplements that in reduced
  form.
- **Interaction rewrites only the view.** A pan or zoom changes only the
  view limits; the data and its cached transform are untouched, so a
  redraw is cheap. The plot core follows this exactly.

The rest is deliberately not adopted, to keep the scope honest: the
pyplot current-figure state machine (the console function targets an
explicit window), the artist zorder tree (a plot window owns a flat list
of series), the weakref invalidation graph (recomputing one affine per
paint is cheap at this scale), and text-as-path rendering. No rasterizer
is written at all: QPainter already provides what the whole Agg layer
provides matplotlib, namely antialiased stroking, dashes, and joins, so
the entire C++ layer of matplotlib's design maps to nothing here.

## Target design

Two modules hold the feature, keeping the file count deliberately low.
`solvcon/pilot/_plot_core.py` is pure Python with no Qt import, so the
whole model is testable without a display; `solvcon/pilot/_plot.py` holds
the Qt half. Tests split the same way: `tests/test_plot_core.py` needs no
GUI, and `tests/test_pilot_plot.py` exercises the widget and the feature
under a virtual display.

```{figure} architecture.svg
:alt: Layered architecture of the native xy plot

The plot stack (left) and how each matplotlib concept maps onto it
(right).
```

### The core: model and geometry (`_plot_core.py`)

`PlotSeries` stores one series as flat float arrays with a label, a
color, a line width, and a dirty flag; a NaN in either array marks a gap
in the line. `PlotModel` is the plot document: the series list, the
default color cycle (matplotlib's C0 to C9 palette), the NaN-safe union
of the series bounding boxes, and the view limits, which autoscale
recomputes with a margin and a nonsingular guard.

```python
class PlotSeries:
    def set_data(self, x, y): ...       # flat float; x=None -> arange(len(y))
    def data_limits(self):              # (xmin, xmax, ymin, ymax) or None
        ...                             # counts a point only if both finite

class PlotModel:
    MARGIN = 0.05
    COLOR_CYCLE = (...)                 # C0..C9
    def add_series(self, series): ...   # assigns a cycle color if unset
    def autoscale(self): ...            # view = data limits + margin
```

`AffineMap` folds "view range to unit interval" and "unit interval to
pixel rectangle" into one scale and offset per axis, with y flipped for
Qt's top-left origin. An optional per-axis pre-transform is applied to
the data first, which is the seam a log scale would plug into later while
the linear case stays a single multiply-add; the public `x_scale` and
`y_scale` let the pan convert a pixel delta to a data delta without
touching internals.

```python
class AffineMap:
    def __init__(self, xlim, ylim, rect, xpre=None, ypre=None): ...
    def map(self, x, y): ...            # data -> pixel
    def unmap(self, px, py): ...        # pixel -> data (linear axes)
    x_scale, y_scale                    # pixels per data unit, per axis
```

`AxisTicker` picks the smallest staircase step that keeps the tick count
near its target and lays ticks as integer multiples of that step, so the
positions carry no cumulative float drift; `labels` renders with `%g` and
keeps `-0` out.

### The Qt half: widget and feature (`_plot.py`)

```{figure} widget-anatomy.svg
:alt: Anatomy of the plot widget layout

How the widget turns its size and the tick labels into the axes
rectangle, and where each drawing element lands.
```

`PlotWidget` computes the axes rectangle from the current tick labels
with `QFontMetrics` (the left gutter fits the widest y label, the bottom
gutter fits the label height), then paints, in a fixed order, the grid,
the frame, the tick marks and labels, and every series as antialiased
`QPolygonF` runs split at NaN and clipped to the axes rectangle; an empty
model paints a placeholder instead of axes, and a paint pass clears the
series dirty flags. `PlotFeature` supplies the "Plot / XY plot" action
that opens a plot sub-window, `console_plot` adds a series to the plot
window under focus (or the most recent open one) and opens one lazily,
and the mouse owns navigation: the wheel zooms about the cursor, a left
drag pans, and a double click restores the autoscaled view.

## Out of scope, planned as follow-ups

- Migrating the 1D solver applications off matplotlib onto this widget; a
  separate plan once the widget has proven itself.
- Log and other axis scales (the pre-transform seam is already reserved).
- Legend interaction, series removal UI, PNG/SVG export, blit-style
  animation.

<!-- vim: set ft=markdown ff=unix fenc=utf8 et sw=2 ts=2 sts=2 tw=79: -->
