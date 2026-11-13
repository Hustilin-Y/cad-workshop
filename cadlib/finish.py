"""Finishing: roundings and chamfers that don't spoil the print.

The printing rule: edges vertical in the print orientation can be rounded any way;
edges on the bed get only a 45° chamfer (a rounding there would be an overhang, and the chamfer
also hides the elephant's foot); top edges, any rounding.

On a complex body OCCT often refuses to round an edge. So edges
are done one by one: if the radius fails, half of it is tried, otherwise the edge
is skipped: the part doesn't break over cosmetics.
"""

from __future__ import annotations

from build123d import Edge, Solid, chamfer, fillet


def _apply(op, body: Solid, edges: list[Edge], size: float) -> tuple[Solid, int]:
    # First all edges in one operation: OCCT rounds a face's outline (a chain of tangent edges)
    # only as a whole; one by one, neighbouring edges change length and can no longer be found.
    for s in (size, size / 2):
        try:
            result = op(edges, s)
            solids = result.solids()
            if len(solids) == 1 and solids[0].is_valid:
                return solids[0], len(edges)
        except Exception:  # noqa: BLE001
            pass
    done = 0
    for edge in edges:
        for s in (size, size / 2):
            # After each operation the body's edges are recreated: find the current edge by position.
            current = _find_edge(body, edge)
            if current is None:
                break
            try:
                result = op(current, s)
                solids = result.solids()
                if len(solids) == 1 and solids[0].is_valid:
                    body = solids[0]
                    done += 1
                    break
            except Exception:  # noqa: BLE001  OCCT raises various exceptions on a failed rounding
                continue
    return body, done


def _find_edge(body: Solid, edge: Edge, tol: float = 1e-4):
    c, length = edge.center(), edge.length
    for e in body.edges():
        if (e.center() - c).length < tol and abs(e.length - length) < tol:
            return e
    return None


def soften(body: Solid, edges: list[Edge], radius: float) -> tuple[Solid, int]:
    """Round edges one by one; returns (body, how many edges were rounded)."""
    return _apply(lambda e, r: fillet(e, r), body, edges, radius)


def bevel(body: Solid, edges: list[Edge], size: float) -> tuple[Solid, int]:
    """Chamfer edges one by one; returns (body, how many edges were done)."""
    return _apply(lambda e, s: chamfer(e, s), body, edges, size)
