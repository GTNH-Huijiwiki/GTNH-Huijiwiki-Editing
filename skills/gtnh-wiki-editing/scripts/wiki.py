"""GTNH 中文维基编辑者工具（单文件，只依赖 Python 标准库）。

命令行用法：
    python wiki.py whoami [--bot]
    python wiki.py pull 标题 [标题 ...]
    python wiki.py pull -f 本地文件 [...]
    python wiki.py preview -f 本地文件 [--html 输出.html]
    python wiki.py diff -f 本地文件 [...]
    python wiki.py push -f 本地文件 [...] -s "摘要" [--bot] [--minor] [-j 并行数]
    python wiki.py purge 标题 [标题 ...] [--links]
    python wiki.py lua "Lua 代码" | -f 代码文件.lua

英文维基（wiki.gtnewhorizons.com，只读，不需要 Authkey 和账号）：
    python wiki.py pull --en 标题 [标题 ...] [--force]
    python wiki.py pull --en --all [--namespace 编号 ...] [--force]
    python wiki.py pull|preview|diff -f 英文镜像中的文件      # 按路径自动识别为英文站
    python wiki.py diff --en 标题 --since 旧修订号            # 英文页从该修订到现在改了什么
    python wiki.py diff --en 标题 --since 旧修订号 --sentences  # 只列真正新增、改动和删去的句子

也可以作为库导入：
    import wiki
    wiki.login()                        # 个人账号；wiki.login(bot=True) 为机器人账号
    page = wiki.get_page("火箭")        # {'text', 'revid', 'timestamp', 'contentmodel'}
    wiki.edit("火箭", text, "摘要", baserevid=page["revid"])
    wiki.parse(text, "火箭")
    wiki.get_page("Rockets", en=True)   # 读英文站
    wiki.pull_en(["Rockets"])           # 拉到英文镜像

配置从同目录或当前目录的 .env 读取（见 .env.example），环境变量优先：
    BASE_URL         默认 https://gtnh.huijiwiki.com/api.php
    AUTHKEY          灰机 Wiki 的 API Authkey（请求头 X-authkey），向维基管理员索要
    EDITOR_USERNAME / EDITOR_PASSWORD   个人编辑账号
    BOT_USERNAME / BOT_PASSWORD         机器人账号，仅维护者使用
    WIKI_DIR         本地镜像目录，默认 ./wikitext
    EN_WIKI_DIR      英文维基的本地镜像目录，默认 ./wikitext-en
    EN_BASE_URL      默认 https://wiki.gtnewhorizons.com/w/api.php

本地镜像的目录结构与 GTNH-Huijiwiki-Toolchain 的 wiki.py 相同：主命名空间放在 0/，
其他命名空间用中文目录名（模板、模块、零件……），子页面对应子目录。
拉取时记下页面版本号（WIKI_DIR/.revisions.json），保存时据此检测编辑冲突，
线上在拉取后被他人修改时会报错而不会覆盖。

英文镜像与中文镜像平行存放，目录规则和 .revisions.json 相同。区别是英文站有只差大小写的标题，
撞名的文件加 ~pageid 后缀，记录里另存实际路径和内容哈希；本地改过的文件默认不覆盖；
每次拉取的变更追加到 EN_WIKI_DIR/.changes.tsv。
"""

import argparse
from collections import Counter
import datetime
import difflib
import hashlib
import html
import http.cookiejar
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ── 配置 ────────────────────────────────────────────────────


def _load_dotenv():
    for folder in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        path = os.path.join(folder, ".env")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
        return


_load_dotenv()
BASE_URL = os.environ.get("BASE_URL") or "https://gtnh.huijiwiki.com/api.php"
AUTHKEY = os.environ.get("AUTHKEY", "")
WIKI_DIR = os.environ.get("WIKI_DIR") or os.path.join(os.getcwd(), "wikitext")
EN_BASE_URL = os.environ.get("EN_BASE_URL") or "https://wiki.gtnewhorizons.com/w/api.php"
EN_DIR = os.environ.get("EN_WIKI_DIR") or os.path.join(os.getcwd(), "wikitext-en")
USER_AGENT = "GTNH-Huijiwiki-Editing/wiki.py"

_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_account = None

# ── 请求 ────────────────────────────────────────────────────


def _request(params):
    if not AUTHKEY:
        raise RuntimeError("缺少 AUTHKEY：灰机 Wiki 会拦截不带 Authkey 的 API 请求，请在 .env 中填写")
    params = dict(params, format="json", formatversion="2")
    headers = {"X-authkey": AUTHKEY, "User-Agent": USER_AGENT}
    # 读请求也用 POST：GET 结果可能被 CDN 缓存，读到旧版本会让冲突检测失效。
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(BASE_URL, data=data, headers=headers)
    result = json.loads(_opener.open(req, timeout=120).read())
    if "error" in result:
        error = result["error"]
        raise RuntimeError(f"API 错误 {error.get('code')}：{error.get('info')}")
    return result


def api_get(**params):
    return _request(params)


api_post = api_get


def _en_send(request):
    """单独成函数：不经过中文站的 opener，因此不会带上它的 Cookie。"""
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def en_api(**params):
    """请求英文维基。只用于读取：不发送中文站的 Authkey、Cookie 或账号。"""
    params = dict(params, format="json", formatversion="2", maxlag="5")
    data = urllib.parse.urlencode(params).encode("utf-8")
    attempts = 4
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(EN_BASE_URL, data=data, headers={"User-Agent": USER_AGENT})
        try:
            result = _en_send(request)
        except urllib.error.HTTPError as error:
            if attempt == attempts or not (error.code == 429 or error.code >= 500):
                raise RuntimeError(f"英文站请求失败：HTTP {error.code}") from error
        except (OSError, ValueError) as error:
            if attempt == attempts:
                raise RuntimeError(f"英文站请求失败：{error}") from error
        else:
            if "error" not in result:
                return result
            code = result["error"].get("code")
            if code != "maxlag" or attempt == attempts:
                raise RuntimeError(f"英文站 API 错误 {code}：{result['error'].get('info')}")
        time.sleep(3 * attempt)


def _token(kind="csrf"):
    return api_get(action="query", meta="tokens", type=kind)["query"]["tokens"][kind + "token"]


# ── 登录 ────────────────────────────────────────────────────


def whoami():
    info = api_get(action="query", meta="userinfo", uiprop="groups|rights")["query"]["userinfo"]
    return info


def login(bot=False):
    """登录个人账号；bot=True 时登录机器人账号并核对账号名。"""
    global _account
    prefix = "BOT" if bot else "EDITOR"
    username = os.environ.get(prefix + "_USERNAME", "")
    password = os.environ.get(prefix + "_PASSWORD", "")
    if not (username and password):
        raise RuntimeError(f"缺少 {prefix}_USERNAME 或 {prefix}_PASSWORD")
    result = api_post(action="login", lgname=username, lgpassword=password,
                      lgtoken=_token("login"))["login"]
    if result.get("result") != "Success":
        raise RuntimeError(f"登录失败：{result.get('reason', result.get('result'))}")
    name = whoami()["name"]
    if bot:
        # 机器人编辑必须确实落在机器人账号上，且不能与个人账号相同。
        if name != username or name == os.environ.get("EDITOR_USERNAME"):
            raise RuntimeError(f"机器人账号核对失败：API 返回 {name}")
    _account = {"name": name, "bot": bot}
    return name


# ── 页面读写 ─────────────────────────────────────────────────


def get_page(title, en=False):
    """返回 {'title','text','revid','timestamp','contentmodel'}；页面不存在时 text 为 None。

    en=True 时读英文维基。"""
    api = en_api if en else api_get
    page = api(action="query", titles=title, prop="revisions|info",
               rvprop="ids|timestamp|content", rvslots="main")["query"]["pages"][0]
    if page.get("missing"):
        return {"title": page["title"], "text": None, "revid": None, "timestamp": None,
                "contentmodel": page.get("contentmodel")}
    rev = page["revisions"][0]
    return {"title": page["title"], "text": rev["slots"]["main"]["content"], "revid": rev["revid"],
            "timestamp": rev["timestamp"], "contentmodel": rev["slots"]["main"].get("contentmodel")}


def edit(title, text, summary, bot=False, minor=False, baserevid=None, basetimestamp=None, createonly=False):
    """保存页面。bot=True 时要求已用机器人账号登录，并带 bot=1。"""
    if bot and not (_account and _account["bot"]):
        raise RuntimeError("机器人编辑前请先 login(bot=True)")
    params = {"action": "edit", "title": title, "text": text, "summary": summary, "token": _token()}
    if bot:
        params["bot"] = "1"
    if minor:
        params["minor"] = "1"
    if baserevid:
        params["baserevid"] = str(baserevid)
    if basetimestamp:
        params["basetimestamp"] = basetimestamp
        params["starttimestamp"] = basetimestamp
    if createonly:
        params["createonly"] = "1"
    return api_post(**params)["edit"]


def parse(text, title, prop="text|categories|limitreportdata", en=False):
    api = en_api if en else api_post
    return api(action="parse", text=text, title=title, prop=prop,
               contentmodel="wikitext", disablelimitreport="0")["parse"]


def lua(code, module="Module:沙盒/wiki.py"):
    """在 Scribunto 控制台运行一段 Lua，返回 mw.log 输出与返回值。不需要登录，不会保存任何页面。

    例：lua("local D=require('Module:Database'); mw.logObject(D.queryMaterial('氮').OrePrefixes)")
    """
    result = api_post(action="scribunto-console", title=module, content="return {}",
                      question=code, clear="1")
    if result.get("type") == "error":
        raise RuntimeError("Lua 错误：" + str(result.get("message") or result.get("html")))
    return (result.get("print") or "") + (result.get("return") or "")


def purge(titles, links=False):
    params = {"action": "purge", "titles": "|".join(titles)}
    if links:
        params["forcelinkupdate"] = "1"
    return api_post(**params).get("purge", [])


# ── 本地镜像 ─────────────────────────────────────────────────

_NS_DIRS = {"Template": "模板", "Module": "模块", "Gadget": "零件", "Gadget definition": "零件定义",
            "Category": "分类", "File": "文件"}
_EXT = {"wikitext": ".wikitext", "Scribunto": ".lua", "javascript": ".js", "css": ".css",
        "sanitized-css": ".css", "json": ".json"}
_UNSAFE = [("%", "%25"), (":", "%3A"), ("\\", "%5C"), ("*", "%2A"), ("?", "%3F"),
           ('"', "%22"), ("<", "%3C"), (">", "%3E"), ("|", "%7C")]


def _encode(part):
    for src, dst in _UNSAFE:
        part = part.replace(src, dst)
    return part


def _decode(part):
    for src, dst in reversed(_UNSAFE):
        part = part.replace(dst, src)
    return part


def title_to_path(title, contentmodel=None, root=None):
    ns, sep, leaf = title.partition(":")
    if not sep:
        ns, leaf = "", title
    folder = _NS_DIRS.get(ns, ns) if ns else "0"
    ext = _EXT.get(contentmodel or "", ".lua" if folder == "模块" else ".wikitext")
    if leaf.lower().endswith(ext):
        ext = ""
    return os.path.join(root or WIKI_DIR, folder, *[_encode(p) for p in leaf.split("/")]) + ext


def _is_inside(path, folder):
    root = os.path.normcase(os.path.abspath(folder))
    return os.path.normcase(os.path.abspath(path)).startswith(root + os.sep)


def is_en_path(path):
    """文件是否位于英文镜像中。"""
    return _is_inside(path, EN_DIR)


def _path_key(rel):
    return os.path.normcase(rel.replace("\\", "/"))


def path_to_title(path):
    root = WIKI_DIR
    if is_en_path(path):
        root = EN_DIR
        # 撞名的文件带后缀，不能从文件名反推标题，先查拉取记录。
        key = _path_key(os.path.relpath(os.path.abspath(path), os.path.abspath(EN_DIR)))
        for title, record in _load_revisions(EN_DIR).items():
            if _path_key(record["path"]) == key:
                return title
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    for ext in (".wikitext", ".lua"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    parts = [_decode(p) for p in rel.split(os.sep)]
    return "/".join(parts[1:]) if parts[0] == "0" else parts[0] + ":" + "/".join(parts[1:])


def _revisions_path(root=None):
    return os.path.join(root or WIKI_DIR, ".revisions.json")


_revisions_lock = threading.RLock()


def _load_revisions(root=None):
    try:
        with open(_revisions_path(root), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_revisions(data):
    os.makedirs(WIKI_DIR, exist_ok=True)
    with open(_revisions_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def pull(title, en=False):
    """拉取一个页面，返回本地路径。en=True 时从英文站拉到英文镜像。"""
    if en:
        result = pull_en([title], report=lambda message: None)
        if result["conflicts"]:
            raise RuntimeError(f"本地文件改过，没有覆盖：{result['conflicts'][0]}")
        if result["unavailable"]:
            raise RuntimeError(f"页面不存在：{title}")
        return os.path.join(EN_DIR, _load_revisions(EN_DIR)[result["titles"][0]]["path"])
    page = get_page(title)
    if page["text"] is None:
        raise RuntimeError(f"页面不存在：{title}")
    # 用请求时的标题定位文件和记录版本：API 会把「Project:」等前缀规范成站点名称，
    # 与本地路径换算出的标题不一致。
    path = title_to_path(title, page["contentmodel"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(page["text"])
    with _revisions_lock:
        revisions = _load_revisions()
        revisions[path_to_title(path)] = {"revid": page["revid"], "timestamp": page["timestamp"]}
        _save_revisions(revisions)
    return path


def push(path, summary, bot=False, minor=False):
    """保存本地文件。已有页面必须先 pull，并以拉取时的版本为基准检测编辑冲突。"""
    if is_en_path(path):
        raise RuntimeError(f"英文镜像只读，不能保存：{path}")
    title = path_to_title(path)
    with _revisions_lock:
        base = _load_revisions().get(title)
    current = get_page(title)
    if base:
        # MediaWiki 不把同一账号的先后修改视为冲突，所以在本地先比对版本号。
        if current["revid"] != base["revid"]:
            raise RuntimeError(f"{title} 在你拉取后又被修改过（线上 revid={current['revid']}，"
                               f"拉取时 revid={base['revid']}），请先备份本地修改，再 pull 合并")
        result = edit(title, _read(path), summary, bot=bot, minor=minor,
                      baserevid=base["revid"], basetimestamp=base["timestamp"])
    else:
        if current["text"] is not None:
            raise RuntimeError(f"{title} 已存在但没有拉取记录，请先 pull 并合并你的修改")
        result = edit(title, _read(path), summary, bot=bot, minor=minor, createonly=True)
    if "newrevid" in result:
        with _revisions_lock:
            revisions = _load_revisions()
            revisions[title] = {"revid": result["newrevid"], "timestamp": result["newtimestamp"]}
            _save_revisions(revisions)
    return title, result


MAX_RECOMMENDED_JOBS = 8


def _push_message(title, result):
    return f"{title}：{'无变化' if 'nochange' in result else '已保存 revid=' + str(result.get('newrevid'))}"


def push_many(paths, summary, bot=False, minor=False, jobs=1, report=print):
    """保存多个本地文件，返回没有保存成功的数量。

    jobs=1 时按顺序保存，遇到错误立即抛出；jobs>1 时用多个线程同时保存（每个线程一次保存一个页面，
    等服务器保存并解析完再取下一个），单个页面失败不影响其他页面，最后汇总失败。
    并行保存极其容易给服务器造成负载，jobs 通常设为 8 或更低。
    """
    paths = list(dict.fromkeys(paths))
    if jobs < 1:
        raise RuntimeError("并行数必须大于 0")
    if jobs == 1:
        for path in paths:
            report(_push_message(*push(path, summary, bot=bot, minor=minor)))
        return 0
    jobs = min(jobs, len(paths)) or 1
    lock = threading.Lock()
    queue = list(reversed(paths))
    stop = threading.Event()
    counters = {"done": 0, "fail": 0}

    def worker():
        while not stop.is_set():
            with lock:
                if not queue:
                    return
                path = queue.pop()
            try:
                message, failed = _push_message(*push(path, summary, bot=bot, minor=minor)), False
            except Exception as error:  # 单个页面失败（冲突、超时等）不拖累其余页面
                message, failed = f"{path}：失败 {error}", True
            with lock:
                counters["done"] += 1
                counters["fail"] += failed
                report(f"[{counters['done']}/{len(paths)}] {message}")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(jobs)]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            while thread.is_alive():
                thread.join(timeout=0.5)
    except KeyboardInterrupt:
        stop.set()
        report("已中断：正在等待进行中的保存结束……")
        for thread in threads:
            thread.join()
    return counters["fail"] + len(queue)


# ── 英文镜像（只读） ─────────────────────────────────────────

EN_BATCH = 50
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *(f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10))}


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path):
    with open(path, "rb") as f:
        return _sha256(f.read())


def _write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)


def _en_new_path(page, records):
    """给第一次拉取的页面分配相对路径，避开 Windows 上无法并存的名字。"""
    full = title_to_path(page["title"], page.get("contentmodel"), root=EN_DIR)
    parts = os.path.relpath(full, EN_DIR).replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.split(".")[0].upper() in _WINDOWS_DEVICES or (i < len(parts) - 1 and part.endswith((".", " "))):
            parts[i] = "".join(f"%{byte:02X}" for byte in part.encode("utf-8"))
    files = {r["path"].casefold() for t, r in records.items() if t != page["title"]}
    folders = {p.rsplit("/", n)[0] for p in files for n in range(1, p.count("/") + 1)}
    for i in range(1, len(parts)):
        if "/".join(parts[:i]).casefold() in files:  # 需要的目录已经是别的页面的文件
            parts[i - 1] += "~dir"
    rel = "/".join(parts)
    if rel.casefold() in files or rel.casefold() in folders:
        stem, ext = os.path.splitext(rel)
        rel = f"{stem}~{page['pageid']}{ext}"
    return rel


def _en_query_pages(params):
    """查询一批页面并合并续页（内容太多时 API 会分几次返回），返回 (页面列表, 标题规范化表)。"""
    pages, normalized, more = {}, {}, {}
    while True:
        result = en_api(**dict(params, **more))
        query = result.get("query", {})
        normalized.update({n["from"]: n["to"] for n in query.get("normalized", [])})
        for page in query.get("pages", []):
            pages.setdefault(page.get("pageid") or page.get("title"), {}).update(page)
        if "continue" not in result:
            return list(pages.values()), normalized
        more = result["continue"]


def _en_fate(title):
    """线上没有这个标题时，从日志里查它去哪了。"""
    events = en_api(action="query", list="logevents", letitle=title, lelimit="10")["query"]["logevents"]
    for event in events:
        if event.get("type") == "move":
            return f"改名为 {event.get('params', {}).get('target_title', '?')}（{event['timestamp'][:10]}）"
        if event.get("type") == "delete" and event.get("action") == "delete":
            return f"已删除（{event['timestamp'][:10]}）"
    return "日志中没有改名或删除记录"


class _EnSync:
    """一次英文拉取的状态：拉取记录、统计和待写入的变更日志。"""

    def __init__(self, force, report):
        if (os.path.abspath(EN_DIR) == os.path.abspath(WIKI_DIR)
                or _is_inside(EN_DIR, WIKI_DIR) or _is_inside(WIKI_DIR, EN_DIR)):
            raise RuntimeError("EN_WIKI_DIR 必须与中文镜像 WIKI_DIR 分开，不能互相包含")
        self.force, self.report = force, report
        self.records = _load_revisions(EN_DIR)
        self.time = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        self.stats = {"scanned": 0, "unchanged": 0, "added": [], "updated": [], "restored": [],
                      "gone": [], "conflicts": [], "unavailable": [], "titles": []}
        self.pending = []

    def save(self):
        """先写变更日志，再写记录。"""
        if self.pending:
            path = os.path.join(EN_DIR, ".changes.tsv")
            os.makedirs(EN_DIR, exist_ok=True)
            header = not os.path.exists(path)
            with open(path, "a", encoding="utf-8", newline="") as f:
                if header:
                    f.write("拉取时间\t类型\t标题\t旧revid\t新revid\t备注\n")
                for row in self.pending:
                    f.write("\t".join([self.time, *map(str, row)]) + "\n")
            self.pending = []
        data = json.dumps(self.records, ensure_ascii=False, indent=1).encode("utf-8")
        _write_atomic(_revisions_path(EN_DIR), data)

    def change(self, kind, key, title, old="", new="", note=""):
        self.stats[key].append(title)
        self.pending.append((kind, title, old, new, note))
        detail = f" {old} → {new}" if old and new and old != new else (f" revid={new}" if new else "")
        self.report(f"{kind}：{title}{detail}{' ' + note if note else ''}")

    def conflict(self, title, reason):
        self.stats["conflicts"].append(title)
        self.report(f"冲突：{title} {reason}，没有覆盖")

    def gone(self, title):
        record = self.records[title]
        if not record.get("gone"):
            record["gone"] = _en_fate(title)
            self.change("线上已无", "gone", title, record["revid"], "", record["gone"] + "；本地文件保留")

    def batch(self, field, values):
        query = {"action": "query", "prop": "revisions|info", "rvprop": "ids|timestamp",
                 field: "|".join(map(str, values))}
        pages, normalized = _en_query_pages(query)
        if field == "titles":
            found = {p.get("title") for p in pages}
            for requested in values:
                if normalized.get(requested, requested) not in found:  # 例如跨维基链接
                    self.stats["unavailable"].append(requested)
        needed = {}
        for page in pages:
            self.stats["scanned"] += 1
            title = page.get("title")
            if page.get("missing") or page.get("invalid") or not page.get("revisions"):
                if title in self.records:
                    self.gone(title)
                self.stats["unavailable"].append(title or str(page.get("pageid")))
                continue
            record = self.records.get(title)
            path = os.path.join(EN_DIR, record["path"]) if record else None
            exists = bool(path) and os.path.exists(path)
            if exists and not self.force and _file_sha256(path) != record["sha256"]:
                self.conflict(title, "本地文件改过")
            elif (exists and record["revid"] == page["revisions"][0]["revid"]
                    and _file_sha256(path) == record["sha256"]):
                record.pop("gone", None)
                self.stats["unchanged"] += 1
                self.stats["titles"].append(title)
            else:
                needed[page["pageid"]] = page
        if needed:
            pages, _ = _en_query_pages({"action": "query", "prop": "revisions|info",
                                        "rvprop": "ids|timestamp|content", "rvslots": "main",
                                        "pageids": "|".join(map(str, needed))})
            try:
                for page in pages:
                    self.store(page)
            finally:
                self.save()  # 写到一半中断时也要记下已写入的页面，否则下次会误报本地改过
        self.save()

    def store(self, page):
        title = page.get("title")
        revision = (page.get("revisions") or [{}])[0]
        slot = revision.get("slots", {}).get("main", {})
        if "content" not in slot:
            self.stats["unavailable"].append(title or str(page.get("pageid")))
            return
        model = slot.get("contentmodel", page.get("contentmodel"))
        record = self.records.get(title)
        rel = record["path"] if record else _en_new_path(dict(page, contentmodel=model), self.records)
        path = os.path.join(EN_DIR, rel)
        data = slot["content"].encode("utf-8")
        # 没有拉取记录、磁盘上却已有内容不同的文件，是别人放的，同样不覆盖。
        if not record and os.path.exists(path) and not self.force and _file_sha256(path) != _sha256(data):
            self.conflict(title, f"目标位置已有没有拉取记录的文件 {rel}")
            return
        if not record:
            kind, key = "新增", "added"
        elif record["revid"] != revision["revid"]:
            kind, key = "更新", "updated"
        else:
            kind, key = "还原", "restored"
        _write_atomic(path, data)
        old = record["revid"] if record else ""
        self.records[title] = {"revid": revision["revid"], "timestamp": revision["timestamp"],
                               "pageid": page["pageid"], "ns": page["ns"], "path": rel,
                               "sha256": _sha256(data), "redirect": bool(page.get("redirect"))}
        self.stats["titles"].append(title)
        self.change(kind, key, title, old, revision["revid"], "（重定向）" if page.get("redirect") else "")


def pull_en(titles=None, all_pages=False, namespaces=None, force=False, report=print):
    """把英文站页面的当前源码拉到英文镜像，只下载有变化或本地缺失的页面。

    titles 与 all_pages 二选一。重定向保存它自己的源码；不下载图片和历史版本。
    all_pages=True 时还会标出记录里有、线上已经改名或删除的标题（本地文件不删）。
    返回统计：added/updated/restored/gone/conflicts/unavailable/titles 为标题列表，
    scanned、unchanged 为数量；titles 是本地内容已与线上一致的页面。
    """
    if bool(titles) == bool(all_pages):
        raise RuntimeError("请指定英文页面标题，或使用 --all（二选一）")
    sync = _EnSync(force, report)
    if not all_pages:
        titles = list(dict.fromkeys(titles))
        for i in range(0, len(titles), EN_BATCH):
            sync.batch("titles", titles[i:i + EN_BATCH])
        return sync.stats
    if namespaces is None:
        info = en_api(action="query", meta="siteinfo", siprop="namespaces")["query"]["namespaces"]
        namespaces = sorted(int(n) for n in info if int(n) >= 0)
    for namespace in namespaces:
        listed, params = [], {"action": "query", "list": "allpages", "apnamespace": str(namespace),
                              "aplimit": "500"}
        while True:
            result = en_api(**params)
            listed.extend(result["query"]["allpages"])
            if "continue" not in result:
                break
            params.update(result["continue"])
        # 整个命名空间的列表取完之后，才能断定哪些标题已经不在线上。
        live = {p["title"] for p in listed}
        for title, record in list(sync.records.items()):
            if record["ns"] == namespace and title not in live:
                sync.gone(title)
        sync.save()
        for i in range(0, len(listed), EN_BATCH):
            sync.batch("pageids", [p["pageid"] for p in listed[i:i + EN_BATCH]])
    return sync.stats


def _en_revision_pair(title, revid):
    """返回 (旧修订, 当前页面)；旧修订必须属于同一页面。"""
    result = en_api(action="query", revids=str(revid), prop="revisions",
                    rvprop="ids|timestamp|content", rvslots="main")["query"]
    if not result.get("pages"):
        raise RuntimeError(f"英文站没有修订 {revid}")
    old = result["pages"][0]
    current = get_page(title, en=True)
    if current["text"] is None:
        raise RuntimeError(f"英文站页面不存在：{title}")
    if old["title"] != current["title"]:
        raise RuntimeError(f"修订 {revid} 属于页面 {old['title']}，不是 {current['title']}")
    return old["revisions"][0], current


def en_diff_since(title, revid):
    """英文页面从修订 revid 到现在的差异，用来对照译文需要同步什么。"""
    revision, current = _en_revision_pair(title, revid)
    lines = difflib.unified_diff(
        revision["slots"]["main"]["content"].splitlines(), current["text"].splitlines(),
        f"{current['title']} revid={revid} {revision['timestamp']}",
        f"{current['title']} revid={current['revid']} {current['timestamp']}", lineterm="")
    return "\n".join(lines)


def _plain_line(line):
    """去掉文件链接、链接写法和粗斜体，只留读者看到的文字。"""
    line = re.sub(r"\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", " ", line)
    line = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]", r"\1", line)
    line = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", line)
    return re.sub(r"\s+", " ", re.sub(r"'{2,}", "", line)).strip()


def _sentence_key(sentence):
    return re.sub(r"[\W_]+", "", sentence).lower()


def _sentences(text):
    """依次给出 (章节名, 所在行, 句子)。"""
    section = "导言"
    for raw in text.replace("\r\n", "\n").split("\n"):
        heading = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", raw)
        if heading:
            section = _plain_line(heading.group(2))
            continue
        line = _plain_line(raw)
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\[\'\"*])", line):
            if len(_sentence_key(part)) >= 8:
                yield section, line, part


def sentence_changes(old, new, near=0.62, small=6):
    """比较两版英文 wikitext，章节挪动和重排不算改动。

    返回 (新增与改动, 删去)。前者每项为 {section, sentence, line, old, changes}：
    old 是旧版中相近的句子（全新的句子为 None），changes 在改动很少时列出 (旧词, 新词)。
    """
    old_items, new_items = list(_sentences(old)), list(_sentences(new))
    old_pool = [item[2] for item in old_items]
    old_all = "".join(_sentence_key(x) for x in old_pool)
    new_all = "".join(_sentence_key(item[2]) for item in new_items)
    added = []
    for section, line, sentence in new_items:
        if _sentence_key(sentence) in old_all:
            continue
        entry = {"section": section, "sentence": sentence, "line": line, "old": None, "changes": None}
        match = difflib.get_close_matches(sentence, old_pool, n=1, cutoff=near)
        if match:
            entry["old"] = match[0]
            a, b = re.findall(r"\w+|[^\w\s]", match[0]), re.findall(r"\w+|[^\w\s]", sentence)
            ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
            if sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in ops) <= small:
                entry["changes"] = [(" ".join(a[i1:i2]), " ".join(b[j1:j2])) for _, i1, i2, j1, j2 in ops]
        added.append(entry)
    new_pool = [item[2] for item in new_items]
    removed = [(section, sentence) for section, _, sentence in old_items
               if _sentence_key(sentence) not in new_all
               and not difflib.get_close_matches(sentence, new_pool, n=1, cutoff=near)]
    return added, removed


def _format_sentence_changes(added, removed):
    out, last = [], None
    for item in added:
        if item["section"] != last:
            last = item["section"]
            out.append(f"\n== {last}")
        mark = "~" if item["old"] else "+"
        out.append(f"{mark} {item['sentence']}")
        # 句子不在行首时带上这一行的开头，否则看不出它说的是哪个列表项或表格行
        if not item["line"].startswith(item["sentence"]):
            out.append(f"    所在行：{item['line'][:80]}")
        if item["changes"] is not None:
            out.append("    改：" + "；".join(f"“{a}”→“{b}”" for a, b in item["changes"]))
        elif item["old"]:
            out.append(f"    旧：{item['old']}")
    if removed:
        out.append("\n######## 删去的句子")
        out += [f"- [{section}] {sentence}" for section, sentence in removed]
    return "\n".join(out).strip()


def unlisted_changes(old, new):
    """按句比较看不到的改动：太短的行（表格单元格、版本号、短参数值）和链接地址。

    返回按出现顺序排列的“+ 内容”“- 内容”。只比较出现次数，整行挪动不算。
    """
    def short_lines(text):
        lines = (line.strip() for line in text.replace("\r\n", "\n").split("\n"))
        return Counter(line for line in lines
                       if _sentence_key(line) and len(_sentence_key(_plain_line(line))) < 8)

    def urls(text):
        return Counter(re.findall(r"https?://[^\s\[\]|<>{}]+", text))

    out = []
    for count in (short_lines, urls):
        before, after = count(old), count(new)
        out += [f"- {item}" for item in before - after]
        out += [f"+ {item}" for item in after - before]
    return out


def en_sentences_since(title, revid):
    """英文页面从修订 revid 到现在真正新增、改动和删去的句子（可读文本）。"""
    revision, current = _en_revision_pair(title, revid)
    old = revision["slots"]["main"]["content"]
    report = _format_sentence_changes(*sentence_changes(old, current["text"]))
    others = unlisted_changes(old, current["text"])
    if others:
        report += ("\n\n######## 另有短行或链接改动（按句比较看不出位置，用不带 --sentences 的差异核对）\n"
                   + "\n".join(others))
    return report.strip()


# ── 预览检查 ─────────────────────────────────────────────────


def check(path_or_text, title=None, en=None):
    """预览本地内容，返回 Lua 错误、条目校验提示、高开销函数次数与分类。

    en 不指定时，英文镜像里的文件用英文站的模板渲染。"""
    is_file = os.path.isfile(path_or_text)
    if en is None:
        en = is_file and is_en_path(path_or_text)
    text = _read(path_or_text) if is_file else path_or_text
    title = title or path_to_title(path_or_text)
    result = parse(text, title, en=en)
    page_html = result["text"]
    strip = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    report = {
        "title": title,
        "lua_errors": [strip(m) for m in re.findall(r'class="scribunto-error[^"]*"[^>]*>(.*?)</', page_html)],
        "issues": [(code, level, strip(body)) for code, level, body in
                   re.findall(r'data-code="([^"]+)" data-level="([^"]+)">(.*?)</li>', page_html, re.S)],
        "categories": [c["category"] for c in result.get("categories", [])],
        "html": page_html,
    }
    for item in result.get("limitreportdata", []):
        if item["name"] == "limitreport-expensivefunctioncount":
            report["expensive"] = f"{item['0']}/{item['1']}"
    return report


# ── 命令行 ───────────────────────────────────────────────────


def _cli_pull(args):
    zh_titles = [path_to_title(f) for f in args.files if not is_en_path(f)]
    en_titles = [path_to_title(f) for f in args.files if is_en_path(f)]
    (en_titles if args.en else zh_titles).extend(args.titles)
    if args.all:
        if not args.en or args.titles or args.files:
            raise RuntimeError("--all 只能与 --en 连用，且不能再指定标题或文件")
    elif args.namespace:
        raise RuntimeError("--namespace 只能与 --all 连用")
    if args.force and not (args.all or en_titles):
        raise RuntimeError("--force 只用于英文拉取")
    for title in zh_titles:
        print(f"已拉取：{title} → {pull(title)}")
    if not (args.all or en_titles):
        return
    stats = pull_en(en_titles, all_pages=args.all, namespaces=args.namespace, force=args.force)
    counts = "，".join(f"{label} {len(stats[key])}" for key, label in [
        ("added", "新增"), ("updated", "更新"), ("restored", "还原"), ("gone", "线上已无"),
        ("conflicts", "冲突"), ("unavailable", "取不到")])
    print(f"英文镜像：{EN_DIR}\n扫描 {stats['scanned']}，未变 {stats['unchanged']}，{counts}")
    if stats["added"] or stats["updated"] or stats["restored"] or stats["gone"]:
        print(f"变更明细已追加到 {os.path.join(EN_DIR, '.changes.tsv')}")
    for title in stats["unavailable"]:
        print(f"取不到：{title}")
    if stats["conflicts"] or stats["unavailable"]:
        raise RuntimeError("有页面没有拉取成功")


def _cli_diff(args):
    if args.since:
        titles = list(args.titles) + [path_to_title(f) for f in args.files]
        english = all(is_en_path(f) for f in args.files) and (args.en or not args.titles)
        if not english or len(titles) != 1:
            raise RuntimeError("--since 只用于英文页面，一次一个：diff --en 标题 --since 修订号")
        compare = en_sentences_since if args.sentences else en_diff_since
        print(compare(titles[0], args.since) or f"{titles[0]}：无差异")
        return
    if args.sentences:
        raise RuntimeError("--sentences 只能与 --since 连用")
    if args.titles or not args.files:
        raise RuntimeError("请用 -f 指定本地文件（只有 --since 可以直接给标题）")
    for path in args.files:
        title = path_to_title(path)
        english = is_en_path(path)
        remote = get_page(title, en=english)["text"] or ""
        label = "英文站" if english else "线上"
        lines = difflib.unified_diff(remote.splitlines(), _read(path).splitlines(),
                                     f"{label} {title}", f"本地 {path}", lineterm="")
        print("\n".join(lines) or f"{title}：无差异")


def _cli():
    parser = argparse.ArgumentParser(prog="wiki.py", description="GTNH 中文维基编辑者工具")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("whoami", help="登录并显示账号")
    p.add_argument("--bot", action="store_true")
    p = sub.add_parser("pull", help="拉取页面到本地")
    p.add_argument("titles", nargs="*")
    p.add_argument("-f", "--files", nargs="+", default=[])
    p.add_argument("--en", action="store_true", help="标题指英文维基页面，拉到英文镜像（只读）")
    p.add_argument("--all", action="store_true", help="与 --en 连用：拉取英文站全部命名空间的页面源码")
    p.add_argument("--namespace", type=int, action="append", help="与 --all 连用：只拉指定命名空间编号，可重复")
    p.add_argument("--force", action="store_true", help="英文拉取时允许覆盖本地改过的文件")
    p = sub.add_parser("preview", help="预览本地文件并报告问题")
    p.add_argument("-f", "--files", nargs="+", required=True)
    p.add_argument("--html", help="把渲染结果写入此 HTML 文件（仅第一个文件）")
    p = sub.add_parser("diff", help="比较本地文件与线上内容")
    p.add_argument("titles", nargs="*", help="仅与 --since 连用")
    p.add_argument("-f", "--files", nargs="+", default=[])
    p.add_argument("--en", action="store_true", help="标题指英文维基页面")
    p.add_argument("--since", type=int, metavar="REVID", help="显示英文页面从该修订到现在的差异")
    p.add_argument("--sentences", action="store_true", help="与 --since 连用：按句比较，忽略章节挪动和重排")
    p = sub.add_parser("push", help="保存本地文件")
    p.add_argument("-f", "--files", nargs="+", required=True)
    p.add_argument("-s", "--summary", required=True)
    p.add_argument("--bot", action="store_true", help="使用机器人账号并带 bot=1")
    p.add_argument("--minor", action="store_true")
    p.add_argument("-j", "--jobs", type=int, default=1,
                   help="并行保存的线程数，默认 1（顺序）。警告：并行保存极其容易给服务器造成负载，"
                        "通常设为 8 或更低；批量创建页面还可能触发限速")
    p = sub.add_parser("lua", help="在 Scribunto 控制台运行 Lua，用来查询线上数据库")
    p.add_argument("code", nargs="?", help="Lua 代码；用 mw.log / mw.logObject 输出")
    p.add_argument("-f", "--file", help="从文件读取 Lua 代码")
    p = sub.add_parser("purge", help="清除页面缓存")
    p.add_argument("titles", nargs="+")
    p.add_argument("--links", action="store_true", help="同时刷新链接表与分类")
    args = parser.parse_args()

    if args.command == "whoami":
        login(bot=args.bot)
        info = whoami()
        print(f"账号：{info['name']}\n用户组：{'、'.join(info.get('groups', []))}")
        rights = set(info.get("rights", []))
        for right, label in [("bot", "机器人标记"), ("delete", "删除"), ("move", "移动"),
                             ("editinterface", "编辑界面消息"), ("editsitejs", "编辑站点脚本")]:
            print(f"  {label}：{'有' if right in rights else '无'}")
    elif args.command == "pull":
        _cli_pull(args)
    elif args.command == "preview":
        # check() 也接受正文字符串；命令行里路径写错时若不拦下，会把路径本身当正文渲染而看似通过
        missing = [path for path in args.files if not os.path.isfile(path)]
        if missing:
            raise RuntimeError(f"找不到本地文件：{'、'.join(missing)}（主命名空间页面在 wikitext/0/ 下）")
        for index, path in enumerate(args.files):
            report = check(path)
            print(f"== {report['title']}  高开销函数 {report.get('expensive', '?')}")
            for error in report["lua_errors"]:
                print(f"  Lua 错误：{error}")
            for code, level, body in report["issues"]:
                print(f"  [{level}] {body}")
            print(f"  分类：{'、'.join(report['categories']) or '无'}")
            if args.html and index == 0:
                with open(args.html, "w", encoding="utf-8") as f:
                    f.write(report["html"])
    elif args.command == "diff":
        _cli_diff(args)
    elif args.command == "push":
        print(f"已登录：{login(bot=args.bot)}")
        if args.jobs > 1:
            print(f"警告：并行保存（{args.jobs} 个线程）极其容易给服务器造成负载，通常设为 {MAX_RECOMMENDED_JOBS} 或更低。",
                  file=sys.stderr)
            if args.jobs > MAX_RECOMMENDED_JOBS:
                print(f"警告：{args.jobs} 超过了建议的上限 {MAX_RECOMMENDED_JOBS}，请确认确实需要。", file=sys.stderr)
        failed = push_many(args.files, args.summary, bot=args.bot, minor=args.minor, jobs=args.jobs)
        if failed:
            sys.exit(f"错误：{failed} 个页面没有保存成功")
    elif args.command == "lua":
        if not (args.code or args.file):
            raise RuntimeError("请给出 Lua 代码，或用 -f 指定文件")
        print(lua(_read(args.file) if args.file else args.code))
    elif args.command == "purge":
        for item in purge(args.titles, links=args.links):
            print(f"{item['title']}：{'已清除' if 'purged' in item else '未清除'}")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        _cli()
    except RuntimeError as error:
        sys.exit(f"错误：{error}")


if __name__ == "__main__":
    main()
