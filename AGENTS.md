# Agent Instructions

本仓库既是 GTNH 中文维基编辑技能的源仓库，也是推荐的本地编辑工作区。

## 编辑维基

- 编辑 GTNH 中文维基（gtnh.huijiwiki.com）时，按 `skills/gtnh-wiki-editing/SKILL.md` 及其 `references/` 中的文档操作。
- 在仓库根目录运行 `python skills/gtnh-wiki-editing/scripts/wiki.py …`。本地镜像在 `wikitext/`，账号与 Authkey 在 `.env`。
- `wikitext/` 是线上页面的镜像，不是 Git 管理的内容：不要提交镜像，也不要用 Git 分支来管理页面编辑。
- 每个任务开始时建立 `logs/<YYYY-MM-DD>-<任务名>/`，把改动前的备份、临时脚本、查询结果和 `记录.md` 放在里面。
- 批量编辑使用机器人账号（`--bot`），每次编辑都带 `bot=1`，并先核对登录的确实是机器人账号。
- 可以在 `Project:沙盒/<用户名>/` 下自由测试。

## 修改技能本身

- 只修改 `skills/` 下的源文件；维基上 `Project:编辑技能/` 的页面是发布生成的副本，会被下次发布覆盖。
- 文档之间用相对路径链接，指向本维基的页面写完整 URL，发布时会自动改写。
- 推送到 `main` 后，由 GTNH-Huijiwiki-Actions 的「发布编辑技能到维基」流程发布。
