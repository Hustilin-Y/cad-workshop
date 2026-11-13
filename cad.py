"""The CAD workshop's CLI: `uv run cad.py <command>`.

  new part <name>   create parts/<name>/ from the template
  new remix <name> <file>  create remix/<name>/, the original in source/ (read-only), then inspect
  build <folder>    build model.py/remix.py: export, preview, checks, report
  preview <path>    only the PNG preview (a model folder or an STL/3MF/STEP file)
  check <file>      checks of any file, including someone else's
  inspect <file>    size, volume, bodies, base, flat faces: before a remix
  orient <path>     best sides to print on, with PNGs and a PRINT_DOWN line
  build --all       build every part, remix and the calibration; one line each
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import importlib.util
import re
import shutil
import stat
import sys
import time
from datetime import date
from pathlib import Path
from types import ModuleType

ENTRY_FILES = ("model.py", "remix.py")


def main(argv: list[str] | None = None) -> int:
    # Without explicit UTF-8, output into a pipe (Git Bash, ssh, an agent) goes out as cp1252 or ASCII and mm³, ×, ° turn into "?".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except UserError as e:
        print(f"Error: {e}")
        return 2


class UserError(Exception):
    """An error the user can act on, shown without a traceback."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cad.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def profile_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--nozzle", type=float, help="nozzle, mm (default from printer.toml)")
        p.add_argument("--material", help="plastic: PLA/PETG/ABS/ASA (default from printer.toml)")

    p = sub.add_parser("new", help="create a part folder from the template")
    new_sub = p.add_subparsers(dest="kind", required=True)
    np_ = new_sub.add_parser("part", help="a part from scratch: parts/<name>/")
    np_.add_argument("name")
    np_.set_defaults(func=cmd_new_part)
    nr = new_sub.add_parser("remix", help="a remix of someone else's model: remix/<name>/, the original is copied into source/")
    nr.add_argument("name")
    nr.add_argument("file", type=Path)
    nr.set_defaults(func=cmd_new_remix)

    def set_flag(p: argparse.ArgumentParser) -> None:
        p.add_argument("--set", action="append", metavar="NAME=VALUE",
                       help="override a model parameter for this run, e.g. --set WIDTH=45 --set LOGO=False "
                            "(a shared module's: --set hanger.ROUND_R=2); the model file is not changed")

    p = sub.add_parser("build", help="build a model")
    p.add_argument("path", type=Path, nargs="?")
    p.add_argument("--all", action="store_true", help="build every part, remix and the calibration")
    p.add_argument("--section", choices=("x", "y", "z"), help="add a section to the preview (through the centre)")
    p.add_argument("--print-ready", action="store_true",
                   help="export STL/3MF turned for printing (PRINT_DOWN on the bed); STEP keeps the design orientation")
    set_flag(p)
    profile_flags(p)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("preview", help="only the preview")
    p.add_argument("path", type=Path)
    p.add_argument("--section", choices=("x", "y", "z"))
    p.add_argument("--out", type=Path, help="where to put the PNG")
    set_flag(p)
    profile_flags(p)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("orient", help="best sides to print on")
    p.add_argument("path", type=Path, help="a model folder or an STL/3MF/STEP file")
    p.add_argument("--top", type=int, default=3, help="how many orientations to show (default 3)")
    p.add_argument("--no-png", action="store_true", help="skip the preview of each orientation")
    set_flag(p)
    profile_flags(p)
    p.set_defaults(func=cmd_orient)

    p = sub.add_parser("check", help="check a file")
    p.add_argument("file", type=Path)
    p.add_argument("--bodies", type=int, default=1, help="expected number of bodies")
    p.add_argument("--down", help="which side of the model goes on the bed: +x/-x/+y/-y/+z/-z (default -z, as in the file)")
    profile_flags(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("inspect", help="a summary of a file")
    p.add_argument("file", type=Path)
    p.set_defaults(func=cmd_inspect)
    return parser


# --- a model from a folder --------------------------------------------------


def load_model(folder: Path) -> ModuleType:
    folder = folder.resolve()
    if not folder.is_dir():
        raise UserError(f"{folder} is not a folder; build expects parts/<name> or remix/<name>")
    entry = next((folder / f for f in ENTRY_FILES if (folder / f).exists()), None)
    if entry is None:
        raise UserError(f"no {' or '.join(ENTRY_FILES)} in {folder}")
    spec = importlib.util.spec_from_file_location(f"cadmodel_{folder.name.replace('-', '_')}", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise UserError(f"{entry.name} has no build(p) function")
    return module


def apply_overrides(module: ModuleType, items: list[str] | None):
    """--set NAME=VALUE: change UPPER_CASE parameters of the model (or of a module it holds, as
    hanger.ROUND_R) for one run. Values are Python literals (45, 0.3, False, "text", (1, 2));
    anything else is taken as text. Returns a function that puts the old values back.

    Only what build(p) reads at run time changes: a value computed from parameters at import
    (TOTAL = WIDTH + 2 * WALL at module level) keeps its old value.
    """
    saved = []
    try:
        for item in items or []:
            name, sep, raw = item.partition("=")
            name = name.strip()
            if not sep or not name:
                raise UserError(f"--set {item!r}: expected NAME=VALUE")
            target, attr = module, name
            if "." in name:
                owner, attr = name.rsplit(".", 1)
                target = getattr(module, owner, None)
                if not isinstance(target, ModuleType):
                    raise UserError(f"--set {name}: the model has no module {owner!r}")
            if not attr.isupper() or not hasattr(target, attr):
                raise UserError(f"--set {name}: no parameter {attr} in {getattr(target, '__name__', 'the model')}")
            try:
                value = ast.literal_eval(raw.strip())
            except (ValueError, SyntaxError):
                value = raw.strip()
            saved.append((target, attr, getattr(target, attr)))
            setattr(target, attr, value)
            print(f"  set {name} = {value!r} (was {saved[-1][2]!r})")
    except Exception:
        _restore(saved)
        raise
    return lambda: _restore(saved)


def _restore(saved) -> None:
    for target, attr, value in reversed(saved):
        setattr(target, attr, value)


def run_model(module: ModuleType, profile):
    """Calls the model's build(p); the result is a build123d solid or a trimesh mesh."""
    import trimesh
    from build123d import Shape

    try:
        result = module.build(profile)
    except ValueError as e:
        # A model's _validate(p) and cadlib.mesh operations explain the error in words; a traceback only gets in the way.
        raise UserError(f"the model did not build: {e}") from e
    if not isinstance(result, (Shape, trimesh.Trimesh)):
        raise UserError(f"build() returned {type(result).__name__}, expected a build123d solid or a trimesh.Trimesh")
    return result


def _profile(args):
    from cadlib.config import load_profile

    try:
        return load_profile(nozzle=args.nozzle, material=args.material)
    except ValueError as e:
        raise UserError(str(e)) from e


# --- commands ---------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _render_template(src: Path, dst: Path, name: str, extra: dict[str, str] | None = None) -> None:
    text = src.read_text(encoding="utf-8").replace("{{name}}", name).replace("{{date}}", date.today().isoformat())
    for key, value in (extra or {}).items():
        text = text.replace(key, value)
    dst.write_text(text, encoding="utf-8")


def _new_folder(kind_dir: str, name: str) -> Path:
    if not NAME_RE.match(name):
        raise UserError(f"name {name!r}: lowercase Latin letters, digits and hyphens only (e.g. wall-hook)")
    folder = ROOT / kind_dir / name
    if folder.exists():
        raise UserError(f"{_rel(folder)} already exists")
    folder.mkdir(parents=True)
    return folder


def cmd_new_part(args) -> int:
    folder = _new_folder("parts", args.name)
    _render_template(TEMPLATES / "part_model.py", folder / "model.py", args.name)
    _render_template(TEMPLATES / "part_README.md", folder / "README.md", args.name)
    print(f"Created: {_rel(folder)}  (model.py, README.md)")
    print(f"Next: fill in the parameters in model.py and `uv run cad.py build {_rel(folder)}`")
    return 0


def cmd_build(args) -> int:
    if getattr(args, "all", False):
        if args.path is not None or getattr(args, "set", None):
            raise UserError("build --all takes no folder and no --set")
        return cmd_build_all(args)
    if args.path is None:
        raise UserError("build: give a model folder, or --all")
    module = load_model(args.path)
    restore = apply_overrides(module, getattr(args, "set", None))
    try:
        return _build(args, module)
    finally:
        restore()


def _build(args, module) -> int:
    import trimesh

    from cadlib.checks import check_mesh
    from cadlib.estimate import estimate
    from cadlib.export import DEFAULT_FORMATS, export_all, export_mesh
    from cadlib.meshio import load_mesh
    from cadlib.preview import render_preview

    t0 = time.perf_counter()
    profile = _profile(args)
    folder = args.path.resolve()
    name = getattr(module, "NAME", folder.name)
    formats = tuple(getattr(module, "FORMATS", DEFAULT_FORMATS))
    expected_bodies = int(getattr(module, "EXPECTED_BODIES", 1))
    print_down = _print_down(getattr(module, "PRINT_DOWN", None), "PRINT_DOWN")
    section = args.section or getattr(module, "SECTION", None)
    out_dir = folder / "out"
    source = folder / module.SOURCE if getattr(module, "SOURCE", None) else None
    if source is not None and not source.is_file():
        raise UserError(f"SOURCE = {module.SOURCE!r}: no such file in {_rel(folder)}")
    source_hash = _sha256(source) if source else None

    result = run_model(module, profile)
    if isinstance(result, trimesh.Trimesh):
        files = export_mesh(result, out_dir, name, formats)
    else:
        files = export_all(result, out_dir, name, formats)

    print(f"== {name} ({profile.printer}, nozzle {profile.nozzle_mm:g}, {profile.material})")
    for fmt, path in files.items():
        print(f"  {fmt.upper():4} {_rel(path)}  {path.stat().st_size / 1024:.0f} KB")

    mesh = load_mesh(files["stl"]) if "stl" in files else load_mesh(next(iter(files.values())))
    if getattr(args, "print_ready", False):
        if print_down is None:
            print("  print-ready: no PRINT_DOWN, the files already lie as printed (bottom on the bed)")
        else:
            from cadlib.checks import down_vector
            from cadlib.orient import label_for, print_ready

            turned = print_ready(mesh, print_down)
            export_mesh(turned, out_dir, name, tuple(f for f in formats if f != "step"))
            print(f"  print-ready: STL/3MF turned with {label_for(down_vector(print_down))} on the bed; STEP as designed")
    report = check_mesh(mesh, profile, expected_bodies, print_down)
    if "3mf" in files and "stl" in files:
        mesh_3mf = load_mesh(files["3mf"])
        for c in check_mesh(mesh_3mf, profile, expected_bodies).checks:
            # The 3MF is checked only for its own mesh (checks 1–2); bed and support are the same as the STL's.
            if c.level == "fail" and c.name.startswith(("1.", "2.")):
                report.add(f"3MF {c.name}", "fail", c.message)
    if source:
        _check_source(folder, source, source_hash, mesh, module, report)
    report.add("Weight", "info", estimate(mesh, profile).summary(profile))

    png = render_preview(mesh, out_dir / f"{name}.png", name, section=section, print_down=print_down)
    print(f"  PNG  {_rel(png)}")
    print()
    print(report.format())
    print()
    elapsed = time.perf_counter() - t0
    if report.failed:
        print(f"BUILD FAILED ({elapsed:.1f} s): fix the FAIL lines above.")
        return 1
    print(f"Done in {elapsed:.1f} s. Open the STL/3MF in Bambu Studio and make sure it shows no mesh warnings.")
    return 0


def _check_source(folder: Path, source: Path, hash_before: str, result_mesh, module, report) -> None:
    """The original is untouched (hash before/after the build and the one in SOURCE.md) + check 7."""
    from cadlib.checks import compare_to_original
    from cadlib.meshio import load_mesh

    if _sha256(source) != hash_before:
        report.add("Original", "fail", f"{_rel(source)} changed during the build: remix.py writes into source/")
    recorded = _recorded_hash(folder / "SOURCE.md")
    if recorded and recorded != hash_before:
        report.add("Original", "fail", f"the hash of {source.name} differs from SOURCE.md: the source was replaced or changed")
    elif recorded:
        report.add("Original", "ok", f"{source.name} unchanged (SHA-256 matches SOURCE.md)")
    compare_to_original(load_mesh(source), result_mesh, report, getattr(module, "EXPECTED_VOLUME_DELTA", None))


def _recorded_hash(source_md: Path) -> str | None:
    if not source_md.exists():
        return None
    match = re.search(r"SHA-256:\s*`?([0-9a-f]{64})", source_md.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_new_remix(args) -> int:
    from cadlib.meshio import SUPPORTED

    original = args.file.resolve()
    if not original.is_file():
        raise UserError(f"no such file: {args.file}")
    ext = original.suffix.lower()
    if ext not in SUPPORTED:
        raise UserError(f"format {ext} isn't supported, expected: {', '.join(SUPPORTED)}")
    folder = _new_folder("remix", args.name)
    source_dir = folder / "source"
    source_dir.mkdir()
    copy = source_dir / original.name
    shutil.copy2(original, copy)
    copy.chmod(stat.S_IREAD)  # read-only: an accidental write fails loudly
    digest = _sha256(copy)

    is_step = ext in (".step", ".stp")
    replacements = {"{{file}}": original.name, "{{sha256}}": digest}
    _render_template(TEMPLATES / ("remix_step.py" if is_step else "remix_mesh.py"), folder / "remix.py", args.name, replacements)
    _render_template(TEMPLATES / "remix_SOURCE.md", folder / "SOURCE.md", args.name, replacements)
    _render_template(TEMPLATES / "remix_README.md", folder / "README.md", args.name, replacements)

    print(f"Created: {_rel(folder)}  (source/{original.name} read-only, remix.py, SOURCE.md, README.md)")
    print("Fill in the link, the author and the licence in SOURCE.md.\n")
    return cmd_inspect(argparse.Namespace(file=copy))


def cmd_preview(args) -> int:
    import trimesh

    from cadlib.export import shape_to_mesh
    from cadlib.meshio import load_mesh
    from cadlib.preview import render_preview

    path = args.path.resolve()
    print_down = None
    if path.is_dir():
        module = load_model(path)
        restore = apply_overrides(module, getattr(args, "set", None))
        try:
            result = run_model(module, _profile(args))
        finally:
            restore()
        mesh = result if isinstance(result, trimesh.Trimesh) else shape_to_mesh(result)
        name = getattr(module, "NAME", path.name)
        section = args.section or getattr(module, "SECTION", None)
        print_down = _print_down(getattr(module, "PRINT_DOWN", None), "PRINT_DOWN")
        out = args.out or path / "out" / f"{name}.png"
    else:
        mesh = _load_file(path)
        name = path.stem
        section = args.section
        out = args.out or _out_dir_for(path) / f"{name}.png"
    render_preview(mesh, out, name, section=section, print_down=print_down)
    print(f"PNG: {_rel(out)}")
    return 0


def cmd_check(args) -> int:
    from cadlib.checks import check_mesh
    from cadlib.estimate import estimate

    mesh = _load_file(args.file)
    profile = _profile(args)
    report = check_mesh(mesh, profile, args.bodies, _print_down(args.down, "--down"))
    report.add("Weight", "info", estimate(mesh, profile).summary(profile))
    print(f"== {args.file.name}")
    print(report.format())
    return 1 if report.failed else 0


def cmd_inspect(args) -> int:
    from cadlib.info import describe

    mesh = _load_file(args.file)
    print(f"== {args.file.name}")
    rows = describe(mesh)
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"  {k:<{width}}  {v}")
    return 0


def cmd_orient(args) -> int:
    import trimesh

    from cadlib.checks import down_vector
    from cadlib.export import shape_to_mesh
    from cadlib.orient import label_for, print_ready, rank_orientations
    from cadlib.preview import render_preview

    profile = _profile(args)
    path = args.path.resolve()
    current = None
    if path.is_dir():
        module = load_model(path)
        restore = apply_overrides(module, getattr(args, "set", None))
        try:
            result = run_model(module, profile)
        finally:
            restore()
        mesh = result if isinstance(result, trimesh.Trimesh) else shape_to_mesh(result)
        name = getattr(module, "NAME", path.name)
        out_dir = path / "out"
        current = _print_down(getattr(module, "PRINT_DOWN", None), "PRINT_DOWN")
    else:
        mesh = _load_file(path)
        name = path.stem
        out_dir = _out_dir_for(path)

    ranked = rank_orientations(mesh, profile)
    current_label = label_for(down_vector(current)) if current is not None else "-Z"
    print(f"== {name}: {len(ranked)} candidate sides, best first (now printed with {current_label} on the bed)")
    print(f"  {'#':>2}  {'on the bed':<20} {'height':>8} {'base':>9} {'base %':>6} {'overhang':>8}  notes")
    for k, o in enumerate(ranked[: max(args.top, 1)], 1):
        mark = "  <- now" if o.label == current_label else ""
        notes = ", ".join(o.notes) or "-"
        print(f"  {k:>2}  {o.label:<20} {o.height_mm:>5.1f} mm {o.base_mm2:>6.0f} mm² {o.base_share * 100:>5.0f}% "
              f"{o.overhang_share * 100:>7.1f}%  {notes}{mark}")
        if not args.no_png:
            png = render_preview(print_ready(mesh, o.down), out_dir / f"{name}-orient-{k}.png",
                                 f"{name} #{k}: {o.label} on the bed")
            print(f"      PNG {_rel(png)}")
    best = ranked[0]
    if not best.fits_bed:
        print("No side fits the bed: the part needs splitting (cadlib.mesh.split_by_plane) or scaling.")
        return 1
    print(f"Best: PRINT_DOWN = {best.print_down}   (in model.py; for a file: check --down / build --print-ready)")
    return 0


def cmd_build_all(args) -> int:
    """Build every model folder with its own settings; print one line each and the failures in full."""
    folders = [ROOT / "calibration"] + sorted(
        d for base in ("parts", "remix") for d in (ROOT / base).glob("*") if d.is_dir()
    )
    folders = [d for d in folders if any((d / f).exists() for f in ENTRY_FILES)]
    if not folders:
        raise UserError("no model folders found")
    print(f"== building {len(folders)} models")
    failed = skipped = 0
    for folder in folders:
        buffer = io.StringIO()
        t0 = time.perf_counter()
        try:
            with contextlib.redirect_stdout(buffer):
                code = cmd_build(argparse.Namespace(
                    path=folder, all=False, section=None, print_ready=False, set=None,
                    nozzle=args.nozzle, material=args.material))
        except UserError as e:
            code = 2
            buffer.write(f"Error: {e}\n")
        except FileNotFoundError as e:
            from cadlib.logo import LogoMissing

            if not isinstance(e, LogoMissing):
                code = 3
                buffer.write(f"{type(e).__name__}: {e}\n")
            else:  # a logo-only part in a copy without the private logo data: nothing to build here
                skipped += 1
                print(f"  {_rel(folder):<40} {'skipped':<12}   no logo data in this copy")
                continue
        except Exception as e:  # noqa: BLE001  one broken model must not stop the rest
            code = 3
            buffer.write(f"{type(e).__name__}: {e}\n")
        text = buffer.getvalue()
        warns = text.count("[WARN]")
        status = {0: "ok", 1: "FAIL", 2: "error", 3: "crash"}.get(code, f"exit {code}")
        if status == "ok" and warns:
            status = f"ok, {warns} warn"
        print(f"  {_rel(folder):<40} {status:<12} {time.perf_counter() - t0:5.1f} s")
        if code:
            failed += 1
            for line in text.strip().splitlines()[-12:]:
                print(f"      {line}")
    built = len(folders) - failed - skipped
    print(f"{built} of {len(folders)} built" + (f", {failed} failed" if failed else "") + (f", {skipped} skipped" if skipped else ""))
    return 1 if failed else 0


# --- utilities --------------------------------------------------------------


def _load_file(path: Path):
    from cadlib.meshio import load_mesh

    if not path.is_file():
        raise UserError(f"no such file: {path}")
    try:
        return load_mesh(path)
    except ValueError as e:
        raise UserError(str(e)) from e


def _print_down(value, where: str):
    """The side for the bed from the model (PRINT_DOWN) or the flag (--down), checked up front."""
    if value is None:
        return None
    from cadlib.checks import down_vector

    try:
        down_vector(value)
    except ValueError as e:
        raise UserError(f"{where}: {e}") from e
    return value


def _out_dir_for(file: Path) -> Path:
    """PNGs for a file go into out/ next to it; nothing is written into source/."""
    parent = file.resolve().parent
    if parent.name == "out":  # a built file: its pictures go next to it, not into out/out/
        return parent
    return (parent.parent if parent.name == "source" else parent) / "out"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
