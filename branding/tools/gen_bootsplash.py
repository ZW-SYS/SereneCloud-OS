#!/usr/bin/env python3
"""生成 U 盘开机菜单的背景图（GRUB 800x600，isolinux 640x480）。"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
WALL = ROOT / "config/includes.chroot/usr/share/wallpapers/SereneCloud/contents/images/1920x1080.jpg"
LOGO = ROOT / "config/includes.chroot/usr/share/serenecloud/serenecloud-logo.png"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def splash(w, h, out):
    wall = Image.open(WALL).convert("RGB")
    # 裁成 4:3 再缩放
    W, H = wall.size
    cw = int(H * w / h)
    wall = wall.crop(((W - cw) // 2, 0, (W - cw) // 2 + cw, H)).resize((w, h), Image.LANCZOS)
    # 下半部分加深，让菜单文字清楚
    shade = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(shade)
    for y in range(h):
        t = max(0.0, (y / h - 0.42) / 0.58)
        d.line([(0, y), (w, y)], fill=int(170 * min(1, t * 1.4)))
    wall = Image.composite(Image.new("RGB", (w, h), (14, 30, 56)), wall, shade)
    img = wall.convert("RGBA")
    ls = int(h * 0.22)
    logo = Image.open(LOGO).convert("RGBA").resize((ls, ls), Image.LANCZOS)
    img.alpha_composite(logo, ((w - ls) // 2, int(h * 0.06)))
    font = ImageFont.truetype(FONT, int(h * 0.065))
    txt = "SereneCloud OS"
    tw = ImageDraw.Draw(img).textlength(txt, font=font)
    ty = int(h * 0.06) + ls + int(h * 0.01)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text(((w - tw) / 2, ty), txt, font=font, fill=(20, 50, 90, 200))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4)))
    ImageDraw.Draw(img).text(((w - tw) / 2, ty), txt, font=font, fill=(255, 255, 255, 255))
    img.convert("RGB").save(out, optimize=True)
    print("wrote", out)

splash(800, 600, ROOT / "config/includes.binary/boot/grub/splash.png")
splash(640, 480, ROOT / "config/includes.binary/isolinux/splash.png")
