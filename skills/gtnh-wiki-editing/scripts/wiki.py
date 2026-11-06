"""GTNH 中文维基编辑者工具（单文件，只依赖 Python 标准库）。

命令行用法：
    python wiki.py whoami [--bot]
    python wiki.py pull 标题 [标题 ...]
    python wiki.py pull -f 本地文件 [...]
    python wiki.py preview -f 本地文件 [--html 输出.html]
    python wiki.py diff -f 本地文件 [...]
    python wiki.py push -f 本地文件 [...] -s "摘要" [--bot] [--minor]
    python wiki.py purge 标题 [标题 ...] [--links]
    python wiki.py lua "Lua 代码" | -f 代码文件.lua

也可以作为库导入：
    import wiki
    wiki.login()                        # 个人账号；wiki.login(bot=True) 为机器人账号
    page = wiki.get_page("火箭")        # {'text', 'revid', 'timestamp', 'contentmodel'}
    wiki.edit("火箭", text, "摘要", baserevid=page["revid"])
    wiki.parse(text, "火箭")

配置从同目录或当前目录的 .env 读取（见 .env.example），环境变量优先：
    BASE_URL         默认 https://gtnh.huijiwiki.com/api.php
    AUTHKEY          灰机 Wiki 的 API Authkey（请求头 X-authkey），向维基管理员索要
    EDITOR_USERNAME / EDITOR_PASSWORD   个人编辑账号
    BOT_USERNAME / BOT_PASSWORD         机器人账号，仅维护者使用
    WIKI_DIR         本地镜像目录，默认 ./wikitext

本地镜像的目录结构与 GTNH-Huijiwiki-Toolchain 的 wiki.py 相同：主命名空间放在 0/，
其他命名空间用中文目录名（模板、模块、零件……），子页面对应子目录。
拉取时记下页面版本号（WIKI_DIR/.revisions.json），保存时据此检测编辑冲突，
线上在拉取后被他人修改时会报错而不会覆盖。
"""

import argparse
import difflib
import html
import http.cookiejar
import json
import os
import re
import sys
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


def get_page(title):
    """返回 {'title','text','revid','timestamp','contentmodel'}；页面不存在时 text 为 None。"""
    page = api_get(action="query", titles=title, prop="revisions|info",
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


def parse(text, title, prop="text|categories|limitreportdata"):
    return api_post(action="parse", text=text, title=title, prop=prop,
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


def title_to_path(title, contentmodel=None):
    ns, sep, leaf = title.partition(":")
    if not sep:
        ns, leaf = "", title
    folder = _NS_DIRS.get(ns, ns) if ns else "0"
    ext = _EXT.get(contentmodel or "", ".lua" if folder == "模块" else ".wikitext")
    if leaf.lower().endswith(ext):
        ext = ""
    return os.path.join(WIKI_DIR, folder, *[_encode(p) for p in leaf.split("/")]) + ext


def path_to_title(path):
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(WIKI_DIR))
    for ext in (".wikitext", ".lua"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    parts = [_decode(p) for p in rel.split(os.sep)]
    return "/".join(parts[1:]) if parts[0] == "0" else parts[0] + ":" + "/".join(parts[1:])


def _revisions_path():
    return os.path.join(WIKI_DIR, ".revisions.json")


def _load_revisions():
    try:
        with open(_revisions_path(), encoding="utf-8") as f:
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


def pull(title):
    page = get_page(title)
    if page["text"] is None:
        raise RuntimeError(f"页面不存在：{title}")
    # 用请求时的标题定位文件和记录版本：API 会把「Project:」等前缀规范成站点名称，
    # 与本地路径换算出的标题不一致。
    path = title_to_path(title, page["contentmodel"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(page["text"])
    revisions = _load_revisions()
    revisions[path_to_title(path)] = {"revid": page["revid"], "timestamp": page["timestamp"]}
    _save_revisions(revisions)
    return path


def push(path, summary, bot=False, minor=False):
    """保存本地文件。已有页面必须先 pull，并以拉取时的版本为基准检测编辑冲突。"""
    title = path_to_title(path)
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
        revisions = _load_revisions()
        revisions[title] = {"revid": result["newrevid"], "timestamp": result["newtimestamp"]}
        _save_revisions(revisions)
    return title, result


# ── 预览检查 ─────────────────────────────────────────────────


def check(path_or_text, title=None):
    """预览本地内容，返回 Lua 错误、条目校验提示、高开销函数次数与分类。"""
    text = _read(path_or_text) if os.path.isfile(path_or_text) else path_or_text
    title = title or path_to_title(path_or_text)
    result = parse(text, title)
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


def _cli():
    parser = argparse.ArgumentParser(prog="wiki.py", description="GTNH 中文维基编辑者工具")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("whoami", help="登录并显示账号")
    p.add_argument("--bot", action="store_true")
    p = sub.add_parser("pull", help="拉取页面到本地")
    p.add_argument("titles", nargs="*")
    p.add_argument("-f", "--files", nargs="+", default=[])
    p = sub.add_parser("preview", help="预览本地文件并报告问题")
    p.add_argument("-f", "--files", nargs="+", required=True)
    p.add_argument("--html", help="把渲染结果写入此 HTML 文件（仅第一个文件）")
    p = sub.add_parser("diff", help="比较本地文件与线上内容")
    p.add_argument("-f", "--files", nargs="+", required=True)
    p = sub.add_parser("push", help="保存本地文件")
    p.add_argument("-f", "--files", nargs="+", required=True)
    p.add_argument("-s", "--summary", required=True)
    p.add_argument("--bot", action="store_true", help="使用机器人账号并带 bot=1")
    p.add_argument("--minor", action="store_true")
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
        titles = list(args.titles) + [path_to_title(f) for f in args.files]
        for title in titles:
            print(f"已拉取：{title} → {pull(title)}")
    elif args.command == "preview":
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
        for path in args.files:
            title = path_to_title(path)
            remote = get_page(title)["text"] or ""
            lines = difflib.unified_diff(remote.splitlines(), _read(path).splitlines(),
                                         f"线上 {title}", f"本地 {path}", lineterm="")
            print("\n".join(lines) or f"{title}：无差异")
    elif args.command == "push":
        print(f"已登录：{login(bot=args.bot)}")
        for path in args.files:
            title, result = push(path, args.summary, bot=args.bot, minor=args.minor)
            print(f"{title}：{'无变化' if 'nochange' in result else '已保存 revid=' + str(result.get('newrevid'))}")
    elif args.command == "lua":
        if not (args.code or args.file):
            raise RuntimeError("请给出 Lua 代码，或用 -f 指定文件")
        print(lua(_read(args.file) if args.file else args.code))
    elif args.command == "purge":
        for item in purge(args.titles, links=args.links):
            print(f"{item['title']}：{'已清除' if 'purged' in item else '未清除'}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        _cli()
    except RuntimeError as error:
        sys.exit(f"错误：{error}")
