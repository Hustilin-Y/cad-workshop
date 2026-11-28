"""The light 3D preview the Mini App's Print tab shows (cadlib/webpreview.py): format v1."""
import struct

import numpy as np
import pytest
import trimesh

from cadlib.webpreview import MAX_TRIANGLES, read_preview, write_preview


def test_a_box_round_trips_within_a_tenth_of_a_millimetre(tmp_path):
    box = trimesh.creation.box(extents=(40.0, 20.0, 10.0))
    box.apply_translation((20.0, 10.0, 5.0))
    path = tmp_path / "box.preview.bin"
    info = write_preview([(box, None, 0)], path)
    data = read_preview(path)
    assert np.allclose(data["bbox"], [0, 0, 0, 40, 20, 10], atol=1e-3)
    (group,) = data["groups"]
    assert group["rgba"] == (200, 200, 200, 255) and group["plate"] == 0
    assert np.allclose(group["vertices"].min(axis=0), [0, 0, 0], atol=0.1)
    assert np.allclose(group["vertices"].max(axis=0), [40, 20, 10], atol=0.1)
    assert len(group["faces"]) == 12 == info.triangles
    assert info.bytes == path.stat().st_size


def test_a_dense_mesh_is_cut_to_the_budget(tmp_path):
    sphere = trimesh.creation.icosphere(subdivisions=7, radius=50.0)  # 327,680 faces
    path = tmp_path / "sphere.preview.bin"
    info = write_preview([(sphere, None, 0)], path)
    assert info.triangles <= MAX_TRIANGLES
    assert path.stat().st_size <= 1024 * 1024
    data = read_preview(path)
    assert np.allclose(data["bbox"][:3], sphere.bounds[0], atol=0.1)  # AC3.1
    assert np.allclose(data["bbox"][3:], sphere.bounds[1], atol=0.1)


def test_groups_keep_their_colours_and_plates(tmp_path):
    a = trimesh.creation.box(extents=(10, 10, 10))
    b = trimesh.creation.box(extents=(5, 5, 5))
    b.apply_translation((100, 0, 0))
    path = tmp_path / "kit.preview.bin"
    write_preview([(a, (255, 0, 0, 255), 1), (b, (0, 0, 255, 128), 2)], path)
    groups = read_preview(path)["groups"]
    assert [(g["rgba"], g["plate"]) for g in groups] == [((255, 0, 0, 255), 1), ((0, 0, 255, 128), 2)]
    assert np.allclose(groups[1]["vertices"].mean(axis=0), [100, 0, 0], atol=0.1)


def test_more_than_65535_vertices_use_32_bit_indices(tmp_path):
    sphere = trimesh.creation.icosphere(subdivisions=7, radius=50.0)
    path = tmp_path / "big.preview.bin"
    write_preview([(sphere, None, 0)], path, max_triangles=150_000)
    (group,) = read_preview(path)["groups"]
    assert len(group["vertices"]) > 65535
    assert group["faces"].max() < len(group["vertices"])


def test_a_bad_file_is_refused(tmp_path):
    box = trimesh.creation.box(extents=(1, 1, 1))
    path = tmp_path / "ok.preview.bin"
    write_preview([(box, None, 0)], path)
    raw = path.read_bytes()
    (tmp_path / "short.bin").write_bytes(raw[:-10])
    (tmp_path / "magic.bin").write_bytes(b"XXXX" + raw[4:])
    (tmp_path / "version.bin").write_bytes(raw[:4] + struct.pack("<H", 2) + raw[6:])
    for name in ("short.bin", "magic.bin", "version.bin"):
        with pytest.raises(ValueError):
            read_preview(tmp_path / name)


# -- written by the CLI ------------------------------------------------------------------------

from cad import main  # noqa: E402


def _box_part(folder, name="box", size=20):
    folder.mkdir(parents=True)
    (folder / "model.py").write_text(
        "from build123d import Box, Pos\n"
        f"NAME = '{name}'\n"
        "def build(p):\n"
        f"    return Pos(0, 0, 5) * Box({size}, 10, 10)\n", encoding="utf-8")
    return folder


def test_build_writes_the_preview(tmp_path, capsys):
    folder = _box_part(tmp_path / "box")
    assert main(["build", str(folder)]) == 0
    path = folder / "out" / "box.preview.bin"
    data = read_preview(path)
    assert np.allclose(data["bbox"], [-10, -5, 0, 10, 5, 10], atol=0.1)
    assert "PREV" in capsys.readouterr().out


def test_kit_writes_groups_with_their_plates(tmp_path):
    _box_part(tmp_path / "one", "part-one", 20)
    _box_part(tmp_path / "two", "part-two", 30)
    (tmp_path / "one" / "kit.py").write_text("KITS = {'demo': [[('.', 1)], [('../two', 2)]]}\n", encoding="utf-8")
    assert main(["kit", str(tmp_path / "one")]) == 0
    groups = read_preview(tmp_path / "one" / "out" / "demo.preview.bin")["groups"]
    assert [g["plate"] for g in groups] == [1, 2, 2]


def test_mesh_preview_from_a_3mf_and_skips_when_fresh(tmp_path, capsys):
    folder = _box_part(tmp_path / "box")
    assert main(["build", str(folder)]) == 0
    preview = folder / "out" / "box.preview.bin"
    preview.unlink()
    assert main(["mesh-preview", str(folder)]) == 0
    assert read_preview(preview)["groups"]
    capsys.readouterr()
    assert main(["mesh-preview", str(folder)]) == 0
    assert "up to date" in capsys.readouterr().out


def test_mesh_preview_all_walks_the_model_folders(tmp_path, capsys, monkeypatch):
    import cad
    monkeypatch.setattr(cad, "ROOT", tmp_path)
    for kind, name in (("parts", "a"), ("remix", "b")):
        folder = _box_part(tmp_path / kind / name, name)
        assert main(["build", str(folder)]) == 0
        (folder / "out" / f"{name}.preview.bin").unlink()
    assert main(["mesh-preview", "--all"]) == 0
    assert (tmp_path / "parts" / "a" / "out" / "a.preview.bin").is_file()
    assert (tmp_path / "remix" / "b" / "out" / "b.preview.bin").is_file()


def test_a_mesh_the_decimator_cannot_reduce_still_fits_and_ends(tmp_path, monkeypatch):
    """Found on caulk-gun (1.29M faces): fast-simplification stalls far above the target. The
    preview must still finish under the budget (vertex clustering), never loop."""
    import fast_simplification

    calls = []

    def stalled(points, faces, target_reduction):
        calls.append(target_reduction)
        return points, faces  # reduces nothing, like a mesh it can't collapse

    monkeypatch.setattr(fast_simplification, "simplify", stalled)
    sphere = trimesh.creation.icosphere(subdivisions=7, radius=50.0)
    path = tmp_path / "stuck.preview.bin"
    info = write_preview([(sphere, None, 0)], path)
    assert info.triangles <= MAX_TRIANGLES and len(calls) <= 3
    data = read_preview(path)
    assert np.allclose(data["bbox"][:3], sphere.bounds[0], atol=0.1)
    assert np.allclose(data["bbox"][3:], sphere.bounds[1], atol=0.1)
