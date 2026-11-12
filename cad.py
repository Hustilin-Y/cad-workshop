"""CLI CAD-мастерской: `uv run cad.py <команда>`.

  new part <имя>    создать parts/<имя>/ из шаблона
  new remix <имя> <файл>  создать remix/<имя>/, оригинал в source/ (только чтение), сразу inspect
  build <папка>     собрать model.py/remix.py, экспорт, превью, проверки, отчёт
  preview <путь>    только PNG-превью (папка модели или файл STL/3MF/STEP)
  check <файл>      проверки любого файла, включая чужой
  inspect <файл>    габариты, объём, тела, основание, плоскости — перед ремиксом
"""

from __future__ import annotations

import argparse
import hashlib
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
    # Отчёт по-русски: без явного UTF-8 вывод в трубу (Git Bash, ssh, агент) идёт в cp1252 или ASCII и превращается в «?????».
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except UserError as e:
        print(f"Ошибка: {e}")
        return 2


class UserError(Exception):
    """Понятная пользователю ошибка без трейсбэка."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cad.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def profile_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--nozzle", type=float, help="сопло, мм (по умолчанию из printer.toml)")
        p.add_argument("--material", help="пластик: PLA/PETG/ABS/ASA (по умолчанию из printer.toml)")

    p = sub.add_parser("new", help="создать папку детали из шаблона")
    new_sub = p.add_subparsers(dest="kind", required=True)
    np_ = new_sub.add_parser("part", help="деталь с нуля: parts/<имя>/")
    np_.add_argument("name")
    np_.set_defaults(func=cmd_new_part)
    nr = new_sub.add_parser("remix", help="ремикс чужой модели: remix/<имя>/, оригинал копируется в source/")
    nr.add_argument("name")
    nr.add_argument("file", type=Path)
    nr.set_defaults(func=cmd_new_remix)

    p = sub.add_parser("build", help="собрать модель")
    p.add_argument("path", type=Path)
    p.add_argument("--section", choices=("x", "y", "z"), help="добавить разрез в превью (через центр)")
    profile_flags(p)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("preview", help="только превью")
    p.add_argument("path", type=Path)
    p.add_argument("--section", choices=("x", "y", "z"))
    p.add_argument("--out", type=Path, help="куда положить PNG")
    profile_flags(p)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("check", help="проверки файла")
    p.add_argument("file", type=Path)
    p.add_argument("--bodies", type=int, default=1, help="ожидаемое число тел")
    p.add_argument("--down", help="какая сторона модели ложится на стол: +x/-x/+y/-y/+z/-z (по умолчанию -z, как в файле)")
    profile_flags(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("inspect", help="сводка по файлу")
    p.add_argument("file", type=Path)
    p.set_defaults(func=cmd_inspect)
    return parser


# --- модель из папки ---------------------------------------------------------


def load_model(folder: Path) -> ModuleType:
    folder = folder.resolve()
    if not folder.is_dir():
        raise UserError(f"{folder} не папка; build ожидает parts/<имя> или remix/<имя>")
    entry = next((folder / f for f in ENTRY_FILES if (folder / f).exists()), None)
    if entry is None:
        raise UserError(f"в {folder} нет {' или '.join(ENTRY_FILES)}")
    spec = importlib.util.spec_from_file_location(f"cadmodel_{folder.name.replace('-', '_')}", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build"):
        raise UserError(f"в {entry.name} нет функции build(p)")
    return module


def run_model(module: ModuleType, profile):
    """Вызывает build(p) модели; результат — тело build123d или trimesh-сетка."""
    import trimesh
    from build123d import Shape

    try:
        result = module.build(profile)
    except ValueError as e:
        # _validate(p) модели и операции cadlib.mesh объясняют ошибку текстом; трейсбэк тут только мешает.
        raise UserError(f"модель не собралась: {e}") from e
    if not isinstance(result, (Shape, trimesh.Trimesh)):
        raise UserError(f"build() вернула {type(result).__name__}, нужно тело build123d или trimesh.Trimesh")
    return result


def _profile(args):
    from cadlib.config import load_profile

    try:
        return load_profile(nozzle=args.nozzle, material=args.material)
    except ValueError as e:
        raise UserError(str(e)) from e


# --- команды -----------------------------------------------------------------

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
        raise UserError(f"имя «{name}»: только строчные латинские буквы, цифры и дефис (например wall-hook)")
    folder = ROOT / kind_dir / name
    if folder.exists():
        raise UserError(f"{_rel(folder)} уже существует")
    folder.mkdir(parents=True)
    return folder


def cmd_new_part(args) -> int:
    folder = _new_folder("parts", args.name)
    _render_template(TEMPLATES / "part_model.py", folder / "model.py", args.name)
    _render_template(TEMPLATES / "part_README.md", folder / "README.md", args.name)
    print(f"Создано: {_rel(folder)}  (model.py, README.md)")
    print(f"Дальше: заполнить параметры в model.py и `uv run cad.py build {_rel(folder)}`")
    return 0


def cmd_build(args) -> int:
    import trimesh

    from cadlib.checks import check_mesh
    from cadlib.export import DEFAULT_FORMATS, export_all, export_mesh
    from cadlib.meshio import load_mesh
    from cadlib.preview import render_preview

    t0 = time.perf_counter()
    profile = _profile(args)
    module = load_model(args.path)
    folder = args.path.resolve()
    name = getattr(module, "NAME", folder.name)
    formats = tuple(getattr(module, "FORMATS", DEFAULT_FORMATS))
    expected_bodies = int(getattr(module, "EXPECTED_BODIES", 1))
    print_down = _print_down(getattr(module, "PRINT_DOWN", None), "PRINT_DOWN")
    section = args.section or getattr(module, "SECTION", None)
    out_dir = folder / "out"
    source = folder / module.SOURCE if getattr(module, "SOURCE", None) else None
    if source is not None and not source.is_file():
        raise UserError(f"SOURCE = {module.SOURCE!r}: файл не найден в {_rel(folder)}")
    source_hash = _sha256(source) if source else None

    result = run_model(module, profile)
    if isinstance(result, trimesh.Trimesh):
        files = export_mesh(result, out_dir, name, formats)
    else:
        files = export_all(result, out_dir, name, formats)

    print(f"== {name} ({profile.printer}, сопло {profile.nozzle_mm:g}, {profile.material})")
    for fmt, path in files.items():
        print(f"  {fmt.upper():4} {_rel(path)}  {path.stat().st_size / 1024:.0f} КБ")

    mesh = load_mesh(files["stl"]) if "stl" in files else load_mesh(next(iter(files.values())))
    report = check_mesh(mesh, profile, expected_bodies, print_down)
    if "3mf" in files and "stl" in files:
        mesh_3mf = load_mesh(files["3mf"])
        for c in check_mesh(mesh_3mf, profile, expected_bodies).checks[:3]:
            if c.level == "fail":
                report.add(f"3MF {c.name}", "fail", c.message)
    if source:
        _check_source(folder, source, source_hash, mesh, module, report)

    png = render_preview(mesh, out_dir / f"{name}.png", name, section=section)
    print(f"  PNG  {_rel(png)}")
    print()
    print(report.format())
    print()
    elapsed = time.perf_counter() - t0
    if report.failed:
        print(f"СБОРКА ПРОВАЛЕНА ({elapsed:.1f} с): исправьте ошибки FAIL выше.")
        return 1
    print(f"Готово за {elapsed:.1f} с. Откройте STL/3MF в Bambu Studio и убедитесь, что нет предупреждений о сетке.")
    return 0


def _check_source(folder: Path, source: Path, hash_before: str, result_mesh, module, report) -> None:
    """Оригинал не тронут (хэш до/после сборки и записанный в SOURCE.md) + проверка 7."""
    from cadlib.checks import compare_to_original
    from cadlib.meshio import load_mesh

    if _sha256(source) != hash_before:
        report.add("Оригинал", "fail", f"{_rel(source)} изменился во время сборки — remix.py пишет в source/")
    recorded = _recorded_hash(folder / "SOURCE.md")
    if recorded and recorded != hash_before:
        report.add("Оригинал", "fail", f"хэш {source.name} не совпадает с записанным в SOURCE.md — исходник подменён или изменён")
    elif recorded:
        report.add("Оригинал", "ok", f"{source.name} не изменён (SHA-256 совпадает с SOURCE.md)")
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
        raise UserError(f"файл не найден: {args.file}")
    ext = original.suffix.lower()
    if ext not in SUPPORTED:
        raise UserError(f"формат {ext} не поддерживается, нужны: {', '.join(SUPPORTED)}")
    folder = _new_folder("remix", args.name)
    source_dir = folder / "source"
    source_dir.mkdir()
    copy = source_dir / original.name
    shutil.copy2(original, copy)
    copy.chmod(stat.S_IREAD)  # только чтение: случайная запись упадёт с ошибкой
    digest = _sha256(copy)

    is_step = ext in (".step", ".stp")
    replacements = {"{{file}}": original.name, "{{sha256}}": digest}
    _render_template(TEMPLATES / ("remix_step.py" if is_step else "remix_mesh.py"), folder / "remix.py", args.name, replacements)
    _render_template(TEMPLATES / "remix_SOURCE.md", folder / "SOURCE.md", args.name, replacements)
    _render_template(TEMPLATES / "remix_README.md", folder / "README.md", args.name, replacements)

    print(f"Создано: {_rel(folder)}  (source/{original.name} только для чтения, remix.py, SOURCE.md, README.md)")
    print("Заполните в SOURCE.md ссылку, автора и лицензию.\n")
    return cmd_inspect(argparse.Namespace(file=copy))


def cmd_preview(args) -> int:
    import trimesh

    from cadlib.export import shape_to_mesh
    from cadlib.meshio import load_mesh
    from cadlib.preview import render_preview

    path = args.path.resolve()
    if path.is_dir():
        module = load_model(path)
        result = run_model(module, _profile(args))
        mesh = result if isinstance(result, trimesh.Trimesh) else shape_to_mesh(result)
        name = getattr(module, "NAME", path.name)
        section = args.section or getattr(module, "SECTION", None)
        out = args.out or path / "out" / f"{name}.png"
    else:
        mesh = _load_file(path)
        name = path.stem
        section = args.section
        out = args.out or _out_dir_for(path) / f"{name}.png"
    render_preview(mesh, out, name, section=section)
    print(f"PNG: {_rel(out)}")
    return 0


def cmd_check(args) -> int:
    from cadlib.checks import check_mesh

    mesh = _load_file(args.file)
    report = check_mesh(mesh, _profile(args), args.bodies, _print_down(args.down, "--down"))
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


# --- утилиты -----------------------------------------------------------------


def _load_file(path: Path):
    from cadlib.meshio import load_mesh

    if not path.is_file():
        raise UserError(f"файл не найден: {path}")
    try:
        return load_mesh(path)
    except ValueError as e:
        raise UserError(str(e)) from e


def _print_down(value, where: str):
    """Сторона на стол из модели (PRINT_DOWN) или флага (--down), проверенная заранее."""
    if value is None:
        return None
    from cadlib.checks import down_vector

    try:
        down_vector(value)
    except ValueError as e:
        raise UserError(f"{where}: {e}") from e
    return value


def _out_dir_for(file: Path) -> Path:
    """PNG для чужого файла кладём в out/ рядом; в source/ ничего не пишем."""
    parent = file.resolve().parent
    return (parent.parent if parent.name == "source" else parent) / "out"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
