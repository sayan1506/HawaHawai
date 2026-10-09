"""Rasterize the existing wind-mark geometry for browser install icons, using stdlib."""
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'frontend/public'
segments = [(52, 70, 123, 70), (52, 96, 137, 96), (52, 122, 104, 122)]
arcs = [(123, 58, 12, -math.pi / 2, math.pi / 2), (137, 108, 12, -math.pi / 2, math.pi / 2), (104, 134, 12, -math.pi / 2, math.pi / 2)]
# Continue the three rounded wind strokes; safe padding also suits maskable icons.
for cx, cy, radius, start, end in arcs:
    points = [(cx + radius * math.cos(start + (end-start)*i/32), cy + radius * math.sin(start + (end-start)*i/32)) for i in range(33)]
    segments.extend((*a, *b) for a, b in zip(points, points[1:]))


def distance(x, y, line):
    ax, ay, bx, by = line
    t = max(0, min(1, ((x-ax)*(bx-ax)+(y-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)))
    return math.hypot(x-ax-t*(bx-ax), y-ay-t*(by-ay))


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))


for size in (192, 512):
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            d = min(distance((x+.5)*192/size, (y+.5)*192/size, s) for s in segments)
            alpha = max(0, min(1, (5-d)*size/192+.5))
            rows.extend(round(c*(1-alpha)+255*alpha) for c in (21, 94, 85))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')
    (ROOT / f'icon-{size}.png').write_bytes(png)
print('Created 192px and 512px PWA wind icons')
