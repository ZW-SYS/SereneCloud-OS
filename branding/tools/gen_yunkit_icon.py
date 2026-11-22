#!/usr/bin/env python3
"""画「云匣」的图标：云安蓝圆角方块 + 白色文件夹 + 小云朵。
用法：QT_QPA_PLATFORM=offscreen python3 branding/tools/gen_yunkit_icon.py"""
import os, sys
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

app = QGuiApplication(sys.argv)
ROOT = os.path.join(os.path.dirname(__file__), "../../config/includes.chroot/usr/share/icons/hicolor")


def draw(s):
    img = QImage(s, s, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, QColor("#6FA6DD"))
    g.setColorAt(1, QColor("#2F5F93"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(s * .04, s * .04, s * .92, s * .92), s * .22, s * .22)
    # 文件夹
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawRoundedRect(QRectF(s * .20, s * .26, s * .26, s * .12), s * .03, s * .03)
    p.drawRoundedRect(QRectF(s * .20, s * .31, s * .60, s * .44), s * .05, s * .05)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(s * .20, s * .38, s * .60, s * .38), s * .05, s * .05)
    # 云朵
    p.setBrush(QColor("#4F8CC9"))
    cx, cy = s * .5, s * .58
    for dx, dy, r in ((-.09, .02, .065), (0, -.025, .085), (.09, .02, .065)):
        p.drawEllipse(QPointF(cx + dx * s, cy + dy * s), r * s, r * s)
    p.drawRoundedRect(QRectF(cx - .155 * s, cy + .005 * s, .31 * s, .08 * s), .04 * s, .04 * s)
    p.end()
    return img


for size in (32, 48, 64, 128, 256):
    d = os.path.join(ROOT, f"{size}x{size}", "apps")
    os.makedirs(d, exist_ok=True)
    draw(size).save(os.path.join(d, "yunkit.png"))
print("ok")
