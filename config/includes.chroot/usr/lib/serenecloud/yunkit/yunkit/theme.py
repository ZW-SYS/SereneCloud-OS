# 云匣 · 外观（深色 / 浅色）
# 默认深色：深蓝灰 + 云安蓝 #4F8CC9，圆角
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette

BLUE = "#4F8CC9"

DARK = dict(
    bg="#1B2029", bg2="#222834", panel="#262D3A", card="#2C3443", hover="#343E50",
    sel="#3A5F88", border="#364052", text="#E6EAF0", text2="#9AA6B8", accent=BLUE,
    accent2="#6FA6DD", danger="#E06C75", ok="#7FC8A0",
)
LIGHT = dict(
    bg="#EEF2F7", bg2="#E4EAF2", panel="#F6F8FB", card="#FFFFFF", hover="#DCE6F2",
    sel="#B9D3EE", border="#CCD6E3", text="#1E2633", text2="#5D6B7F", accent=BLUE,
    accent2="#3C77B3", danger="#C94B55", ok="#3D9A6A",
)


def settings():
    return QSettings("SereneCloud", "YunKit")


def current_name():
    return settings().value("theme", "dark")


def colors():
    return DARK if current_name() == "dark" else LIGHT


def qss(c):
    return f"""
QWidget {{ background: {c['bg']}; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']};
            border-radius: 6px; padding: 4px 8px; }}
#Sidebar {{ background: {c['bg2']}; border: none; }}
#Sidebar QLabel#SideTitle {{ color: {c['text2']}; font-size: 9pt; font-weight: 600;
            padding: 10px 14px 4px 14px; background: transparent; }}
#SideList {{ background: transparent; border: none; outline: 0; }}
#SideList::item {{ padding: 6px 10px; margin: 1px 8px; border-radius: 8px; }}
#SideList::item:hover {{ background: {c['hover']}; }}
#SideList::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
#Toolbar {{ background: {c['bg']}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:pressed, QToolButton:checked {{ background: {c['sel']}; }}
QPushButton {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px;
               padding: 6px 14px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton#Primary {{ background: {c['accent']}; color: white; border: none; }}
QPushButton#Primary:hover {{ background: {c['accent2']}; }}
QPushButton#Danger {{ color: {c['danger']}; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: {c['accent']}; selection-color: white; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['border']};
    selection-background-color: {c['sel']}; outline: 0; }}
#Pane {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 12px; }}
#Pane[active="true"] {{ border: 1px solid {c['accent']}; }}
#Pane QWidget {{ background: transparent; }}
#PathBar {{ background: {c['card']}; border-radius: 8px; }}
#Crumb {{ padding: 4px 8px; border-radius: 6px; }}
#Crumb:hover {{ background: {c['hover']}; }}
QListView, QTreeView, QTableView {{ background: transparent; border: none; outline: 0;
    alternate-background-color: {c['bg2']}; }}
QListView::item {{ border-radius: 10px; padding: 4px; }}
QListView::item:hover, QTreeView::item:hover {{ background: {c['hover']}; }}
QListView::item:selected, QTreeView::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QTreeView::item {{ padding: 4px 2px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {c['text2']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 6px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {c['text2']}; padding: 6px 12px; margin-right: 2px;
    border-radius: 8px; }}
QTabBar::tab:selected {{ background: {c['card']}; color: {c['text']}; }}
QTabBar::tab:hover {{ background: {c['hover']}; }}
QTabWidget::pane {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text2']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QStatusBar {{ background: {c['bg']}; color: {c['text2']}; }}
QStatusBar QLabel {{ color: {c['text2']}; }}
QSplitter::handle {{ background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {c['border']};
    background: {c['card']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; }}
QProgressBar {{ background: {c['card']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
#Badge {{ background: {c['accent']}; color: white; border-radius: 8px; padding: 2px 8px; }}
#Muted {{ color: {c['text2']}; }}
#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
#Card QWidget {{ background: transparent; }}
"""


def apply(app):
    c = colors()
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["card"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["bg2"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["card"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["sel"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text2"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["card"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    app.setPalette(pal)
    app.setStyleSheet(qss(c))
