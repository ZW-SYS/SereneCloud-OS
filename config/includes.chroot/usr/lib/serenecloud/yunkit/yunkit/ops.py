# 云匣 · 文件操作（复制、移动、删除、放进回收站）在后台线程里做，不卡界面
import os, shutil, subprocess

from PyQt6.QtCore import QThread, pyqtSignal

from . import vfs


def _sudo(args):
    r = subprocess.run(["sudo", "-n"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise PermissionError(r.stderr.strip() or "sudo 失败")


class FileOp(QThread):
    progress = pyqtSignal(int, int, str)     # 第几个, 一共几个, 当前名字
    finished_ok = pyqtSignal(str)            # 完成提示
    failed = pyqtSignal(str)

    def __init__(self, op, entries, dest=None, root_mode=False):
        super().__init__()
        self.op, self.entries, self.dest, self.root = op, entries, dest, root_mode
        self.cancelled = False

    def run(self):
        errors = []
        n = len(self.entries)
        for i, e in enumerate(self.entries):
            if self.cancelled:
                break
            self.progress.emit(i, n, e.name)
            try:
                self._one(e)
            except Exception as ex:
                errors.append(f"{e.name}：{ex}")
        self.progress.emit(n, n, "")
        if errors:
            self.failed.emit("有 %d 个没成功：\n" % len(errors) + "\n".join(errors[:8]))
        else:
            word = {"copy": "复制", "move": "移动", "delete": "删除", "trash": "放进回收站",
                    "extract": "取出"}.get(self.op, "完成")
            self.finished_ok.emit(f"已{word} {n} 项")

    def _one(self, e):
        if self.op in ("copy", "move", "extract"):
            if e.archive:  # 从压缩包里取出来
                tmp = vfs.extract_member(e.archive, e.inner)
                target = vfs.unique_path(os.path.join(self.dest, e.name))
                shutil.move(tmp, target)
                return
            src = e.local
            target = os.path.join(self.dest, e.name)
            if os.path.abspath(target) == os.path.abspath(src):
                if self.op == "move":
                    return
            if os.path.isdir(src) and (self.dest + "/").startswith(src.rstrip("/") + "/"):
                raise OSError("不能把文件夹放进它自己里面")
            target = vfs.unique_path(target)
            try:
                if self.op == "move":
                    shutil.move(src, target)
                elif os.path.isdir(src) and not os.path.islink(src):
                    shutil.copytree(src, target, symlinks=True)
                else:
                    shutil.copy2(src, target, follow_symlinks=False)
            except PermissionError:
                if not self.root:
                    raise PermissionError("没有权限（可以打开 Root 模式）")
                _sudo(["mv", src, target] if self.op == "move" else ["cp", "-a", src, target])
        elif self.op == "trash":
            try:
                vfs.trash(e.local)
            except PermissionError:
                raise PermissionError("没有权限放进回收站（Root 模式下请用「彻底删除」）")
        elif self.op == "delete":
            if e.extra.get("trash_name"):
                vfs.delete_trash_item(e)
                return
            p = e.local
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except PermissionError:
                if not self.root:
                    raise PermissionError("没有权限（可以打开 Root 模式）")
                _sudo(["rm", "-rf", "--", p])
