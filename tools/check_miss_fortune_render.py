"""Exercise the actual MF GPU renderer without starting Isaac or opening a window."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/samira/external'))
import moderngl
from PIL import Image, ImageDraw
from mf_renderer import MissFortuneRenderer
from mf_muzzle import MuzzleFlashes


class RecordedCanvas:
    def __init__(self):
        self.draws = []

    def begin(self, screen):
        pass

    def polygon(self, *args):
        self.draws.append(args)

    def flush(self):
        pass


def check_muzzle_window():
    flashes = MuzzleFlashes.__new__(MuzzleFlashes)
    flashes.canvas = RecordedCanvas()
    flashes.frames = {'QCast': (32, 32, 16, 16)}
    state = dict(screen=[800, 600], mfMuzzle=dict(kind='q', start=10, finish=14))
    sockets = dict(right=[100, 100], right_forward=[120, 100])
    for clock, count in [(9, 0), (10, 1), (13, 1), (14, 0)]:
        flashes.canvas.draws.clear()
        flashes.draw(dict(state, clock=clock), sockets)
        assert len(flashes.canvas.draws) == count, (clock, count)


def main():
    check_muzzle_window()
    output = ROOT / 'work/mf-render-audit'
    output.mkdir(parents=True, exist_ok=True)
    with moderngl.create_standalone_context(require=330) as ctx:
        size = (512, 512)
        frame = ctx.framebuffer([ctx.texture(size, 4)], ctx.depth_renderbuffer(size))
        renderer = MissFortuneRenderer(ctx, ROOT / 'assets/mf-local/mf.glb',
                                      ROOT / 'src/samira-testroom/mod/resources/gfx/mf')
        assert renderer.actor and renderer.muzzles and renderer.taunt_doll.actor
        clips = renderer.actor.model.durations
        sheet = Image.new('RGB', (8*160, math.ceil(len(clips)/8)*180), (22, 24, 32))
        checks = []
        for index, clip in enumerate(clips):
            for direction in range(8):
                for phase in (0., .25, .5, .75, .99):
                    renderer.reset()
                    frame.use()
                    ctx.viewport = (0, 0, *size)
                    frame.clear(0, 0, 0, 0)
                    angle = direction * math.tau/8
                    state = dict(kind=clip, clip=clip, actionFrame=phase*clips[clip]*30,
                                 clock=phase*clips[clip]*30, position=[256, 340], screen=list(size),
                                 face=[math.cos(angle), math.sin(angle)])
                    if clip in ('attack', 'attack2', 'crit', 'q', 'r'):
                        state['mfMuzzle'] = dict(kind=clip, start=state['clock'],
                                                finish=state['clock']+4, gun=1)
                    if clip in ('taunt_spam', 'taunt_loop'):
                        state['expression'] = 'taunt_spam'
                        if clip == 'taunt_loop':
                            state['actionFrame'] += clips['taunt_spam']*30
                    ok, capabilities = renderer.draw(state, 1/30)
                    assert ok and capabilities.get('mfMuzzle'), (clip, direction, phase)
                    assert ctx.error == 'GL_NO_ERROR', (clip, direction, phase)
                    image = Image.frombytes('RGBA', size, frame.read(components=4)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    box = image.getbbox()
                    if box is None:
                        events = renderer.actor.model.active_events(clip, phase)
                        assert clip == 'respawn' and any('Body' in event.get('mHideSubmeshList', ()) for event in events)
                    else:
                        assert 0 < box[0] < box[2] < size[0] and 0 < box[1] < box[3] < size[1], (clip, box)
                    checks.append(dict(clip=clip, direction=direction, phase=phase, bbox=box))
                    if direction == 1 and phase == .5 and box:
                        crop = image.crop(box)
                        crop = crop.resize((crop.width*3, crop.height*3), Image.Resampling.NEAREST)
                        crop.thumbnail((150, 148))
                        x, y = index%8*160, index//8*180
                        sheet.paste(crop, (x+(160-crop.width)//2, y+22), crop)
                        ImageDraw.Draw(sheet).text((x+4,y+4), clip, fill=(245,225,185))
        report = dict(scope='Actual GPU rendering, no live Isaac gameplay', gpu=ctx.info['GL_RENDERER'],
                      clips=len(clips), frames=len(checks), muzzle_timing='passed', samples=checks)
        (output / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
        sheet.save(output / 'contact-sheet.png')
        renderer.close()
        frame.release()
        print(json.dumps({key:value for key,value in report.items() if key != 'samples'}))


if __name__ == '__main__':
    main()
