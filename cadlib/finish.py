"""Отделка: скругления и фаски, которые не портят печать.

Правило для печати: рёбра, вертикальные в ориентации печати, — скругляются как угодно;
рёбра на столе — только фаска 45° (скругление у стола дало бы нависание, а фаска
заодно убирает «слоновью ногу»); рёбра сверху — скругление любое.

OCCT на сложном теле нередко отказывается скруглить ребро. Поэтому рёбра
обрабатываются по одному: если радиус не проходит, пробуется половина, иначе ребро
пропускается — деталь не ломается из-за косметики.
"""

from __future__ import annotations

from build123d import Edge, Solid, chamfer, fillet


def _apply(op, body: Solid, edges: list[Edge], size: float) -> tuple[Solid, int]:
    # Сначала все рёбра одной операцией: контур грани (цепочка касательных рёбер) OCCT
    # скругляет только целиком — по одному соседние рёбра меняют длину и перестают находиться.
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
            # После каждой операции рёбра тела пересоздаются: ищем текущее ребро по положению.
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
            except Exception:  # noqa: BLE001  OCCT бросает разные исключения на неудачном скруглении
                continue
    return body, done


def _find_edge(body: Solid, edge: Edge, tol: float = 1e-4):
    c, length = edge.center(), edge.length
    for e in body.edges():
        if (e.center() - c).length < tol and abs(e.length - length) < tol:
            return e
    return None


def soften(body: Solid, edges: list[Edge], radius: float) -> tuple[Solid, int]:
    """Скруглить рёбра по одному; возвращает (тело, сколько рёбер скруглено)."""
    return _apply(lambda e, r: fillet(e, r), body, edges, radius)


def bevel(body: Solid, edges: list[Edge], size: float) -> tuple[Solid, int]:
    """Фаска на рёбрах по одному; возвращает (тело, сколько рёбер обработано)."""
    return _apply(lambda e, s: chamfer(e, s), body, edges, size)
