"""Miss Fortune's authored muzzle sprites at animated weapon sockets."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
from canvas import Canvas


SPRITES = {
    'attack': ('AACast', .40, .40),
    'attack2': ('AACast', .40, .40),
    'crit': ('AACritCast', .43, .43),
    'q': ('QCast', .53, .53),
    'r': ('RMuzzle', .20, .18),
}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _point(value):
    return isinstance(value, (tuple, list)) and len(value) == 2 and all(_number(n) for n in value)


def _load_frames(canvas, root, basename, names):
    tree = ET.parse(root / (basename + '.anm2'))
    sheet = tree.find('./Content/Spritesheets/Spritesheet')
    if sheet is None or sheet.get('Path') != basename + '.png':
        raise ValueError('Invalid muzzle spritesheet reference: ' + basename)
    with Image.open(root / sheet.get('Path')) as source:
        source.load()
        for name in names:
            animation = tree.find("./Animations/Animation[@Name='%s']" % name)
            frame = animation.find('./LayerAnimations/LayerAnimation/Frame') if animation is not None else None
            if frame is None:
                raise ValueError('Missing muzzle frame: ' + name)
            x, y, w, h, px, py = (int(frame.attrib[key]) for key in
                                   ('XCrop', 'YCrop', 'Width', 'Height', 'XPivot', 'YPivot'))
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > source.width or y + h > source.height:
                raise ValueError('Invalid muzzle crop: ' + name)
            crop = source.crop((x, y, x + w, y + h)).convert('RGBA')
            if not crop.getchannel('A').getbbox():
                raise ValueError('Empty muzzle frame: ' + name)
            canvas.add(name, crop)
            yield name, (w, h, px, py)


class MuzzleFlashes:
    def __init__(self, ctx, asset_dir):
        self.canvas = Canvas(ctx, asset_dir, font=False)
        try:
            root = Path(asset_dir)
            self.frames = dict(_load_frames(self.canvas, root, 'shot_effects',
                                            ('AACast', 'AACritCast', 'AACritSpark', 'QCast')))
            self.frames.update(_load_frames(self.canvas, root, 'ultimate_effects', ('RMuzzle',)))
        except Exception:
            self.canvas.close()
            raise

    def _sprite(self, name, point, direction, sx, sy, alpha):
        w, h, px, py = self.frames[name]
        dx, dy = direction
        corners = []
        for x, y in ((-px, -py), (w-px, -py), (w-px, h-py), (-px, h-py)):
            x, y = x * sx, y * sy
            corners.append((point[0] + x*dx - y*dy, point[1] + x*dy + y*dx))
        self.canvas.polygon(corners, (1, 1, 1, alpha), name,
                            [(0, 0), (1, 0), (1, 1), (0, 1)])

    def draw(self, state, points):
        if not isinstance(state, dict) or not isinstance(points, dict):
            return
        cue = state.get('mfMuzzle')
        screen = state.get('screen')
        clock = state.get('clock')
        if not isinstance(cue, dict) or not _point(screen) or min(screen) <= 0 or not _number(clock):
            return
        kind, start, finish = cue.get('kind'), cue.get('start'), cue.get('finish')
        if not isinstance(kind, str) or kind not in SPRITES or not _number(start) or not _number(finish) or finish <= start:
            return
        if clock < start or clock >= finish:
            return
        if kind == 'r':
            gun = cue.get('gun')
            if type(gun) is not int or gun not in (1, 2):
                return
            sides = ('right',) if gun == 1 else ('left',)
        else:
            sides = ('left',) if kind == 'attack2' else ('right', 'left') if kind == 'crit' else ('right',)
        sockets = []
        for side in sides:
            p, f = points.get(side), points.get(side + '_forward')
            if not _point(p) or not _point(f):
                return
            dx, dy = f[0]-p[0], f[1]-p[1]
            length = math.hypot(dx, dy)
            if not math.isfinite(length) or length <= 1e-9:
                return
            sockets.append((p, (dx/length, dy/length)))
        age = max(0., clock - start)
        alpha = max(0., 1 - age / (finish - start))
        if kind == 'r':
            alpha = .88 * max(0., 1 - age / 2)
        if alpha <= 0:
            return
        image, sx, sy = SPRITES[kind]
        self.canvas.begin(screen)
        for point, direction in sockets:
            self._sprite(image, point, direction, sx, sy, alpha)
            if kind == 'crit':
                self._sprite('AACritSpark', point, direction, .28, .28, .68*alpha)
        self.canvas.flush()

    def close(self):
        if self.canvas:
            self.canvas.close()
            self.canvas = None
