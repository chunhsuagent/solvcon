# Cell picking in Python and the GUI

Lift the pilot viewer's pick result out of the widget into a standalone type, bind that type to Python so a pick is a first-class, testable object rather than an ad-hoc dict, and wire a click in the 3D viewer through to the Inspector so the picked entity is shown on screen.

## Goal

1. **A standalone pick type.** Extract `PickResult` out of the `RDomainWidget` class into a type of its own, so the picked information (entity kind, id, element type, measure, centroid) is a plain value that lives independently of the viewer widget.
2. **A first-class Python object.** Bind the standalone `PickResult` through pybind11 so `pickCell` / `pickNode` / `pickFace` hand Python a real object with named, read-only fields and a `hit` flag, replacing today's hand-built dict, so picking is usable and unit-testable from Python.
3. **A pick shown in the GUI.** Let a click in the 3D viewer pick the entity under the cursor, and route the result to the Inspector panel so the pick appears as a section in the mesh tree, next to the counts and boundary sets already shown there.
4. **Tests at every layer.** Unit-test the bound `PickResult` from Python, and test the click-to-Inspector path under a virtual display, so both the data object and the GUI wiring are covered.

The planned steps come first. Every section after them exists to support the steps: what the pilot has today and the gaps that remain, the design the steps build, and the follow-ups left out of scope.

## Planned steps

Each step is one pull request: one concern, lint-clean, and leaving the tree building and the pilot suite green. This plan lands first as its own pull request; the vocabulary it uses (`PickResult`, `setPickCallback`, `lastPick`, `make_selection_info`) is defined under "Design", and the evidence for each step is under "What the pilot has today".

1. **Step 1. Extract `PickResult` into a standalone type.** Add `cpp/solvcon/pilot/PickResult.hpp` holding `solvcon::PickResult` (moved verbatim out of `RDomainWidget`), register the header in `cpp/solvcon/pilot/CMakeLists.txt`, and update `RDomainWidget.hpp` and `RDomainWidget.cpp` so `pickCell` / `pickNode` / `pickFace` return the namespace-scope type. Then bind it: in `cpp/solvcon/pilot/wrap_pilot.cpp`, add a `py::class_` for `solvcon::PickResult` with read-only `kind`, `id`, `type`, `measure`, and `centroid`, plus a `hit` property, and make the three pick methods return the bound object (always a `PickResult`, never `None`, per the miss contract below), dropping `pick_to_py`. Rewrite the existing pick tests in `tests/test_pilot_domain_widget.py` from dict access to attribute access and a `hit()` miss, and add `PickResult` unit tests. Extracting the type has no external effect until it is bound, so the extraction and the binding are one concern. Depends on nothing.
2. **Step 2. Notify a pick from a click.** In `RDomainWidget`, store the last pick and add `lastPick()`; add a Python-settable pick callback (`setPickCallback`) invoked when a pick lands; and, in `mouseReleaseEvent`, treat a left button that moved less than a small pixel threshold since press as a click, picking the cell under the cursor and firing the callback with the result, hit or miss (a larger travel is a camera drag and picks nothing) -- no dedicated mode and no modifier. The viewer highlight comes free, because `pickCell` already paints the picked cell through `setSelection`; a miss click additionally calls `clearSelection()`, so clicking empty space clears the stale highlight. Bind `lastPick` and `setPickCallback`. Add a live GUI test that a click routes a `PickResult` to a registered callback, that a miss click clears the selection, and that a drag does neither. Depends on Step 1.
3. **Step 3. Show the pick in the Inspector.** In `solvcon/pilot/_tree_panel.py`, give `MeshInfoTree` a selection section (`make_selection_info` and `set_selection`), and in `TreePanel._sync` register a pick callback on the active 3D viewer that feeds the picked `PickResult` into the mesh tree, clearing it when the mesh changes. Add a GUI test that a pick updates the tree. Depends on Step 2.

The train is linear: Step 1 is the load-bearing one -- it lifts the pick out of the widget and turns it into a Python object the later steps and the tests consume; Step 2 adds the C++ trigger and the cross-language callback; and Step 3 is the Python GUI surface. Nothing here is safely parallel, since each step consumes the type or the API the previous one lands; review order equals merge order.

## What the pilot has today

`PickResult` is a helper struct nested inside the widget, not a type of its own (`cpp/solvcon/pilot/RDomainWidget.hpp:148`):

```cpp
struct PickResult
{
    std::string kind = "none";
    int id = -1;
    int type = -1;
    double measure = 0.0;
    QVector3D centroid;

    bool hit() const { return "none" != kind; }
}; /* end struct PickResult */
```

The three pick methods return it and are declared alongside it (`cpp/solvcon/pilot/RDomainWidget.hpp:162`):

```cpp
PickResult pickCell(int x, int y);
PickResult pickNode(int x, int y);
PickResult pickFace(int x, int y);
```

A pick carries the entity kind (`"cell"`, `"node"`, `"face"`, or `"none"` for a miss), the entity id, the element type number (for a cell), a measure (cell volume or face area), and the centroid. `pickCell` fills every field; `pickNode` sets only `kind`, `id`, and `centroid`; `pickFace` sets `kind`, `id`, `measure`, and `centroid` (`cpp/solvcon/pilot/RDomainWidget.cpp:1100`, `:1164`, `:1220`). The element type number matches the `StaticMesh` constants the Inspector already names (`solvcon/pilot/_tree_panel.py:101`, `CELL_TYPE_NAME`).

The pick methods already paint their own viewer feedback. Every hit routes through `setSelection`, which drops the previous highlight drawable and, for a cell, adds a bright surface highlight over the picked cell's triangles; a node or face records the selection point without a surface highlight (`cpp/solvcon/pilot/RDomainWidget.cpp:1231`, `:1242`). `clearSelection` drops the selection and its highlight (`cpp/solvcon/pilot/RDomainWidget.hpp:166`, `.cpp:1326`) and is already bound to Python (`cpp/solvcon/pilot/wrap_pilot.cpp:331`). A miss, however, returns early without touching the previous selection, so a stale highlight lingers until the next hit or an explicit `clearSelection`.

Picking reaches Python, but only as a hand-built dict, not as a type. In the pybind layer, `pick_to_py` converts a `PickResult` to a `dict` and returns `None` on a miss (`cpp/solvcon/pilot/wrap_pilot.cpp:143`):

```cpp
static pybind11::object pick_to_py(RDomainWidget::PickResult const & r)
{
    if (!r.hit()) { return py::none(); }
    py::dict d;
    d["kind"] = r.kind;
    d["id"] = r.id;
    // ... type, measure, centroid as a 3-tuple ...
}
```

The three methods are bound through lambdas that call `pick_to_py` (`cpp/solvcon/pilot/wrap_pilot.cpp:302`), so the only Python surface is a loose dict. The existing tests read it by key -- `r["kind"]`, `r["id"]`, `r["measure"]`, `r["centroid"]` -- and assert `None` on a miss (`tests/test_pilot_domain_widget.py:1145`). A plain value type bound to Python is already the pilot's own idiom: `Overlay2dOptions` is bound as a `py::class_` with `def_readwrite` fields (`cpp/solvcon/pilot/wrap_pilot.cpp:1221`).

Nothing connects a pick to a mouse click or to the GUI. `mousePressEvent` only chooses a camera drag action from the button and modifiers; it never calls a pick method (`cpp/solvcon/pilot/RDomainWidget.cpp:1756`), and the widget declares no Qt signal and holds no callback. A pick happens only when Python calls `pickCell` and reads the return value. On the GUI side, the Inspector's `MeshInfoTree` builds its tree from the mesh alone -- style toggles, overlay toggles, boundary sets, then the counts, bounding box, and cell-type sections rendered by `make_mesh_info` and `_render_sections` (`solvcon/pilot/_tree_panel.py:182`, `:125`, `:68`) -- with no place for a picked entity. The unified `TreePanel` follows the active sub-window and, for a 3D viewer, hands the widget's mesh to `MeshInfoTree` in `_sync`; it already routes boundary, edge, and normal toggles from the tree back to the viewer through plain Python callbacks (`solvcon/pilot/_tree_panel.py:782`, `:797`), which is the seam a pick callback plugs into.

### Gaps

- **`PickResult` is welded to the widget** (Step 1). It is a nested struct, so no code and no test can name the pick type without the widget. Step 1 lifts it to `solvcon::PickResult` in its own header.
- **A pick is a dict, not an object** (Step 1). `pick_to_py` synthesizes a `dict`, so Python has no `PickResult` type to construct, inspect, or assert against beyond string keys. Step 1 binds the standalone type and returns it from the three pick methods.
- **No click picks, and nothing notifies Python** (Step 2). The press only arms a camera drag, and the widget has no signal or callback, so a pick is purely a pull from Python. Step 2 adds `lastPick`, a settable pick callback, and a pick from a click distinguished from a drag.
- **The Inspector cannot show a pick** (Step 3). `MeshInfoTree` renders only mesh-derived sections and `TreePanel` wires no pick path. Step 3 adds a selection section and registers a pick callback in `_sync`.

## Design

### The standalone type (`PickResult.hpp`)

Step 1 moves the struct verbatim into a new namespace-scope type; only its home changes, not its fields or its `hit()` semantics. It stays a plain value carrying `QVector3D`, matching the pilot's other rendering types, and is header-only (no `.cpp`).

```cpp
// cpp/solvcon/pilot/PickResult.hpp
namespace solvcon
{

/// The result of a viewer pick: the entity kind ("cell", "node",
/// "face", or "none" for a miss), its id, its element type (for a
/// cell), a measure (cell volume or face area), and its centroid.
struct PickResult
{
    std::string kind = "none";
    int id = -1;
    int type = -1;
    double measure = 0.0;
    QVector3D centroid;

    bool hit() const { return "none" != kind; }
}; /* end struct PickResult */

} /* end namespace solvcon */
```

`RDomainWidget.hpp` includes the new header and drops the nested struct; its three pick methods return `PickResult` (same namespace, so unqualified), and the definitions in `RDomainWidget.cpp` change their return type spelling only. The header is added to `SOLVCON_PILOT_PYMODHEADERS` in `cpp/solvcon/pilot/CMakeLists.txt`.

### The pybind11 binding

Step 1 binds the standalone type the same way `Overlay2dOptions` is bound, with read-only fields (a pick is produced by C++, not assembled in Python) and the `centroid` exposed as an `(x, y, z)` tuple to match the value the dict carried:

```cpp
py::class_<PickResult> pick_result(
    mod, "PickResult",
    "The result of a viewer pick: the entity kind, id, element type "
    "(for a cell), a measure (cell volume or face area), and the "
    "centroid. hit is False on a miss.");
pick_result
    .def_readonly("kind", &PickResult::kind)
    .def_readonly("id", &PickResult::id)
    .def_readonly("type", &PickResult::type)
    .def_readonly("measure", &PickResult::measure)
    .def_property_readonly(
        "hit", &PickResult::hit)
    .def_property_readonly(
        "centroid",
        [](PickResult const & r)
        {
            return py::make_tuple(
                r.centroid.x(), r.centroid.y(), r.centroid.z());
        });
```

`pickCell` / `pickNode` / `pickFace` then return the bound object directly, and `pick_to_py` and its `None`-on-miss path are dropped. The miss contract is settled: a pick method **always** returns a `PickResult`, never `None`; a miss is `kind == "none"` with `hit()` false, so callers branch on `hit` rather than on `None`. This is why Step 1 also rewrites the existing pick tests from `r["kind"]` to `r.kind` and from an `assertIsNone` miss to `assertFalse(r.hit)`, and why the Inspector wiring in Step 3 keys on `pick.hit` alone.

### Notifying a pick from a click

Step 2 gives the widget a memory of its last pick and a way to tell Python about one. `RDomainWidget` gains a stored `PickResult m_last_pick` set by the pick methods, a `PickResult lastPick() const` getter, and a `std::function<void(PickResult const &)> m_pick_callback` set through `void setPickCallback(std::function<void(PickResult const &)>)`. When a pick lands, the widget invokes the callback if one is set. A callback, rather than a Qt signal, is chosen because the viewer reaches Python as the pybind-wrapped object (the object `RManager::currentR3DWidget` returns and on which `mesh`, `showBoundary`, and the pick methods are already called), so a `std::function` the Python side registers mirrors the existing `boundary_toggled` / `edges_toggled` / `normals_toggled` callback style exactly. `setPickCallback` and `lastPick` are bound in `wrap_pilot.cpp`, and passing `None` clears the callback.

The pick needs no dedicated mode and no modifier, because a pick and a camera move are already distinct gestures: a pick is a single click (press and release at nearly the same pixel) and a camera move is a drag. The handlers confirm the two do not conflict. `mousePressEvent` only records the press point and selects a drag action; it moves nothing (`cpp/solvcon/pilot/RDomainWidget.cpp:1756`, ending at `update()` on `:1807`). The camera turns only in `mouseMoveEvent`, and only while a button is held, by the `pos - m_last_mouse_pos` delta (`cpp/solvcon/pilot/RDomainWidget.cpp:1810`, the no-button early return at `:1812` and the pan/zoom/rotate at `:1822`). `mouseReleaseEvent` only resets the drag action (`cpp/solvcon/pilot/RDomainWidget.cpp:1836`). So a press followed by a release with no movement in between leaves the camera untouched, which is exactly a click.

Step 2 uses that. The widget records the press position in a new member (the existing `m_last_mouse_pos` is overwritten by each move, so it cannot serve) and, in `mouseReleaseEvent`, measures the travel from press to release: below a small pixel threshold it is a click, so the widget picks the cell under the cursor with `pickCell`, stores it as `m_last_pick`, and fires the callback with the result, hit or miss; at or above the threshold it was a camera drag and no pick happens. The gesture is scoped to a plain left button with no navigation modifier, so a right- or middle-button pan and a modified navigation drag never pick. The on-screen feedback costs Step 2 nothing new: a hit already swaps the highlight inside `pickCell` (through `setSelection`), and on a miss the click calls `clearSelection()`, so clicking empty space drops the stale highlight while the miss result flowing through the callback lets the Inspector clear its selection section in the same gesture.

### Wiring the pick into the Inspector (Python)

Step 3 adds a selection section to the mesh tree and feeds it from a pick callback. `MeshInfoTree` gains a classmethod that turns a pick into display rows and a method that renders (or clears) it:

```python
@classmethod
def make_selection_info(cls, pick):
    """Build the picked-entity rows as one ``(section, rows)`` group.

    :param pick: The pick to describe, or a miss.
    :type pick: solvcon.pilot.PickResult
    :return: A single ``(section, rows)`` group, or ``None`` on a miss.
    :rtype: tuple or None
    """
    if pick is None or not pick.hit:
        return None
    rows = [["kind", pick.kind], ["id", str(pick.id)]]
    if pick.kind == "cell":
        rows.append(["type", cls.CELL_TYPE_NAME.get(pick.type,
                                                    str(pick.type))])
    if pick.kind in ("cell", "face"):
        rows.append(["measure", f"{pick.measure:.4g}"])
    cx, cy, cz = pick.centroid
    rows.append(["centroid", f"({cx:.4g}, {cy:.4g}, {cz:.4g})"])
    return ("Selection", rows)

def set_selection(self, pick):
    """Show the picked entity as the selection section, or clear it.

    :param pick: The pick to show, or ``None`` to clear the section.
    :type pick: solvcon.pilot.PickResult or None
    :return: None
    """
    # Re-render the tree with the selection group appended so the
    # section tracks the latest pick (or its absence).
    ...
```

`TreePanel._sync` already selects the mesh tree and hands it the viewer's mesh for a 3D sub-window; there it also registers a pick callback on the active viewer that forwards each pick into the tree:

```python
def _sync(self):
    widget3d = self._mgr.currentR3DWidget()
    if widget3d is not None:
        self._stack.setCurrentWidget(self._mesh_tree)
        self._mesh_tree.set_mesh(widget3d.mesh)
        widget3d.setPickCallback(self._on_picked)
        return
    ...

def _on_picked(self, pick):
    """Show the viewer's latest pick in the mesh tree."""
    self._mesh_tree.set_selection(pick)
```

The selection is transient: `set_mesh` already rebuilds the tree from the mesh, so loading or switching a mesh drops the section until the next pick, and a miss (or a cleared selection) renders no section.

## Out of scope

- Picking in the 2D canvas (`R2DWidget`); this plan covers the 3D domain viewer only, which is where `pickCell` / `pickNode` / `pickFace` live.
- A pick-mode toolbar or menu, cursor feedback, and multi-select; the GUI trigger here is the single click Step 2 introduces.
- Reading field values at the picked entity, or any derived analysis beyond the geometric facts a `PickResult` already carries.
- Surfacing the pick in the embedded console namespace (`build_pilot_namespace`); a console handle for the current pick is a natural follow-up once the object and the callback exist.

<!-- vim: set ft=markdown ff=unix fenc=utf8 et sw=2 ts=2 sts=2 tw=79: -->
