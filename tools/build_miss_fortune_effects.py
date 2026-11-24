"""Convert particle inputs from the supplied Skin69 abilities ZIP for Isaac."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from struct import unpack_from
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
from cdtb.export import TexConverter
from PIL import Image, ImageChops, ImageOps


PARTICLES = "assets/characters/missfortune/skins/skin69/particles/"
SUFFIX = ".skins_missfortune_skin69."
DESTINATION = Path(__file__).resolve().parents[1] / "src/samira-testroom/mod/resources/gfx/mf"


def source_asset(archive, hashes, stem, extension="tex"):
    path = f"{PARTICLES}missfortune_skin69_{stem}{SUFFIX}{extension}"
    return checked_asset(archive, hashes, path)


def checked_asset(archive, hashes, path):
    data = archive.read(path)
    if sha256(data).hexdigest() != hashes[path]:
        raise ValueError(f"Skin69 manifest hash mismatch for {path}")
    return data


def texture(archive, hashes, stem):
    return decode(source_asset(archive, hashes, stem))


def decode(tex):
    with Image.open(BytesIO(TexConverter.tex_to_dds(tex))) as image:
        return image.convert("RGBA")


def bullet_image(mesh, material):
    # Skin69's supplied v3.2 SCB has positions and per-face UVs. Project the
    # shell side-on with the pointed end facing right and sample its own TEX.
    if mesh[:12] != b"r3d2Mesh\x03\x00\x02\x00":
        raise ValueError("Expected a Skin69 v3.2 SCB")
    vertex_count, face_count, flags = unpack_from("<III", mesh, 140)
    face_start = 192 + vertex_count * 12
    if flags != 2 or len(mesh) != face_start + face_count * 100:
        raise ValueError("Unexpected Skin69 SCB layout")
    xyz = np.array([unpack_from("<3f", mesh, 180 + i * 12) for i in range(vertex_count)])
    pixels = np.asarray(material)
    height, width = 64, 128
    sx = (xyz[:, 1] - xyz[:, 1].min()) * ((width - 4) / np.ptp(xyz[:, 1])) + 2
    sy = height / 2 - xyz[:, 0] * ((width - 4) / np.ptp(xyz[:, 1]))
    sy += max(0, 2 - sy.min())
    height = max(height, math.ceil(sy.max()) + 2)
    result = np.zeros((height, width, 4), np.uint8)
    depth = np.full((height, width), -np.inf)
    for i in range(face_count):
        start = face_start + i * 100
        corners = list(unpack_from("<3I", mesh, start))
        uvs = np.array(unpack_from("<6f", mesh, start + 76)).reshape(2, 3)
        ax, bx, cx = sx[corners]
        ay, by, cy = sy[corners]
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-8:
            continue
        left, right = math.floor(min(ax, bx, cx)), math.ceil(max(ax, bx, cx))
        top, bottom = math.floor(min(ay, by, cy)), math.ceil(max(ay, by, cy))
        y, x = np.mgrid[top:bottom, left:right] + .5
        a = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
        b = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
        weights = np.stack((a, b, 1 - a - b), axis=-1)
        z = weights @ xyz[corners, 2]
        region = depth[top:bottom, left:right]
        mask = (weights >= 0).all(axis=-1) & (z > region)
        if not mask.any():
            continue
        uv = weights[mask] @ uvs.T
        color = pixels[(uv[:, 1] * material.height).astype(int) % material.height,
                       (uv[:, 0] * material.width).astype(int) % material.width].copy()
        # Diffuse approximation for Isaac's flat sprite renderer.
        normal = np.cross(xyz[corners[1]] - xyz[corners[0]], xyz[corners[2]] - xyz[corners[0]])
        light = .77 + .23 * abs(normal[2]) / np.linalg.norm(normal)
        color[:, :3] = np.minimum(color[:, :3] * light * 1.45, 255)
        result[top:bottom, left:right][mask] = color
        region[mask] = z[mask]
    image = Image.fromarray(result)
    return image.crop(image.getbbox()).resize((28, 10), Image.Resampling.LANCZOS)


def crop(image, size):
    return image.crop(image.getbbox()).resize(size, Image.Resampling.LANCZOS)


def additive_to_rgba(image):
    # Use source intensity as coverage for textures authored with additive blending.
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint32)
    alpha = rgb.max(axis=2)
    straight = (rgb * 255 + alpha[..., None] // 2) // np.maximum(alpha[..., None], 1)
    return Image.fromarray(np.dstack((straight, alpha)).astype(np.uint8))


def tint(image, rgba):
    color = tuple(round(channel * 255) for channel in rgba)
    return ImageChops.multiply(image, Image.new("RGBA", image.size, color))


def shot_effects(archive, hashes, basic_glow=None):
    images, provenance = {}, {}

    def read(stem, extension):
        path = f"{PARTICLES}{stem}{SUFFIX}{extension}"
        return checked_asset(archive, hashes, path), {"path": path, "sha256": hashes[path]}

    def texture_sprite(name, effect, emitter, stem, size, rgba):
        tex, source = read(stem, "tex")
        image = decode(tex)
        if image.getchannel("A").getextrema() == (255, 255):
            image = additive_to_rgba(image)
        images[name] = tint(crop(image, size), rgba)
        provenance[name] = {"effect": effect, "emitter": emitter, "rgba": rgba, "sources": [source]}

    def ground_sprite(name, emitter, stem, rgba):
        tex, source = read(stem, "tex")
        mask, mask_source = read("zoe_skin20_aura_self", "tex")
        tile = decode(tex).resize((64, 64), Image.Resampling.LANCZOS)
        ground = Image.new("RGBA", (128, 128))
        for x, y in ((0, 0), (64, 0), (0, 64), (64, 64)):
            ground.paste(tile, (x, y))
        opacity = decode(mask).getchannel("A").resize(ground.size, Image.Resampling.LANCZOS)
        ground.putalpha(ImageChops.multiply(ground.getchannel("A"), opacity))
        images[name] = tint(ground, rgba)
        provenance[name] = {"effect": "83a848bd", "emitter": emitter, "rgba": rgba,
                            "uv_repeat": [2, 2], "sources": [source, mask_source]}

    def projectile(name, effect, stem, emitters, body_rgba, glint_rgba=(1, .76, .49, .45)):
        mesh, geometry = read(stem, "scb")
        material, skin = read("missfortune_skin69_q_bullet01", "tex")
        highlight, glint = read("masteryi_skin52_trails_03", "tex")
        body = tint(bullet_image(mesh, decode(material)), body_rgba)
        shine = tint(bullet_image(mesh, decode(highlight)), glint_rgba)
        images[name] = Image.alpha_composite(body, shine)
        provenance[name] = {"effect": effect, "emitters": emitters,
                            "body_rgba": body_rgba, "glint_rgba": glint_rgba,
                            "sources": [geometry, skin, glint]}

    projectile("QBullet", "5c7810ca", "missfortune_skin69_q_bullet01",
               ("bullets2", "bullets6"), (.634, 0, 0, 1))
    projectile("QDud", "6183dc78", "missfortune_skin69_q_bullet02",
               ("bullets2", "bullets4"), (.46, .02, 0, 1))
    projectile("RCore", "d2d2c9bc", "missfortune_skin69_q_bullet01",
               ("bullets", "bullets4"), (.519, .296, .142, 1))
    texture_sprite("AATrail", "f98fc5e2", "trail", "missfortune_skin69_trail",
                   (64, 12), (.936, .707, .270, 1))
    # The AA Glow emitter's BasicGlow texture is absent from the supplied ZIP.
    # Front_Glow_Alpha1 is an available, separately authored AA emitter.
    texture_sprite("AAGlow", "f98fc5e2", "Front_Glow_Alpha1", "missfortune_skin21_ball32_02",
                   (40, 40), (1, 0, 0, .4))
    if basic_glow:
        data, source = basic_glow
        image = decode(data)
        if image.getchannel("A").getextrema() == (255, 255):
            image = additive_to_rgba(image)
        rgba = (.9367, .6313, .2496, .4)
        images["AABasicGlow"] = tint(crop(image, (40, 40)), rgba)
        provenance["AABasicGlow"] = {"effect": "f98fc5e2", "emitter": "Glow",
                                     "rgba": rgba, "sources": [source]}
    texture_sprite("RGlow", "d2d2c9bc", "ProjectedLight", "3161glow",
                   (40, 40), (1, .6645, .1614, .302))
    texture_sprite("AACast", "7495d294", "Flash", "missfortune_skin50_ba_flash_sharp_01",
                   (38, 38), (.790, .483, .280, .502))
    texture_sprite("AACritCast", "7c0942a9", "Flash", "missfortune_skin50_ba_flash_sharp_01",
                   (42, 42), (.784, .561, .166, 1))
    texture_sprite("AACritSpark", "7c0942a9", "Flash1", "vayne_skin64_sparkle",
                   (34, 34), (.944, .596, .231, 1))
    texture_sprite("QGlow", "5c7810ca", "bullets_OuterGlow", "3161glow",
                   (46, 32), (.901, .610, .304, .8))
    texture_sprite("QCast", "9c2a03a4", "Flash", "missfortune_skin50_ba_flash_sharp_01",
                   (48, 48), (1, .737, .183, .302))
    texture_sprite("QImpact", "e40b94f6", "Flash", "vayne_skin64_sparkle",
                   (36, 36), (.98, .75, .33, 1))
    texture_sprite("QSecondImpact", "b696c2b7", "Basic", "missfortune_skin50_ba_flash_sharp_01",
                   (44, 44), (.84, .60, .23, 1))
    ground_sprite("RainGround", "AOE_Indicator", "missfortune_skin69_groundt1", (.09, .09, .17, 1))
    ground_sprite("RainGold", "AOE_Indicator1", "missfortune_skin69_r_ground01", (1, .671, .384, 1))
    texture_sprite("RainRingGlow", "83a848bd", "ProjectionRing2", "missfortune_skin69_e_teamring_blur",
                   (128, 128), (.768, .468, .242, 1))
    texture_sprite("RainStreak", "74c6e72c", "Trail1", "missfortune_skin69_e_trail_01",
                   (64, 16), (.95, .574, .268, 1))
    texture_sprite("RainImpact", "7f1dcbdc", "Flash", "missfortune_skin50_ba_flash_sharp_01",
                   (38, 38), (1, .602, .241, 1))
    texture_sprite("RainImpactGlow", "7f1dcbdc", "Glow_Add", "3161glow",
                   (40, 40), (1, .68, .31, .6))
    projectile("RainCore", "6414b462", "missfortune_skin69_q_bullet01",
               ("bullets1", "bullets2"), (.67, .28, .22, 1), (.81, .56, .37, .3))
    return images, provenance


def atlas_sprites(archive, hashes):
    bullet = bullet_image(source_asset(archive, hashes, "q_bullet01", "scb"),
                          texture(archive, hashes, "q_bullet01"))
    trail = ImageOps.mirror(crop(texture(archive, hashes, "q_trail02"), (53, 10)))
    rain = crop(texture(archive, hashes, "e_trail").rotate(-90, expand=True), (39, 7))
    ring = texture(archive, hashes, "e_teamring_green").resize((170, 170), Image.Resampling.LANCZOS)
    sheet = texture(archive, hashes, "q_tar_light01")
    impact = crop(sheet.crop((0, 0, sheet.width // 2, sheet.height // 2)), (24, 26))
    flash = texture(archive, hashes, "cast_muzzleflash_01")
    flash = flash.crop((0, 0, flash.width // 2, flash.height // 2)).convert("L")
    muzzle = Image.new("RGBA", flash.size, "white")
    muzzle.putalpha(flash)
    sparkles = texture(archive, hashes, "e_sparklies_02").resize((32, 32), Image.Resampling.LANCZOS)
    return {"Ring": ring, "Bullet": bullet, "Trail": trail, "Rain": rain,
            "Impact": impact, "Muzzle": crop(muzzle, (32, 22)), "Sparkles": sparkles}


def write_atlas(images, name, size, default_animation):
    actor = ET.Element("AnimatedActor")
    ET.SubElement(actor, "Info", Version="1", Fps="30")
    content = ET.SubElement(actor, "Content")
    sheets = ET.SubElement(content, "Spritesheets")
    ET.SubElement(sheets, "Spritesheet", Path=f"{name}.png", Id="0")
    layers = ET.SubElement(content, "Layers")
    ET.SubElement(layers, "Layer", Name="Particle", Id="0", SpritesheetId="0")
    ET.SubElement(content, "Nulls")
    ET.SubElement(content, "Events")
    animations = ET.SubElement(actor, "Animations", DefaultAnimation=default_animation)
    atlas = Image.new("RGBA", size)
    x, y, next_row = 0, 0, 0
    settings = {"XScale": "100", "YScale": "100", "Delay": "1", "Visible": "true",
                "RedTint": "255", "GreenTint": "255", "BlueTint": "255", "AlphaTint": "255",
                "RedOffset": "0", "GreenOffset": "0", "BlueOffset": "0", "Rotation": "0",
                "Interpolated": "false", "XPosition": "0", "YPosition": "0"}
    for animation_name, image in images.items():
        width, height = image.size
        if x + width > atlas.width:
            x, y = 0, next_row
        if width > atlas.width or y + height > atlas.height:
            raise ValueError(f"{animation_name} exceeds the {name} atlas")
        atlas.paste(image, (x, y))
        animation = ET.SubElement(animations, "Animation", Name=animation_name, FrameNum="1", Loop="true")
        ET.SubElement(ET.SubElement(animation, "RootAnimation"), "Frame", settings)
        layer = ET.SubElement(ET.SubElement(animation, "LayerAnimations"), "LayerAnimation",
                              LayerId="0", Visible="true")
        ET.SubElement(layer, "Frame", settings, XCrop=str(x), YCrop=str(y),
                      Width=str(width), Height=str(height), XPivot=str(width // 2), YPivot=str(height // 2))
        ET.SubElement(animation, "NullAnimations")
        ET.SubElement(animation, "Triggers")
        x += width + 2
        next_row = max(next_row, y + height + 2)
    atlas.save(DESTINATION / f"{name}.png")
    ET.indent(actor, space="    ")
    ET.ElementTree(actor).write(DESTINATION / f"{name}.anm2", encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("abilities_zip", type=Path)
    parser.add_argument("--wad", type=Path, help="Optional local PBE MissFortune WAD for the AA Glow texture")
    parser.add_argument("--shots-only", action="store_true", help="Rebuild only the shot atlas and its provenance")
    args = parser.parse_args()
    basic_glow = None
    if args.wad:
        from import_yone_assets import Wad, archive_hash, wad_hash
        wad_digest = archive_hash(args.wad)
        if wad_digest != "ec155cda0e61f3cea58d2fb775746b0143d5c12b9d9da80b60618889f4b4d362":
            raise ValueError("Unexpected PBE MissFortune WAD SHA-256")
        path = f"{PARTICLES}missfortune_basicglow{SUFFIX}tex"
        member = next((item for item in Wad(args.wad, hashes={}).files if item.path_hash == wad_hash(path)), None)
        if member is None:
            raise ValueError(f"Missing {path} in PBE WAD")
        with args.wad.open("rb") as stream:
            data = member.read_data(stream)
        digest = sha256(data).hexdigest()
        if digest != "a149b7aa748011e97719db565e46ac379b9d0b934cc8b20f4705e0d933c4e27f":
            raise ValueError(f"Unexpected source hash for {path}")
        basic_glow = data, {"path": path, "sha256": digest,
                            "archive": "PBE MissFortune.wad.client", "archive_sha256": wad_digest}
    with ZipFile(args.abilities_zip) as archive:
        hashes = json.loads(archive.read("manifest.json"))["assets"]
        if not args.shots_only:
            write_atlas(atlas_sprites(archive, hashes), "projectiles", (256, 256), "Bullet")
        shots, sources = shot_effects(archive, hashes, basic_glow)
        write_atlas(shots, "shot_effects", (512, 320), "QBullet")
        provenance = {"archive": args.abilities_zip.name, "sha256": sha256(args.abilities_zip.read_bytes()).hexdigest(),
                      "conversion": "SCB side projection and source TEX with emitter tint", "sprites": sources}
        provenance["rain_trophies"] = {
            "effect": "83a848bd", "emitter": "Parent",
            "source": "recall_effects.provenance.json",
            "children": {"59761bb0": "RecallTrophy2024", "5c762069": "RecallTrophy2025",
                         "5b761ed6": "RecallTrophyFMVP"},
        }
        (DESTINATION / "shot_effects.provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        # Use the supplied P_Mark_BG layer directly. The graph also references
        # P_Mark and P_Mark01, which are absent from this archive.
        if not args.shots_only:
            mark = texture(archive, hashes, "p_mark_bg")
            write_atlas({"Mark": mark}, "passive", mark.size, "Mark")
