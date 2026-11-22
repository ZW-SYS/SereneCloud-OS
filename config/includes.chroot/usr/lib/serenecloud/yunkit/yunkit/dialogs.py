# 云匣 · 对话框：重命名、批量重命名、属性和权限、压缩、搜索
import fnmatch, grp, os, pwd, re, stat, subprocess, time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QTabWidget)

from . import util, vfs


def buttons(dlg, ok_text="确定"):
    bb = QDialogButtonBox()
    ok = bb.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setObjectName("Primary")
    bb.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


def ask_name(parent, title, label, default="", select_stem=True):
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.setMinimumWidth(420)
    v = QVBoxLayout(d)
    v.addWidget(QLabel(label))
    e = QLineEdit(default)
    v.addWidget(e)
    v.addWidget(buttons(d))
    e.setFocus()
    if select_stem and "." in default.strip("."):
        e.setSelection(0, default.rfind("."))
    else:
        e.selectAll()
    if d.exec() and e.text().strip():
        name = e.text().strip()
        if "/" in name:
            QMessageBox.warning(parent, "云匣", "名字里不能有 /")
            return None
        return name
    return None


class BatchRename(QDialog):
    """批量重命名：替换文字、加前后缀、按序号、改大小写，实时预览。"""

    def __init__(self, parent, entries):
        super().__init__(parent)
        self.setWindowTitle("批量重命名")
        self.resize(760, 520)
        self.entries = entries
        self.find = QLineEdit(); self.find.setPlaceholderText("要找的文字（可留空）")
        self.repl = QLineEdit(); self.repl.setPlaceholderText("换成")
        self.regex = QCheckBox("正则表达式")
        self.prefix = QLineEdit(); self.prefix.setPlaceholderText("前缀")
        self.suffix = QLineEdit(); self.suffix.setPlaceholderText("后缀（加在扩展名前面）")
        self.number = QCheckBox("加序号")
        self.start = QSpinBox(); self.start.setRange(0, 999999); self.start.setValue(1)
        self.digits = QSpinBox(); self.digits.setRange(1, 8); self.digits.setValue(2)
        self.template = QLineEdit(); self.template.setPlaceholderText("完全改名：例如 照片_{n}（{n} 是序号，{name} 是原名）")
        self.case = QComboBox(); self.case.addItems(["大小写不变", "全部小写", "全部大写"])
        self.ext = QLineEdit(); self.ext.setPlaceholderText("新扩展名（留空不改）")
        f = QGridLayout()
        f.addWidget(QLabel("查找替换"), 0, 0); f.addWidget(self.find, 0, 1); f.addWidget(self.repl, 0, 2); f.addWidget(self.regex, 0, 3)
        f.addWidget(QLabel("前后缀"), 1, 0); f.addWidget(self.prefix, 1, 1); f.addWidget(self.suffix, 1, 2)
        nb = QHBoxLayout(); nb.addWidget(self.number); nb.addWidget(QLabel("从")); nb.addWidget(self.start)
        nb.addWidget(QLabel("位数")); nb.addWidget(self.digits); nb.addStretch(1)
        f.addWidget(QLabel("序号"), 2, 0); f.addLayout(nb, 2, 1, 1, 3)
        f.addWidget(QLabel("模板"), 3, 0); f.addWidget(self.template, 3, 1, 1, 3)
        f.addWidget(QLabel("其他"), 4, 0); f.addWidget(self.case, 4, 1); f.addWidget(self.ext, 4, 2)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["原来的名字", "新名字"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.warn = QLabel(); self.warn.setObjectName("Muted")
        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addWidget(self.table, 1)
        v.addWidget(self.warn)
        v.addWidget(buttons(self, "全部改名"))
        for w in (self.find, self.repl, self.prefix, self.suffix, self.template, self.ext):
            w.textChanged.connect(self.preview)
        for w in (self.regex, self.number):
            w.toggled.connect(self.preview)
        for w in (self.start, self.digits):
            w.valueChanged.connect(self.preview)
        self.case.currentIndexChanged.connect(self.preview)
        self.preview()

    def new_names(self):
        out = []
        for i, e in enumerate(self.entries):
            name = e.name
            if e.is_dir or "." not in name.strip("."):
                stem, ext = name, ""
            else:
                stem, ext = name[:name.rfind(".")], name[name.rfind("."):]
            n = str(self.start.value() + i).zfill(self.digits.value())
            if self.template.text():
                stem = self.template.text().replace("{n}", n).replace("{name}", stem)
            if self.find.text():
                try:
                    stem = re.sub(self.find.text(), self.repl.text(), stem) if self.regex.isChecked() \
                        else stem.replace(self.find.text(), self.repl.text())
                except re.error:
                    pass
            stem = self.prefix.text() + stem + self.suffix.text()
            if self.number.isChecked() and not self.template.text():
                stem = f"{stem}_{n}"
            if self.ext.text().strip() and not e.is_dir:
                ext = "." + self.ext.text().strip().lstrip(".")
            new = stem + ext
            if self.case.currentIndex() == 1:
                new = new.lower()
            elif self.case.currentIndex() == 2:
                new = new.upper()
            out.append(new)
        return out

    def preview(self):
        names = self.new_names()
        self.table.setRowCount(len(names))
        dup = len(set(names)) != len(names)
        for i, (e, n) in enumerate(zip(self.entries, names)):
            self.table.setItem(i, 0, QTableWidgetItem(e.name))
            self.table.setItem(i, 1, QTableWidgetItem(n))
        bad = any("/" in n or not n for n in names)
        self.warn.setText("⚠️ 有重复或不合法的名字，请改一下" if dup or bad else f"共 {len(names)} 个")
        return not (dup or bad)

    def run(self):
        if not self.exec():
            return 0
        if not self.preview():
            QMessageBox.warning(self, "云匣", "有重复或不合法的名字，没有改。")
            return 0
        names = self.new_names()
        # 先改成临时名字，避免 a→b、b→a 互相覆盖
        tmp = []
        for e in self.entries:
            t = e.local + f".yunkit-tmp-{time.time_ns()}"
            os.rename(e.local, t)
            tmp.append(t)
        done = 0
        for t, e, n in zip(tmp, self.entries, names):
            target = vfs.unique_path(os.path.join(os.path.dirname(e.local), n))
            os.rename(t, target)
            done += 1
        return done


class SizeJob(QThread):
    done = pyqtSignal(int, int, bool)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        s, c, more = vfs.dir_size(self.path)
        self.done.emit(s, c, more)


class Properties(QDialog):
    """属性：大小、位置、时间、权限（可以改）、所有者。"""

    def __init__(self, parent, entry, root_mode=False):
        super().__init__(parent)
        self.e = entry
        self.root = root_mode
        self.setWindowTitle(f"属性 — {entry.name}")
        self.setMinimumWidth(460)
        tabs = QTabWidget()
        info = QWidget()
        f = QFormLayout(info)
        f.setVerticalSpacing(10)
        self.size_lbl = QLabel(util.human_size(entry.size) + f"（{entry.size:,} 字节）" if not entry.is_dir else "正在计算…")
        f.addRow("名称", QLabel(entry.name))
        f.addRow("类型", QLabel(util.KIND_NAME.get(entry.kind, "文件")))
        loc = QLabel(os.path.dirname(entry.local) if entry.local else entry.archive + " 里面")
        loc.setWordWrap(True); loc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow("位置", loc)
        f.addRow("大小", self.size_lbl)
        f.addRow("修改时间", QLabel(util.human_time(entry.mtime)))
        if entry.local:
            try:
                st = os.stat(entry.local)
                f.addRow("访问时间", QLabel(util.human_time(st.st_atime)))
            except OSError:
                pass
            if entry.is_link:
                f.addRow("链接到", QLabel(os.readlink(entry.local)))
        tabs.addTab(info, "常规")
        if entry.is_dir and entry.local:
            self.job = SizeJob(entry.local)
            self.job.done.connect(lambda s, c, more: self.size_lbl.setText(
                f"{util.human_size(s)}，{c}{'+' if more else ''} 个文件"))
            self.job.start()
        # 权限
        self.boxes = {}
        if entry.local and entry.mode:
            perm = QWidget()
            g = QGridLayout(perm)
            for col, t in enumerate(("", "读", "写", "执行"), 0):
                g.addWidget(QLabel(t), 0, col)
            for row, (who, shift) in enumerate((("所有者", 6), ("用户组", 3), ("其他人", 0)), 1):
                g.addWidget(QLabel(who), row, 0)
                for col, bit in enumerate((4, 2, 1), 1):
                    cb = QCheckBox()
                    cb.setChecked(bool(entry.mode >> shift & bit))
                    self.boxes[(shift, bit)] = cb
                    g.addWidget(cb, row, col)
            try:
                st = os.lstat(entry.local)
                gname = grp.getgrgid(st.st_gid).gr_name
            except (KeyError, OSError):
                gname = "?"
            self.owner = QLineEdit(entry.owner)
            self.group = QLineEdit(gname)
            g.addWidget(QLabel("所有者"), 4, 0); g.addWidget(self.owner, 4, 1, 1, 3)
            g.addWidget(QLabel("用户组"), 5, 0); g.addWidget(self.group, 5, 1, 1, 3)
            self.octal = QLabel(); self.octal.setObjectName("Muted")
            g.addWidget(self.octal, 6, 0, 1, 4)
            self.recursive = QCheckBox("同时应用到里面所有文件")
            self.recursive.setVisible(entry.is_dir)
            g.addWidget(self.recursive, 7, 0, 1, 4)
            for cb in self.boxes.values():
                cb.toggled.connect(self._oct)
            self._oct()
            tabs.addTab(perm, "权限")
            self.orig_owner, self.orig_group = entry.owner, gname
        v = QVBoxLayout(self)
        v.addWidget(tabs)
        v.addWidget(buttons(self, "应用"))

    def _mode(self):
        m = 0
        for (shift, bit), cb in self.boxes.items():
            if cb.isChecked():
                m |= bit << shift
        return m | (self.e.mode & 0o7000)

    def _oct(self):
        m = self._mode()
        self.octal.setText(f"数字表示：{m & 0o7777:04o}    {util.perm_string(m)}")

    def apply(self):
        if not self.exec() or not self.boxes:
            return False
        m = self._mode()
        p = self.e.local
        cmds = []
        if m != (self.e.mode & 0o7777):
            cmds.append(["chmod"] + (["-R"] if self.recursive.isChecked() else []) + [f"{m:o}", p])
        if self.owner.text() != self.orig_owner or self.group.text() != self.orig_group:
            cmds.append(["chown"] + (["-R"] if self.recursive.isChecked() else []) +
                        [f"{self.owner.text()}:{self.group.text()}", p])
        for c in cmds:
            r = subprocess.run(c, capture_output=True, text=True)
            if r.returncode != 0 and self.root:
                r = subprocess.run(["sudo", "-n"] + c, capture_output=True, text=True)
            if r.returncode != 0:
                QMessageBox.warning(self.parent(), "云匣", "改权限失败：" + r.stderr.strip() +
                                    ("" if self.root else "\n可以打开 Root 模式再试。"))
                return False
        return True


class CompressDialog(QDialog):
    def __init__(self, parent, entries):
        super().__init__(parent)
        self.setWindowTitle("压缩")
        self.setMinimumWidth(420)
        base = entries[0].name if len(entries) == 1 else os.path.basename(os.path.dirname(entries[0].local)) or "压缩包"
        if not entries[0].is_dir and len(entries) == 1 and "." in base:
            base = base[:base.rfind(".")]
        self.name = QLineEdit(base)
        self.fmt = QComboBox()
        self.fmt.addItems(["zip", "7z", "tar.gz", "tar.xz"])
        f = QFormLayout(self)
        f.addRow("名字", self.name)
        f.addRow("格式", self.fmt)
        f.addRow(buttons(self, "压缩"))

    def get(self):
        if self.exec() and self.name.text().strip():
            return self.name.text().strip() + "." + self.fmt.currentText(), self.fmt.currentText()
        return None


class SearchJob(QThread):
    """在文件夹里一层一层往下找名字。"""
    batch = pyqtSignal(list)
    done = pyqtSignal(int)

    def __init__(self, root, text, show_hidden=False):
        super().__init__()
        self.root, self.text, self.hidden = root, text, show_hidden
        self.stop = False

    def run(self):
        pat = self.text.lower()
        glob = any(ch in pat for ch in "*?[")
        found, buf = 0, []
        for dirpath, dirs, files in os.walk(self.root):
            if self.stop:
                break
            if not self.hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            dirs[:] = [d for d in dirs if not os.path.ismount(os.path.join(dirpath, d)) or dirpath == self.root]
            for n in dirs + files:
                if not self.hidden and n.startswith("."):
                    continue
                low = n.lower()
                if (fnmatch.fnmatch(low, pat) if glob else pat in low):
                    e = vfs.local_entry(os.path.join(dirpath, n), n)
                    if e:
                        buf.append(e)
                        found += 1
            if len(buf) >= 50:
                self.batch.emit(buf)
                buf = []
            if found >= 5000:
                break
        if buf:
            self.batch.emit(buf)
        self.done.emit(found)
