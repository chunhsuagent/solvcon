# Native xy plot (RPlotWidget)

Give the pilot a first-class, native xy-plot window: `RPlotWidget`, a `QWidget` beside the 3D domain viewer that holds series data in C++ as `SimpleArray` and draws it with QPainter, reusing the pilot's existing 2D drawing stack. It plots without touching the GPU, so it runs anywhere the pilot's GUI runs -- including headless, where it renders straight to a `QImage` -- and the data never crosses the Python boundary each frame. A GPU (QRhi) renderer is left as an optional future acceleration, not a dependency, and the design keeps the seam for it.

## Goal

1. **A native C++ plot widget on the existing 2D stack.** `RPlotWidget`, a `QWidget`, draws xy series with QPainter and reuses the pilot's `ViewTransform2dFp64` for the world-to-screen mapping and pan/zoom, the way `R2DWidget` already does. Plain Qt, no GPU context: it works on a discrete GPU, on software GL, on no accelerator, and headless (render to a `QImage`) with the same code.
2. **Data resident in C++.** Series hold `SimpleArray<double>`; the widget's `paintEvent` transforms and draws straight from them, so a pan or zoom never turns the arrays into Python objects. This is the reason to build in C++: the solver output is already `SimpleArray` and never has to become a Python object to be drawn.
3. **Decimation is the scalability primitive.** Before drawing, the core reduces each pixel column to a min/max pair, so a million-point series costs one screen-width of segments, not a million. This -- in C++, on the CPU -- is what keeps a large series interactive; no GPU is needed for it.
4. **Python-scriptable.** The widget is bound through pybind11, and the console `plot(x, y)` hands arrays straight to the C++ widget, so a plot is one call from the pilot console.

The planned steps come right below. Every section after them supports the steps: what the pilot has today and the gaps that remain, the design the steps build, and what is deferred.

## Planned steps

Each step is one pull request: one concern, lint-clean, and leaving the pilot building and green. Steps 1 to 3 build the C++ core as independent pieces; steps 4 to 7 build the widget and its integration on top, each on the ones before it. This plan lands first as its own pull request.

1. **Step 1. Series and model (C++).** `RPlotSeries` (a `SimpleArray<double>` pair plus style) and `RPlotModel` (the series list, the color cycle, the NaN-safe data limits, and the view limits with an autoscale margin and a nonsingular guard). The model derives a `ViewTransform2dFp64` from its limits rather than adding a new affine. Pure C++ math with no Qt widget; bound through pybind11 and covered by pytest the way the rest of the pilot is tested.
2. **Step 2. The tick locator (C++).** `RPlotTicker`, a nice-number locator that turns an axis range into round tick positions and their labels. Pure C++, independent of the rest of the core; bound through pybind11 and covered by pytest.
3. **Step 3. The decimator (C++).** `RPlotDecimator`, the min/max-per-pixel-column reduction that bounds the drawn segment count, so a million-point series costs one screen-width of segments. Pure C++, bound through pybind11 and covered by pytest.
4. **Step 4. The QPainter widget draws a series.** `RPlotWidget : QWidget`, structured like `R2DWidget`: it owns a `ViewTransform2dFp64` and an `RPlotModel`, and its `paintEvent` maps each series through the transform, decimates it with `RPlotDecimator` to a screen-width of segments, and strokes the polyline. A render smoke test grabs the widget to a `QImage` (the `renderImage` path `R2DWidget` already provides) and asserts a series changes the pixels -- the same path headless export uses.
5. **Step 5. Axes, grid, and labels.** The frame, grid, and tick marks reuse the 2D chrome path (`RWorldRenderer2d`), positioned from `RPlotTicker`; tick and axis labels are QPainter text, or `RTextOverlay` where it fits. The plot now reads as a plot, not just a polyline.
6. **Step 6. Pilot integration.** A Python plot feature (a `PilotFeature` subclass, like the pilot's other features) adds the "Plot / XY plot" action and opens an `RPlotWidget` sub-window through `RManager.addSubWindow`; the console `plot(x, y)` hands a `SimpleArray` (zero-copy from a NumPy array) to the widget and is seeded into `build_pilot_namespace`. The plot opens and scripts, still static.
7. **Step 7. Interaction.** Wheel zoom about the cursor, drag pan, and double-click autoscale route through the `ViewTransform2dFp64` helpers (`zoom_at_clamped`, `pan`, `reset`) in the widget's C++ event handlers, then re-decimate and repaint.

Follow-ups after the train: markers and format strings; a legend; and a GPU (QRhi) renderer backend -- only if the post-decimation CPU draw ever becomes the interactive bottleneck for a very large series. A colormap or heatmap layer would build on the same core.

## What the pilot has today

This section records the machinery the steps reuse and the gaps that remain; each gap names the step that fills it.

The pilot cannot plot a data array. The only data plotting is matplotlib embedded in the one-dimensional solver applications (`solvcon/pilot/_base_app.py`), welded to `OneDimBaseApp` and reusable nowhere else, and it pulls the whole matplotlib stack into the GUI.

What the pilot does already have is a full 2D QPainter drawing stack, built for the canvas feature, that this plan reuses instead of reinventing:

- **A 2D view transform.** `ViewTransform2dFp64` (`cpp/solvcon/universe/ViewTransform2d.hpp`, bound to Python) maps world to screen and back with `screen_from_world` / `world_from_screen`, and carries `pan`, `zoom_at`, `zoom_at_clamped`, and `reset` with a +Y-up flip. This is the plot's affine; the plan does not add its own.
- **A 2D QPainter widget.** `R2DWidget` (`cpp/solvcon/pilot/R2DWidget.hpp`, a `QWidget`, bound to Python) paints geometry through the transform, handles wheel-zoom and drag-pan, and offers `renderImage()` for offscreen `QImage` export. `RPlotWidget` follows its structure.
- **2D chrome and text.** `RWorldRenderer2d` (`cpp/solvcon/pilot/RWorldRenderer2d.hpp`) draws the backdrop plus an optional grid, axes, and origin marker; `RAxisGizmo` and `RTextOverlay` render axis and label text. The plot frame, grid, and labels reuse these.
- **The array type.** `SimpleArray<double>` (`cpp/solvcon/buffer/SimpleArray.hpp`) is the pilot's array, zero-copy to and from NumPy, so a series holds solver output without a copy.
- **The binding and feature patterns.** `wrap_pilot.cpp` binds pilot C++ classes through pybind11, `RManager.addSubWindow` places any `QWidget` in a titled MDI sub-window, features are `PilotFeature` (`solvcon/pilot/_gui_common.py`) subclasses, and `build_pilot_namespace` (`solvcon/apputil.py`) seeds the console handles.

If a GPU backend is ever built, its groundwork is present too: a `QRhiWidget` precedent (`RDomainWidget`) and a shader pipeline compiled to `.qsb` (`cpp/solvcon/pilot/shaders/`). None of it is on the critical path for the CPU widget, and `ViewTransform2dFp64` feeds either renderer.

### Gaps

- **No data-series plotting** (steps 1, 4, 6). The 2D stack draws editable geometry (`World` shapes: segments, curves) with ids and selection -- the wrong model for a million-point data series, and there is no widget or model a caller can hand two arrays.
- **No data axes** (steps 1, 2, 5). The canvas chrome grids around the world origin; a plot needs autoscale to the data range with a margin and a nice-number tick locator with value labels.
- **Nothing decimates** (steps 3, 4). Drawing every point costs more as the point count grows; reducing each pixel column to a min/max pair bounds it.
- **The console cannot plot arrays** (step 6). `build_pilot_namespace` seeds many handles but none to plot two arrays.

## Design

The plan keeps the series data and its reduction in C++, reuses the 2D transform and QPainter stack for the drawing, and exposes a thin Python surface.

```{figure} pipeline.svg
:alt: The RPlotWidget CPU pipeline

Series data stays in SimpleArray in C++; the core transforms and decimates it through ViewTransform2d; RPlotWidget strokes it with QPainter. A GPU backend can reuse the same core and transform later.
```

### Running without a GPU or a display

Because the widget is plain QPainter, it needs no GL or Vulkan context. On a machine with no GPU it renders on the CPU with no fallback layer; on a headless host it renders straight into a `QImage`, the way `R2DWidget`'s `renderImage()` already does, so image export needs no display, no `xvfb`, and no software GL. This is the property a GPU/QRhi widget cannot offer without a render context, and it is why the core stays renderer-agnostic.

### The C++ core (pure C++, no widget)

```cpp
class RPlotSeries {
    SimpleArray<double> m_x, m_y;   // NaN marks a gap
    // label, color, width
public:
    void set_data(SimpleArray<double> x, SimpleArray<double> y);
    std::optional<std::array<double,4>> data_limits() const; // NaN-safe
};

class RPlotModel {                       // series list + color cycle
    void add_series(RPlotSeries);        // assigns a cycle color if unset
    void autoscale();                    // view = data limits + margin
    ViewTransform2dFp64 view(int w, int h) const;  // reuse, not reinvent
};

class RPlotTicker { /* nice-number locator + labels */ };

class RPlotDecimator {                   // min/max per pixel column
    // reduces a series to <= 2 points per horizontal pixel
};
```

### The QPainter widget

`RPlotWidget : QWidget` mirrors `R2DWidget`: it owns a `ViewTransform2dFp64` and draws in `paintEvent` by mapping each series through it, decimating with `RPlotDecimator` to a screen-width of segments, and stroking the polyline; the frame, grid, and ticks reuse the 2D chrome, and the labels are QPainter text placed from `RPlotTicker`. A pan or zoom calls the transform's `pan` / `zoom_at_clamped`, re-decimates, and repaints; the `SimpleArray` stays put and is never copied to Python. The same `paintEvent` serves an on-screen widget and an offscreen `QImage`, so interactive display and headless export share one code path.

### The Python layer

The Python plot feature adds the menu action and opens the sub-window; the console `plot(x, y)` wraps its NumPy arguments as `SimpleArray` (zero-copy) and calls the widget's `add_series`. This is the whole Python surface: a menu entry and one console function over the C++ widget.

### Room for a GPU backend

The core (`RPlotModel`, `RPlotTicker`, `RPlotDecimator`) and the `ViewTransform2dFp64` know nothing about QPainter; they produce limits, a transform, ticks, and a decimated point set. A GPU renderer, if profiling ever demands one, reuses all of it and replaces only the paint path -- a `QRhiWidget` sibling that uploads the same `SimpleArray` to a vertex buffer, carries the same transform as a uniform, and draws text through `RTextOverlay`. Keeping that seam is why the core carries no Qt widget code.

## Out of scope, planned as follow-ups

- Markers and matplotlib-style format strings.
- A legend.
- A GPU (QRhi) renderer backend, only if the post-decimation CPU draw becomes the interactive bottleneck for a very large series.
- A colormap or heatmap layer on the same core.
- Folding the series into the `World` shape model; rejected here to keep data visualization separate from shape editing, and revisited only if a concrete need appears.
- Migrating the 1D solver applications onto this widget; a separate plan once the widget has proven itself.

<!-- vim: set ft=markdown ff=unix fenc=utf8 et sw=2 ts=2 sts=2 tw=79: -->
