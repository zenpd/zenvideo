"""
One-time setup of the 3D conversation's people: Microsoft Rocketbox avatars (https://github.com/microsoft/Microsoft-Rocketbox,
MIT licence - keep its copyright notice with the assets) and their motion-captured animations.

    python -m explainer.rocketbox            # the avatars in explainer.office3d.AVATARS and their motions

Only what is needed is downloaded (a sparse, file-list-only clone; about 120 MB per avatar of textures before
conversion): each avatar's version with facial blendshapes (15 visemes, ARKit expressions) and its textures, which are
converted from TGA to JPG/PNG (browsers can't read TGA), into build/rocketbox/<Avatar>/, and the motions into
build/rocketbox/anims/. The clone is kept in build/rocketbox/_src so adding an avatar later is quick.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from explainer.office3d import ASSETS, AVATARS, MOTIONS

REPO = "https://github.com/microsoft/Microsoft-Rocketbox.git"
ANIMS = "Assets/Animations/all_animations_max_motextr_static"     # motions with the root kept in place


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def fetch(log=print) -> None:
    src = ASSETS / "_src"
    if not (src / ".git").exists():
        log("Cloning the Rocketbox file list (no files yet)...")
        src.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--filter=blob:none", "--no-checkout", "--depth", "1", REPO, str(src))
        _git("sparse-checkout", "init", "--no-cone", cwd=src)
    folders = {a["folder"] for a in AVATARS.values()}
    motions = {f for m in MOTIONS.values() for files in m.values() for f in files}
    patterns = ["LICENSE*", "README*"]
    patterns += [f"Assets/Avatars/Professions/{f}/Export/*_facial.fbx" for f in folders]
    patterns += [f"Assets/Avatars/Professions/{f}/Textures/*" for f in folders]
    patterns += [f"{ANIMS}/{m.replace('.fbx', '.max.fbx')}" for m in motions]
    (src / ".git" / "info" / "sparse-checkout").write_text("\n".join(patterns) + "\n", encoding="utf-8")
    log(f"Downloading {len(folders)} avatar(s) and {len(motions)} motion(s)...")
    _git("checkout", cwd=src)
    for key, a in AVATARS.items():
        base = src / "Assets" / "Avatars" / "Professions" / a["folder"]
        out = ASSETS / a["folder"]
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / "Export" / f"{a['folder']}_facial.fbx", out / "avatar.fbx")
        for t in (base / "Textures").glob("*.tga"):
            if "specular" in t.name:
                continue
            im = Image.open(t)
            if "opacity" in t.name:
                im.convert("RGBA").save(out / (t.stem + ".png"), optimize=True)
            else:
                im.convert("RGB").save(out / (t.stem + ".jpg"), quality=90)
        log(f"  {key}: {a['folder']} ready")
    (ASSETS / "anims").mkdir(exist_ok=True)
    for m in motions:
        shutil.copyfile(src / ANIMS / m.replace(".fbx", ".max.fbx"), ASSETS / "anims" / m)
    shutil.copyfile(src / "LICENSE.md", ASSETS / "LICENSE-Rocketbox.md")
    log(f"Rocketbox assets ready in {ASSETS}")


if __name__ == "__main__":
    fetch()
    sys.exit(0)
