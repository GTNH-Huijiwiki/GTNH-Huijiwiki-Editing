# 自动化编辑流程

返回[技能首页](../SKILL.md)。本页说明怎样用脚本或 AI 代理安全地读写维基，以及相关的权限与缓存。

## 准备工作

适用：所有编辑者。

### Authkey

灰机 Wiki 在 CDN 层对外部程序做了人机检测。不带 Authkey 直接请求 `https://gtnh.huijiwiki.com/api.php`，会收到 403 和一个「Just a moment...」质询页，读写都做不了。在请求头里带上 `X-authkey: <你的 Authkey>`，就能正常调用 MediaWiki API。

- **来源**：Authkey 由灰机 Wiki 为本站签发，向维基管理员索要。
- **用途**：只解决程序访问 API 的问题，不代表任何编辑权限；编辑权限由登录的账号决定。
- **保管**：只在本机 `.env` 或 CI 机密中保存，不要发到群聊、页面或提交记录。怀疑泄露时联系管理员更换。
- 浏览器里运行的零件脚本和普通网页浏览不需要 Authkey。

### 账号与权限

| 身份 | 环境变量 | 用途 | 说明 |
|---|---|---|---|
| 个人编辑账号 | `EDITOR_USERNAME`、`EDITOR_PASSWORD` | 日常编辑、少量页面修改 | 编辑记录归属于本人；权限取决于所在用户组 |
| 机器人账号 | `BOT_USERNAME`、`BOT_PASSWORD` | 短时间内大量编辑、数据上传、批量重定向与移动 | 本站机器人账号为「钛管道」；只交给维护者 |

用 `python wiki.py whoami` 可以查看自己账号所在的用户组和关键权限，加 `--bot` 查看机器人账号。以下是截至 2026-11-07 的实际情况，用户组调整后以 `whoami` 为准：

| 操作 | 需要的权限 | 机器人账号 | 管理员、开发者个人账号 |
|---|---|---|---|
| 普通页面、模板、模块、`Data:` 页面 | 编辑 | 可以 | 可以 |
| 机器人标记、删除、移动、保护、移动时不留重定向 | `bot`、`delete`、`move`、`protect`、`suppressredirect` | 可以 | 除机器人标记外可以 |
| 界面消息、站点 CSS（如 `MediaWiki:Common.css`） | `editinterface`、`editsitecss` | 可以 | 可以 |
| 零件脚本与零件定义、站点 JS（如 `MediaWiki:Common.js`） | `editsitejs`、`gadgets-edit`、`gadgets-definition-edit` | **不可以** | 需要开发者权限 |
| 修改页面内容模型 | `editcontentmodel` | 不可以 | 可以 |

- 零件和站点 JS 只能由有开发者权限的个人账号更新，自动化流程无法代劳。
- 机器人账号只用于批量或自动化编辑，不能当作个人账号使用；反过来，大量编辑也不要用个人账号刷屏最近更改。

### 本地环境

1. 安装 Python 3.9 或更高版本（脚本只用标准库）。
2. 把 [scripts/wiki.py](../scripts/wiki.py) 和 [scripts/.env.example](../scripts/.env.example) 复制到工作目录，将 `.env.example` 另存为 `.env` 并填写 `AUTHKEY` 与账号。
3. 运行 `python wiki.py whoami` 确认能登录；维护者再运行 `python wiki.py whoami --bot` 确认机器人账号。

## 编辑工具

适用：所有编辑者。

[scripts/wiki.py](../scripts/wiki.py) 是给编辑者用的单文件工具，页面保存在本地 `wikitext/` 目录（目录结构与[工具链](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain)的 `wiki.py` 一致，两者可以共用同一份镜像）：

| 命令 | 作用 |
|---|---|
| `python wiki.py whoami [--bot]` | 登录并显示当前账号与权限 |
| `python wiki.py pull 标题…` | 拉取页面到本地，并记录拉取时的版本号 |
| `python wiki.py preview -f 文件` | 用线上模板预览本地内容，报告 Lua 错误、条目校验提示、高开销函数次数和分类 |
| `python wiki.py diff -f 文件` | 比较本地文件与线上当前内容 |
| `python wiki.py push -f 文件… -s 摘要 [--bot]` | 保存；如果线上在你拉取之后又被别人改过，会报编辑冲突而不是覆盖 |
| `python wiki.py purge 标题… [--links]` | 清除页面缓存；`--links` 同时刷新链接表和分类 |
| `python wiki.py lua "代码"` | 在 Scribunto 控制台运行 Lua，查询线上数据库，不保存页面；用法见[事实核查](style.md#事实核查) |

本地镜像的目录与命名空间对应如下，子页面对应子目录：

| 目录 | 命名空间 | 文件后缀 |
|---|---|---|
| `0/` | 主命名空间（条目） | `.wikitext` |
| `模板/`、`模块/`、`分类/` | 模板、模块、分类 | `.wikitext`、`.lua`、`.wikitext` |
| `零件/`、`零件定义/` | 零件（Gadget）、零件定义 | 页面名自带 `.js`、`.css` |
| `Data/`、`Project/`、`MediaWiki/` 等 | 同名命名空间 | 按内容模型决定，默认 `.wikitext` |

新建文件时目录名一律用中文命名空间名（如 `模块/`），不要同时出现 `Module/` 和 `模块/`。

上传图片等文件时，使用[工具链](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain)中的 `wiki.py`（`python wiki.py push --upload 图片…`），本工具不处理文件上传。

本地 `wikitext/` 是线上页面的镜像，不是 Git 仓库：不要用 Git 提交、分支来管理页面编辑。

自己写脚本时要注意：GET 请求的 API 结果可能被 CDN 缓存，读到的是旧版本；需要最新内容（例如保存前核对版本）时用 POST 请求。`wiki.py` 的所有请求都用 POST。

## 标准流程

适用：所有编辑者。每次编辑都按顺序走完：

1. **拉取**：`python wiki.py pull 页面名`。已有页面一定要从线上当前版本开始改。
2. **修改**：只改需要改的部分，不要顺手重排无关内容。
3. **预览**：`python wiki.py preview -f wikitext/0/页面名.wikitext`。确认没有 Lua 错误；条目页的校验提示（缺重定向、未收录进导航、获取不到配方等）要处理掉，或确认是数据本身缺失。需要实际保存才能验证的改动（如脚本的保存流程），先在 `Project:沙盒/<你的用户名>/` 下自由测试，见[在沙盒里测试](style.md#在沙盒里测试)。
4. **保存**：`python wiki.py push -f … -s "简短的中文摘要"`。摘要写做了什么，例如「补充氧气罐续航表」。
5. **清缓存**：`python wiki.py purge 页面名 --links`。改了模板或模块时，还要清除用到它的测试页面。
6. **核对**：在浏览器里打开页面检查实际效果；改了样式或脚本时先强制刷新（见下文[缓存](#缓存)）。改动响应式布局时，宽屏和窄屏都要看。没有在线上核对过，就不要说问题已经修好；确实没法核对时，要说明原因。

## 批量与机器人编辑

适用：维护者。

- 短时间内编辑大量页面时，使用机器人账号（`--bot`），每次编辑都带 `bot=1`，不要刷屏最近更改。
- 机器人登录后先核对 API 返回的用户名就是机器人账号，再开始写入。`wiki.py` 的 `--bot` 会自动核对。
- 先在一两个页面上试，确认结果正确后再批量执行；批量脚本要能中断后从断点继续。
- 移动、删除页面前先查反向链接和重定向，处理完指向它的链接再动手。
- 数据库上传（`Data:Versions/…`）使用[工具链](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain)，不要用本工具手工逐页上传；除非明确需要，不要运行工具链的大范围上传、删除、图片上传或重定向脚本。工具链每次重新生成的任务数据库（`wiki_inventory.db`）不要提交到仓库。

## 缓存

适用：所有编辑者，维护者需要全部掌握。

维基上有四层缓存，表现为「改了但看不到」：

| 缓存 | 表现 | 处理办法 |
|---|---|---|
| 页面解析缓存 | 模板或模块改了，页面仍显示旧结果 | `purge` 该页面 |
| 链接表与分类 | 分类、反向链接、校验分类没更新 | `purge --links`；大量页面的更新由站点任务队列慢慢完成 |
| 异步加载内容 | 条目底部导航等异步内容仍是旧版 | 这类内容通过 CDN 上的解析请求加载，CDN 不一定按设定的时间过期，也无法从维基端清除；改动后需要等待，或请维护者调整加载参数 |
| 零件 JS/CSS | 改了脚本或样式，浏览器仍运行旧版 | 等几分钟让 ResourceLoader 更新版本，再按 `Ctrl+Shift+R` 强制刷新；`purge` 不能代替浏览器刷新 |

## GitHub 组织与自动化

适用：维护者。

工具与数据流程托管在 GitHub 组织 [GTNH-Huijiwiki](https://github.com/GTNH-Huijiwiki)：

| 仓库 | 作用 |
|---|---|
| [GTNH-Dumper](https://github.com/GTNH-Huijiwiki/GTNH-Dumper) | 游戏内数据导出模组，生成物品、配方、任务等原始导出 |
| [GTNH-Huijiwiki-Toolchain](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain) | 把导出拆分成 `Data:` 页面并上传，附带图标与图片重定向工具 |
| [GTNH-Huijiwiki-Actions](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Actions) | GitHub Actions 定时任务与发布流程，例如同步翻译进度、发布本技能 |
| [GTNH-Huijiwiki-Editing](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Editing) | 本技能的源文件 |
| [GTNH-Recipe-Check](https://github.com/GTNH-Huijiwiki/GTNH-Recipe-Check) | 基于导出数据的配方检查工具 |

自动化相关的约定：

- Actions 仓库的 `Wiki` 环境保存 `WIKI_AUTHKEY`、`BOT_USERNAME`、`BOT_PASSWORD` 三个机密，所有写维基的流程都在这个环境中运行。
- 本技能在 Editing 仓库的 `main` 分支更新后，由 Actions 仓库的「发布编辑技能到维基」流程自动发布到[维基上的技能页面](https://gtnh.huijiwiki.com/wiki/Project:编辑技能/gtnh-wiki-editing)。维基上的副本会被下次发布覆盖，修改请提交到 Editing 仓库。
