# CAD workshop

One person's assistant designs parts for 3D printing and reworks downloaded models with [cad-workshop](https://github.com/Hustilin-Y/cad-workshop), then sends the PNG preview and the print files (3MF, STL, STEP) to their Telegram chat.

## What it needs

- A clone of cad-workshop in that person's folder, `~/workspaces/<name>/cad-workshop`.
- uv. `setup` installs the workshop's packages (about 0.95 GB in its `.venv`, 1.5 GB of uv cache) and `libgl1`, which OpenCascade loads even with no display.
- Memory: on a laptop CPU a build takes 10 to 60 seconds and up to about 0.7 GB; a downloaded model of a million triangles takes up to 1.2 GB.

## Setup

```sh
git clone https://github.com/Hustilin-Y/cad-workshop ~/workspaces/<name>/cad-workshop
~/workspaces/<name>/cad-workshop/multiclaude/install.sh      # --user <name>; the owner by default
assistant addon enable cad-workshop
```

`install.sh` copies this folder into the multiclaude checkout as `addons/cad-workshop/` and fills in the workshop's path and the person. Run it again after updating the clone; `install.sh --uninstall` turns the add-in off and takes it out.

## Files

- `rules.md`: what the assistants know while it's on: who uses it, where, and how it differs from working on a PC.
- `setup`: the packages, libGL, an import check.
