from cadlib.style import log


def test_drain_returns_and_clears():
    log.drain()
    log.note("lattice", "3 cells dropped")
    log.note("finish", "ok", level="info")
    notes = log.drain()
    assert [(n.tool, n.level) for n in notes] == [("lattice", "warn"), ("finish", "info")]
    assert log.drain() == []


def test_profile_has_max_bridge():
    from cadlib.config import load_profile

    assert load_profile().max_bridge_mm == 10.0


def test_build_report_shows_style_line(repo_copy, capsys, tmp_path):
    # a throwaway model whose build() logs a note
    folder = tmp_path / "parts" / "noted"
    folder.mkdir(parents=True)
    (folder / "model.py").write_text(
        "from build123d import Box\nfrom cadlib.style.log import note\nNAME='noted'\n"
        "def build(p):\n    note('lattice', '2 cells dropped')\n    return Box(10, 10, 10)\n",
        encoding="utf-8")
    from cad import main

    assert main(["build", str(folder)]) == 0
    assert "[WARN] Style: lattice: 2 cells dropped" in capsys.readouterr().out
