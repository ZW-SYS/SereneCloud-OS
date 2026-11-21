#!/usr/bin/env python3
"""生成云安 OS 的品牌素材：开机动画帧、壁纸、Logo。

用法：python3 branding/tools/gen_branding.py
输出直接写进 config/includes.chroot/ 对应目录。
设计：天青色渐变天空，几朵柔和的云从四周飘向中心，汇聚后化成 "SereneCloud" 字样。
"""
import math, os, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INC = os.path.join(ROOT, "config", "includes.chroot")
PLY = os.path.join(INC, "usr/share/plymouth/themes/serenecloud")
WALL = os.path.join(INC, "usr/share/wallpapers/SereneCloud/contents/images")
LOGO = os.path.join(INC, "usr/share/serenecloud")

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
FONT = next(f for f in FONT_CANDIDATES if os.path.exists(f))

# 云安配色
SKY_TOP = (14, 36, 66)       # 深夜蓝
SKY_BOTTOM = (46, 104, 158)  # 天青
CLOUD = (240, 246, 252)
ACCENT = (79, 140, 201)      # 主题强调色 #4F8CC9


def gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def cloud_sprite(scale, seed):
    """画一朵柔和的云（透明背景）。"""
    rnd = random.Random(seed)
    w, h = int(340 * scale), int(220 * scale)  # 留足边距，模糊不会被裁成直边
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    base_y = h * 0.62
    for i in range(6):
        cx = w * (0.26 + 0.48 * i / 5) + rnd.uniform(-8, 8) * scale
        r = (34 + rnd.uniform(0, 26)) * scale * (1.25 if 1 < i < 4 else 1.0)
        d.ellipse([cx - r, base_y - r * 1.25, cx + r, base_y + r * 0.55], fill=255)
    d.rounded_rectangle([w * 0.22, base_y - 18 * scale, w * 0.78, base_y + 16 * scale], radius=int(16 * scale), fill=255)
    img = img.filter(ImageFilter.GaussianBlur(4 * scale))
    out = Image.new("RGBA", (w, h), CLOUD + (0,))
    out.putalpha(img)
    return out


def ease(t):
    return 1 - (1 - t) ** 3


def text_layer(w, h, size, alpha):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT, size)
    d = ImageDraw.Draw(layer)
    txt = "SereneCloud"
    bw = d.textlength(txt, font=font)
    x, y = (w - bw) / 2, h / 2 - size * 0.62
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((x, y), txt, font=font, fill=(170, 210, 245, int(150 * alpha)))
    layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(size * 0.12)))
    ImageDraw.Draw(layer).text((x, y), txt, font=font, fill=(255, 255, 255, int(255 * alpha)))
    return layer


def plymouth_frames(n=60, w=800, h=300):
    """开机动画帧（透明背景，脚本把它们放在屏幕中央）。
    0-34 帧：云从四周飘向中心；35-49 帧：云淡出、字样浮现；50-59 帧：字样呼吸光。"""
    os.makedirs(PLY, exist_ok=True)
    starts = [(-0.35, 0.15), (1.1, 0.05), (-0.3, 0.75), (1.05, 0.8), (0.5, -0.5), (0.5, 1.3)]
    sprites = [cloud_sprite(0.55 + 0.1 * (i % 3), i) for i in range(len(starts))]
    for f in range(n):
        frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        move = ease(min(1, f / 34))
        fade = max(0.0, min(1.0, (f - 32) / 15))
        for (sx, sy), sp in zip(starts, sprites):
            cx = (sx + (0.5 - sx) * move) * w
            cy = (sy + (0.5 - sy) * move) * h
            a = sp.copy()
            a.putalpha(a.getchannel("A").point(lambda v: int(v * (1 - fade) * 0.9)))
            frame.alpha_composite(a, (int(cx - sp.width / 2), int(cy - sp.height / 2)))
        if f >= 30:
            ta = min(1.0, (f - 30) / 18)
            if f >= 50:
                ta = 0.85 + 0.15 * math.sin((f - 50) / 10 * math.pi * 2)
            frame = Image.alpha_composite(frame, text_layer(w, h, 84, ta))
        frame.save(os.path.join(PLY, f"frame-{f:02d}.png"), optimize=True)


def wallpaper(w=3840, h=2160):
    os.makedirs(WALL, exist_ok=True)
    img = gradient(w, h, SKY_TOP, SKY_BOTTOM).convert("RGBA")
    rnd = random.Random(7)
    # 远处的星点
    d = ImageDraw.Draw(img)
    for _ in range(260):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h * 0.45)
        r = rnd.uniform(0.8, 2.2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, int(rnd.uniform(60, 180))))
    # 底部的云海
    for i in range(26):
        sp = cloud_sprite(rnd.uniform(2.0, 4.2), 100 + i)
        sp.putalpha(sp.getchannel("A").point(lambda v, k=rnd.uniform(0.35, 0.8): int(v * k)))
        img.alpha_composite(sp, (int(rnd.uniform(-400, w - 200)), int(h * rnd.uniform(0.62, 0.88))))
    # 一盏安静的月
    moon = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(moon).ellipse([w * 0.74, h * 0.16, w * 0.74 + 180, h * 0.16 + 180], fill=(255, 248, 225, 235))
    img = Image.alpha_composite(img, moon.filter(ImageFilter.GaussianBlur(2)))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([w * 0.74 - 120, h * 0.16 - 120, w * 0.74 + 300, h * 0.16 + 300], fill=(255, 240, 200, 60))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))
    rgb = img.convert("RGB")
    rgb.save(os.path.join(WALL, "3840x2160.jpg"), quality=90)
    rgb.resize((1920, 1080), Image.LANCZOS).save(os.path.join(WALL, "1920x1080.jpg"), quality=90)
    rgb.resize((400, 225), Image.LANCZOS).save(os.path.join(os.path.dirname(WALL), "screenshot.png"))


def logo(size=512):
    os.makedirs(LOGO, exist_ok=True)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, size - 8, size - 8], fill=ACCENT + (255,))
    inner = gradient(size, size, (98, 160, 222), (40, 92, 150)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([20, 20, size - 20, size - 20], fill=255)
    img.paste(inner, (0, 0), mask)
    c = cloud_sprite(size / 330, 3)
    img.alpha_composite(c, ((size - c.width) // 2, int(size * 0.5 - c.height * 0.55)))
    img.save(os.path.join(LOGO, "serenecloud-logo.png"))
    for s in (256, 128, 64, 48, 32):
        d = os.path.join(INC, f"usr/share/icons/hicolor/{s}x{s}/apps")
        os.makedirs(d, exist_ok=True)
        img.resize((s, s), Image.LANCZOS).save(os.path.join(d, "serenecloud.png"))
    # Plymouth 底部小 logo
    img.resize((48, 48), Image.LANCZOS).save(os.path.join(PLY, "logo-small.png"))


if __name__ == "__main__":
    plymouth_frames()
    wallpaper()
    logo()
    print("品牌素材已生成 ✓")
