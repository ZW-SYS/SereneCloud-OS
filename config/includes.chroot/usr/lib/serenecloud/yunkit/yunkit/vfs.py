# 云匣 · 虚拟文件系统：本地文件夹、压缩包（当文件夹看）、回收站
#
# 位置字符串：
#   /home/yunan/下载                 本地
#   archive:///home/a/b.zip!/res/x  压缩包里面
#   trash:///                       回收站
import os, pwd, grp, stat, shutil, subprocess, tarfile, tempfile, time, urllib.parse, zipfile
from dataclasses import dataclass, field

from . import util

ARCHIVE = "archive://"
TRASH = "trash:///"
HOME = os.path.expanduser("~")
TRASH_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local/share")), "Trash")


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0
    mode: int = 0
    owner: str = ""
    loc: str = ""            # 打开它要去的位置（文件夹）或它自己的位置
    local: str = ""          # 真实路径（本地文件才有）
    archive: str = ""        # 所在压缩包
    inner: str = ""          # 在压缩包里的路径
    extra: dict = field(default_factory=dict)
    is_link: bool = False
    hidden: bool = False

    @property
    def kind(self):
        return util.kind_of(self.name, self.is_dir)


class ListError(Exception):
    pass


# ---------------- 位置 ----------------

def is_archive_loc(loc):
    return loc.startswith(ARCHIVE)


def split_archive(loc):
    rest = loc[len(ARCHIVE):]
    if "!" in rest:
        a, inner = rest.split("!", 1)
    else:
        a, inner = rest, "/"
    return a, inner.strip("/")


def make_archive_loc(archive, inner=""):
    return f"{ARCHIVE}{archive}!/{inner.strip('/')}"


def parent_of(loc):
    if loc == TRASH:
        return HOME
    if is_archive_loc(loc):
        a, inner = split_archive(loc)
        if not inner:
            return os.path.dirname(a)
        return make_archive_loc(a, os.path.dirname(inner))
    p = os.path.dirname(loc.rstrip("/")) or "/"
    return p


def display_parts(loc):
    """面包屑：[(显示名, 位置), ...]"""
    if loc == TRASH:
        return [("回收站", TRASH)]
    if is_archive_loc(loc):
        a, inner = split_archive(loc)
        parts = display_parts(a)
        parts[-1] = ("📦 " + parts[-1][0], make_archive_loc(a, ""))
        acc = ""
        for seg in [s for s in inner.split("/") if s]:
            acc = f"{acc}/{seg}" if acc else seg
            parts.append((seg, make_archive_loc(a, acc)))
        return parts
    path = os.path.abspath(loc)
    parts = []
    if path.startswith(HOME):
        parts.append(("主文件夹", HOME))
        rest = path[len(HOME):]
        base = HOME
    else:
        parts.append(("根目录 /", "/"))
        rest = path
        base = ""
    for seg in [s for s in rest.split("/") if s]:
        base = f"{base}/{seg}"
        parts.append((seg, base))
    return parts


def title_of(loc):
    return display_parts(loc)[-1][0].replace("📦 ", "")


# ---------------- 本地 ----------------

_uid_cache = {}


def owner_name(uid):
    if uid not in _uid_cache:
        try:
            _uid_cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _uid_cache[uid] = str(uid)
    return _uid_cache[uid]


def local_entry(path, name=None):
    name = name or os.path.basename(path.rstrip("/")) or "/"
    try:
        lst = os.lstat(path)
    except OSError:
        return None
    is_link = stat.S_ISLNK(lst.st_mode)
    try:
        st = os.stat(path) if is_link else lst
    except OSError:
        st = lst
    is_dir = stat.S_ISDIR(st.st_mode)
    return Entry(name=name, is_dir=is_dir, size=0 if is_dir else st.st_size, mtime=st.st_mtime,
                 mode=st.st_mode, owner=owner_name(st.st_uid), loc=path, local=path,
                 is_link=is_link, hidden=name.startswith("."))


def list_local(path, root_mode=False):
    try:
        names = os.listdir(path)
    except PermissionError:
        if root_mode:
            return list_local_sudo(path)
        raise ListError("没有权限打开这个文件夹。可以在右上角打开「Root 模式」再试。")
    except FileNotFoundError:
        raise ListError("这个文件夹不存在了。")
    except OSError as e:
        raise ListError(str(e))
    out = []
    for n in names:
        e = local_entry(os.path.join(path, n), n)
        if e:
            out.append(e)
    return out


def list_local_sudo(path):
    r = subprocess.run(["sudo", "-n", "find", path, "-mindepth", "1", "-maxdepth", "1",
                        "-printf", r"%Y\t%s\t%T@\t%m\t%u\t%f\n"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 and not r.stdout:
        raise ListError("Root 模式也打不开：" + (r.stderr.strip() or "sudo 需要密码"))
    out = []
    for line in r.stdout.splitlines():
        try:
            t, size, mt, mode, user, name = line.split("\t", 5)
        except ValueError:
            continue
        isd = t == "d"
        full = os.path.join(path, name)
        out.append(Entry(name=name, is_dir=isd, size=0 if isd else int(size), mtime=float(mt),
                         mode=int(mode, 8) | (stat.S_IFDIR if isd else stat.S_IFREG),
                         owner=user, loc=full, local=full, hidden=name.startswith(".")))
    return out


# ---------------- 压缩包 ----------------

_arc_cache = {}


def archive_kind(path):
    """zip（含 apk/jar）用 Python 自带的 zipfile；tar 用 tarfile；其它交给 7z。"""
    e = util.ext_of(path)
    low = path.lower()
    try:
        if e in ("zip", "apk", "jar", "aar", "war", "apks", "xapk", "aab") and zipfile.is_zipfile(path):
            return "zip"
        if low.endswith(".zst") or low.endswith(".tzst"):
            return "7z"
        if e in ("tar", "tgz", "tbz", "txz", "gz", "bz2", "xz") and tarfile.is_tarfile(path):
            return "tar"
    except OSError:
        pass
    return "7z"


def _seven():
    for c in ("7z", "7zz", "7za"):
        if shutil.which(c):
            return c
    return None


def _read_archive(path):
    """返回 {内部路径: (是否文件夹, 大小, 时间)}"""
    kind = archive_kind(path)
    items = {}
    if kind == "zip":
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                n = i.filename.strip("/")
                if not n:
                    continue
                t = time.mktime(i.date_time + (0, 0, -1)) if i.date_time[0] > 1979 else 0
                items[n] = (i.is_dir(), i.file_size, t)
    elif kind == "tar":
        with tarfile.open(path) as t:
            for m in t.getmembers():
                n = m.name.strip("/").removeprefix("./")
                if n:
                    items[n] = (m.isdir(), m.size, m.mtime)
    else:
        sz = _seven()
        if not sz:
            raise ListError("没有找到 7z 程序，打不开这种压缩包。")
        r = subprocess.run([sz, "l", "-slt", "-ba", "-p", path], capture_output=True, text=True,
                           timeout=120, stdin=subprocess.DEVNULL)
        if r.returncode != 0 and not r.stdout.strip():
            raise ListError("打不开这个压缩包：" + (r.stderr.strip().splitlines() or ["可能已损坏或有密码"])[-1])
        cur = {}
        for line in r.stdout.splitlines() + [""]:
            if not line.strip():
                if cur.get("Path"):
                    n = cur["Path"].strip("/")
                    isd = cur.get("Folder") == "+" or cur.get("Attributes", "").startswith("D")
                    try:
                        t = time.mktime(time.strptime(cur.get("Modified", "")[:19], "%Y-%m-%d %H:%M:%S"))
                    except ValueError:
                        t = 0
                    items[n] = (isd, int(cur.get("Size") or 0), t)
                cur = {}
                continue
            if " = " in line:
                k, v = line.split(" = ", 1)
                cur[k] = v
    # 补上隐含的文件夹
    for n in list(items):
        parts = n.split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d not in items:
                items[d] = (True, 0, 0)
    return items


def archive_items(path):
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key not in _arc_cache:
        _arc_cache.clear() if len(_arc_cache) > 20 else None
        _arc_cache[key] = _read_archive(path)
    return _arc_cache[key]


def list_archive(loc):
    a, inner = split_archive(loc)
    try:
        items = archive_items(a)
    except ListError:
        raise
    except Exception as e:
        raise ListError(f"打不开这个压缩包：{e}")
    prefix = inner + "/" if inner else ""
    out = []
    for n, (isd, size, t) in items.items():
        if not n.startswith(prefix):
            continue
        rest = n[len(prefix):]
        if not rest or "/" in rest:
            continue
        out.append(Entry(name=rest, is_dir=isd, size=size, mtime=t, loc=make_archive_loc(a, n),
                         archive=a, inner=n, hidden=rest.startswith(".")))
    return out


_extract_root = None


def extract_root():
    global _extract_root
    if not _extract_root:
        _extract_root = tempfile.mkdtemp(prefix="yunkit-")
    return _extract_root


def extract_member(archive, inner, dest_dir=None):
    """把压缩包里的一个文件（或文件夹）取出来，返回取出后的路径。"""
    dest_dir = dest_dir or os.path.join(extract_root(), str(abs(hash(archive))))
    os.makedirs(dest_dir, exist_ok=True)
    kind = archive_kind(archive)
    items = archive_items(archive)
    names = [n for n in items if n == inner or n.startswith(inner + "/")] if inner else list(items)
    base = os.path.dirname(inner)
    if kind == "zip":
        with zipfile.ZipFile(archive) as z:
            for n in names:
                isd = items[n][0]
                rel = n[len(base) + 1:] if base else n
                target = _safe_join(dest_dir, rel)
                if isd:
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                try:
                    data_name = n if n in z.NameToInfo else n + "/"
                    with z.open(data_name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                except KeyError:
                    pass
    elif kind == "tar":
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                n = m.name.strip("/").removeprefix("./")
                if n not in names:
                    continue
                rel = n[len(base) + 1:] if base else n
                target = _safe_join(dest_dir, rel)
                if m.isdir():
                    os.makedirs(target, exist_ok=True)
                elif m.isfile():
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with t.extractfile(m) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    else:
        sz = _seven()
        tmp = tempfile.mkdtemp(dir=extract_root())
        args = [sz, "x", "-y", "-p", f"-o{tmp}", archive]
        if inner:
            args.append(inner)
        subprocess.run(args, capture_output=True, timeout=600, stdin=subprocess.DEVNULL)
        src = os.path.join(tmp, inner) if inner else tmp
        if inner:
            target = os.path.join(dest_dir, os.path.basename(inner))
            if os.path.exists(target):
                shutil.rmtree(target) if os.path.isdir(target) else os.remove(target)
            shutil.move(src, target)
        else:
            for n in os.listdir(tmp):
                shutil.move(os.path.join(tmp, n), os.path.join(dest_dir, n))
        shutil.rmtree(tmp, ignore_errors=True)
    return os.path.join(dest_dir, os.path.basename(inner)) if inner else dest_dir


def _safe_join(root, rel):
    p = os.path.normpath(os.path.join(root, rel))
    if not (p == root or p.startswith(root.rstrip("/") + "/")):
        raise ListError("压缩包里有不安全的路径，已跳过。")
    return p


def extract_all(archive, dest):
    os.makedirs(dest, exist_ok=True)
    kind = archive_kind(archive)
    if kind == "7z":
        r = subprocess.run([_seven(), "x", "-y", "-p", f"-o{dest}", archive], capture_output=True,
                           text=True, timeout=3600, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise ListError("解压失败：" + (r.stderr.strip().splitlines() or ["可能有密码"])[-1])
    else:
        extract_member(archive, "", dest)
    return dest


def compress(files, out, fmt):
    """fmt: zip / 7z / tar.gz / tar.xz"""
    if fmt == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                base = os.path.dirname(f.rstrip("/"))
                if os.path.isdir(f):
                    for root, dirs, fs in os.walk(f):
                        z.write(root, os.path.relpath(root, base))
                        for x in fs:
                            p = os.path.join(root, x)
                            z.write(p, os.path.relpath(p, base))
                else:
                    z.write(f, os.path.relpath(f, base))
    elif fmt in ("tar.gz", "tar.xz"):
        with tarfile.open(out, "w:" + fmt.split(".")[1]) as t:
            for f in files:
                t.add(f, os.path.basename(f.rstrip("/")))
    elif fmt == "7z":
        r = subprocess.run([_seven(), "a", "-y", out] + list(files), capture_output=True, text=True,
                           timeout=3600, cwd=os.path.dirname(files[0]))
        if r.returncode != 0:
            raise ListError("压缩失败：" + r.stderr.strip())
    return out


# ---------------- 回收站（freedesktop 规范） ----------------

def trash(path):
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", path], capture_output=True, text=True)
        if r.returncode == 0:
            return
    files = os.path.join(TRASH_DIR, "files")
    info = os.path.join(TRASH_DIR, "info")
    os.makedirs(files, exist_ok=True)
    os.makedirs(info, exist_ok=True)
    base = os.path.basename(path.rstrip("/"))
    name, i = base, 1
    while os.path.exists(os.path.join(files, name)) or os.path.exists(os.path.join(info, name + ".trashinfo")):
        i += 1
        name = f"{base}.{i}"
    with open(os.path.join(info, name + ".trashinfo"), "w") as f:
        f.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (
            urllib.parse.quote(os.path.abspath(path)), time.strftime("%Y-%m-%dT%H:%M:%S")))
    shutil.move(path, os.path.join(files, name))


def list_trash():
    files = os.path.join(TRASH_DIR, "files")
    info = os.path.join(TRASH_DIR, "info")
    out = []
    if not os.path.isdir(files):
        return out
    for n in os.listdir(files):
        e = local_entry(os.path.join(files, n), n)
        if not e:
            continue
        orig, deleted = "", 0
        try:
            for line in open(os.path.join(info, n + ".trashinfo"), encoding="utf-8"):
                if line.startswith("Path="):
                    orig = urllib.parse.unquote(line[5:].strip())
                elif line.startswith("DeletionDate="):
                    deleted = time.mktime(time.strptime(line[13:].strip()[:19], "%Y-%m-%dT%H:%M:%S"))
        except (OSError, ValueError):
            pass
        e.name = os.path.basename(orig) or n
        e.extra = {"orig": orig, "trash_name": n}
        if deleted:
            e.mtime = deleted
        e.loc = e.local
        out.append(e)
    return out


def restore_trash(entry):
    orig = entry.extra.get("orig")
    if not orig:
        raise ListError("不知道它原来在哪里。")
    os.makedirs(os.path.dirname(orig), exist_ok=True)
    target = unique_path(orig)
    shutil.move(entry.local, target)
    try:
        os.remove(os.path.join(TRASH_DIR, "info", entry.extra["trash_name"] + ".trashinfo"))
    except OSError:
        pass
    return target


def empty_trash():
    for sub in ("files", "info"):
        d = os.path.join(TRASH_DIR, sub)
        if os.path.isdir(d):
            for n in os.listdir(d):
                p = os.path.join(d, n)
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)


def delete_trash_item(entry):
    p = entry.local
    shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
    try:
        os.remove(os.path.join(TRASH_DIR, "info", entry.extra["trash_name"] + ".trashinfo"))
    except OSError:
        pass


# ---------------- 统一入口 ----------------

def list_loc(loc, root_mode=False):
    if loc == TRASH:
        return list_trash()
    if is_archive_loc(loc):
        return list_archive(loc)
    return list_local(loc, root_mode)


def unique_path(path):
    if not os.path.exists(path) and not os.path.islink(path):
        return path
    d, b = os.path.split(path)
    stem, ext = (b.rsplit(".", 1) + [""])[:2] if "." in b.strip(".") else (b, "")
    i = 2
    while True:
        cand = os.path.join(d, f"{stem} ({i})" + (f".{ext}" if ext else ""))
        if not os.path.exists(cand):
            return cand
        i += 1


def dir_size(path, limit=200000):
    total, count = 0, 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
            count += 1
            if count > limit:
                return total, count, True
    return total, count, False
