"""Assemble the personal Windows bundle; never starts Isaac or its renderer."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("overlay model bridge layered_surface samira_vfx client_vfx canvas system_pointer samira_audio "
           "combat_effects hud status visibility native_cursor shop_ui localization mastery_renderer mastery_glb "
           "mastery_particles yone_combat_audio yone_vfx display_geometry").split()
YONE_FILES = ("yone.glb", "actions.json", "rig-events.json")
MF_FILES = ("mf.glb", "actions.json", "rig-events.json")
YONE_AUDIO = (
    "manifest.json", "joke.wav", "taunt.wav", "dance.wav", "dance_loop.wav", "laugh.wav",
    "attack.wav", "attack2.wav", "q.wav", "q3.wav", "w.wav", "e.wav", "e_return.wav", "r.wav", "shield.wav",
)


def build(output, *, include_local_yone=False, include_local_mf=False, staging_area=None,
          python_runtime=None, yone_assets=None, dependency_archive=None, version=None):
    python_runtime = python_runtime or ROOT / "work/export-runtime/python"
    yone_assets = yone_assets or ROOT / "assets/yone-local"
    mf_assets = ROOT / "assets/mf-local"
    version = version or ET.parse(ROOT / "src/samira-testroom/mod/metadata.xml").findtext("version")
    if not version or any(c not in "0123456789.-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in version):
        raise ValueError("Invalid release version")
    dependency_zip = zipfile.ZipFile(dependency_archive) if dependency_archive else None
    if dependency_zip and dependency_zip.testzip():
        raise ValueError("Dependency archive failed CRC verification")
    def dependency_member(relative):
        return "Soul-Fighter-Samira/companion/" + relative
    def has_yone(name):
        return (yone_assets / name).is_file() or bool(dependency_zip and dependency_member("assets/yone-local/" + name) in dependency_zip.namelist())
    if include_local_yone:
        missing = [name for name in YONE_FILES if not has_yone(name)]
        if missing:
            raise FileNotFoundError("Run tools/import_yone_assets.py first. Missing from assets/yone-local: "
                                    + ", ".join(missing))
    if include_local_mf:
        missing = [name for name in MF_FILES if not (mf_assets / name).is_file()]
        if missing:
            raise FileNotFoundError("Run tools/import_miss_fortune_assets.py first. Missing files: "
                                    + ", ".join(missing))
    output.mkdir(parents=True, exist_ok=True)
    dedicated_stage = staging_area is not None
    if staging_area is None:
        stage_name = "friend-export-yone-local" if include_local_yone else "friend-export"
        staging_area = ROOT / "work" / ("miss-fortune-local" if include_local_mf else stage_name)
    stage = staging_area / "Soul-Fighter-Samira"
    if stage.exists():
        if dedicated_stage:
            raise FileExistsError(f"Choose a fresh staging directory: {staging_area}")
        assert stage.resolve().parent == staging_area.resolve()
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    def copy(source, target):
        source = ROOT / source
        target = stage / target
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(source, target)

    copy("src/samira-testroom/mod", "samira_testroom")
    copy(python_runtime, "companion/python")
    # NumPy build command launchers encode the build machine's interpreter path.
    for name in ("bin", "include"):
        tooling = stage / "companion/python/Lib/site-packages" / name
        if tooling.exists():
            assert tooling.resolve().is_relative_to(stage.resolve())
            shutil.rmtree(tooling)
    for name in MODULES:
        copy(f"src/samira/external/{name}.py", f"companion/src/samira/external/{name}.py")
    for name in ("mf_renderer", "mf_taunt_doll", "mf_muzzle"):
        path = f"src/samira/external/{name}.py"
        if (ROOT / path).is_file():
            copy(path, f"companion/{path}")
    copy("src/samira/external/assets", "companion/src/samira/external/assets")
    copy("src/samira-testroom/mod/resources/gfx/mf", "companion/src/samira-testroom/mod/resources/gfx/mf")
    for name in ("model.glb", "rig-events.json"):
        copy(f"src/samira/reference/source/{name}", f"companion/src/samira/reference/source/{name}")
    copy("tools/run_testroom_renderer.py", "companion/tools/run_testroom_renderer.py")
    copy("src/samira-testroom/visual-settings.json", "companion/src/samira-testroom/visual-settings.json")
    for name in ("audio", "vfx", "manifest.json"):
        copy(f"assets/samira-soul-fighter/{name}", f"companion/assets/samira-soul-fighter/{name}")
    if include_local_yone:
        if dependency_zip:
            prefix = dependency_member("assets/yone-local/")
            for member in dependency_zip.namelist():
                if member.startswith(prefix) and not member.endswith("/"):
                    relative = Path(member[len(prefix):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("Unsafe dependency member")
                    target = stage / "companion/assets/yone-local" / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(dependency_zip.read(member))
        for name in YONE_FILES:
            if (yone_assets / name).is_file():
                copy(yone_assets / name, f"companion/assets/yone-local/{name}")
        local_vfx = ROOT / "assets/yone-local/vfx"
        vfx = local_vfx if local_vfx.is_dir() else yone_assets / "vfx"
        if vfx.is_dir():
            copy(vfx, "companion/assets/yone-local/vfx")
        for name in YONE_AUDIO:
            if (yone_assets / "audio" / name).is_file():
                copy(yone_assets / "audio" / name, f"companion/assets/yone-local/audio/{name}")
        if (yone_assets / "yone-portrait.png").is_file():
            copy(yone_assets / "yone-portrait.png", "samira_testroom/resources/gfx/samira/yone-portrait.png")
    if include_local_mf:
        for name in MF_FILES:
            copy(mf_assets / name, f"companion/assets/mf-local/{name}")
        doll = mf_assets / "taunt-doll"
        if doll.is_dir():
            copy(doll, "companion/assets/mf-local/taunt-doll")
        copy("docs/miss-fortune-audio.lock.json", "provenance/miss-fortune-audio.lock.json")
        copy("docs/miss-fortune-hud.lock.json", "provenance/miss-fortune-hud.lock.json")
    for name in ("yone-ability-icons.lock.json", "yone-progression-hud.lock.json", "yone-spirit-audio.lock.json", "items-icons.lock.json", "components-data.lock.json",
                 "components-icons.lock.json"):
        copy(f"docs/{name}", f"provenance/{name}")
    for source, target in (("export-launcher.cmd", "launch.cmd"), ("export-launcher.ps1", "launcher.ps1"), ("export-INSTALL.txt", "INSTALL.txt")):
        copy(f"tools/{source}", target)
    for source, target in (("export-stop.cmd", "stop.cmd"), ("export-stop.ps1", "stop.ps1")):
        if (ROOT / "tools" / source).exists():
            copy(f"tools/{source}", target)
    (stage / "companion/work").mkdir(parents=True, exist_ok=True)
    (stage / "CREDITS.txt").write_text(
        "Soul Fighter Samira — personal experimental mod.\n"
        "League of Legends character, model, animations, sounds and original artwork: Riot Games.\n"
        "Framework and external renderer adapted from TFOS4 Isaac-LoL-HeroStudio:\n"
        "https://github.com/TFOS4/Isaac-LoL-HeroStudio\n"
        "https://github.com/TFOS4/Isaac-LoL-HeroStudio/releases/tag/v1.0.0\n"
        "Asset provenance is retained in companion/assets/samira-soul-fighter manifests.\n"
        "Yone ability icon provenance: provenance/yone-ability-icons.lock.json.\n"
        "Yone keystone icons and HUD texture crops: provenance/yone-progression-hud.lock.json.\n"
        "Yone spirit warning provenance: provenance/yone-spirit-audio.lock.json.\n"
        "Item and component artwork: provenance/items-icons.lock.json and provenance/components-icons.lock.json.\n"
        "Riot Data Dragon component recipes: provenance/components-data.lock.json.\n"
        "Python and dependency notices/licenses accompany companion/python.\n"
        "Liberation font license: samira_testroom/resources/font/LIBERATION-LICENSE.txt.\n"
        "No blanket license is granted for third-party materials.\n"
        + ("Summoner's Rift shopkeeper and visual provenance: "
           "samira_testroom/resources/gfx/league_shop/sources.json.\n"
           if (ROOT / "src/samira-testroom/mod/resources/gfx/league_shop/sources.json").is_file() else "")
        + ("Classic Yone materials were imported locally from the user's League of Legends installation.\n"
           if include_local_yone else "")
        + ("The Yone effects bundle uses materials supplied in the user's classic ability visual archive.\n"
           if include_local_yone and (vfx / "manifest.json").is_file() else "")
        + ("MVP T1 Miss Fortune model and animation source checksums are recorded in companion/assets/mf-local/rig-events.json.\n"
           "Miss Fortune sound provenance: provenance/miss-fortune-audio.lock.json.\n"
           "Miss Fortune HUD artwork provenance: provenance/miss-fortune-hud.lock.json.\n"
           "Miss Fortune Homeguard and Pentakill effect provenance: samira_testroom/resources/gfx/mf/special_effects.provenance.json.\n"
           "Miss Fortune Bullet Time effect provenance: samira_testroom/resources/gfx/mf/ultimate_effects.provenance.json.\n"
           "Miss Fortune shot effect provenance: samira_testroom/resources/gfx/mf/shot_effects.provenance.json.\n"
           "Miss Fortune Recall effect provenance: samira_testroom/resources/gfx/mf/recall_effects.provenance.json.\n"
           "Miss Fortune Recall props and pet provenance: samira_testroom/resources/gfx/mf/recall_props.provenance.json and recall_pet.provenance.json.\n"
           "Miss Fortune Joke effect provenance: samira_testroom/resources/gfx/mf/joke_effects.provenance.json.\n"
           "Miss Fortune Dance effect provenance: samira_testroom/resources/gfx/mf/dance_effects.provenance.json.\n"
           "Miss Fortune Death and Respawn effect provenance: samira_testroom/resources/gfx/mf/lifecycle_effects.provenance.json.\n"
           if include_local_mf else ""), encoding="utf-8")
    dependency_info = {
        "version": version,
        "python_runtime": {"python_exe_sha256": hashlib.sha256((python_runtime / "python.exe").read_bytes()).hexdigest()},
        "dependency_archive": ({"name": dependency_archive.name, "sha256": hashlib.sha256(dependency_archive.read_bytes()).hexdigest(),
                                "used_prefix": dependency_member("assets/yone-local/")} if dependency_archive else None),
    }
    (stage / "BUILD.json").write_text(json.dumps(dependency_info, indent=2), encoding="utf-8")
    if dependency_zip:
        dependency_zip.close()
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    manifest = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_name = "Soul-Fighter-Samira-0.3.2-Windows.zip"
    if include_local_mf:
        archive_name = f"Soul-Fighter-Miss-Fortune-{version}-Windows-Test.zip"
    elif include_local_yone:
        archive_name = "Soul-Fighter-Samira-Yone-Local-Windows.zip"
    archive = output / archive_name
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(stage.parent).as_posix(), (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, path.read_bytes(), compresslevel=6)
        info = zipfile.ZipInfo("Soul-Fighter-Samira/companion/work/", (2020, 1, 1, 0, 0, 0))
        info.external_attr = 0o40755 << 16
        z.writestr(info, "")
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"Corrupt archive member: {bad}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files) + 1, "sha256": digest}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--staging-area", type=Path, help="Use a fresh directory for the temporary release tree.")
    parser.add_argument("--include-local-yone", action="store_true",
                        help="Include the locally imported classic Yone model in a personal ZIP.")
    parser.add_argument("--include-local-mf", action="store_true",
                        help="Include the supplied Miss Fortune model in a personal ZIP.")
    parser.add_argument("--python-runtime", type=Path, help="Path to the prepared embedded Python installation.")
    parser.add_argument("--yone-assets", type=Path, help="Path to the locally imported Yone assets.")
    parser.add_argument("--dependency-archive", type=Path, help="Verified prior portable ZIP; reuse only Yone asset files, never old code.")
    parser.add_argument("--version", help="Package version (defaults to mod metadata.xml).")
    arguments = parser.parse_args()
    build(arguments.output, include_local_yone=arguments.include_local_yone, include_local_mf=arguments.include_local_mf,
          staging_area=arguments.staging_area, python_runtime=arguments.python_runtime, yone_assets=arguments.yone_assets,
          dependency_archive=arguments.dependency_archive, version=arguments.version)
