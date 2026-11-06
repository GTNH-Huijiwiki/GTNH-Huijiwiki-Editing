# GTNH-Huijiwiki-Editing

GTNH 中文维基的编辑技能（AI 代理可直接读取的 `SKILL.md`）。

## 目录

```
skills/
  <技能名>/
    SKILL.md          # 技能首页：开头的 YAML 写 name、description
    references/*.md   # 分主题的详细文档，每份以一级标题开头
    scripts/          # 配套脚本，例如编辑者版 wiki.py
```

目前的技能：

- [gtnh-wiki-editing](skills/gtnh-wiki-editing/SKILL.md)：自动化编辑流程、维基技术现状、推荐编辑规范，附编辑者版
  [wiki.py](skills/gtnh-wiki-editing/scripts/wiki.py)。

文档之间请用相对路径链接（如 `references/style.md`），指向本维基页面时写完整 URL
（`https://gtnh.huijiwiki.com/wiki/页面名`），发布时会自动改写为维基内部链接。

## 作为编辑工作区

本仓库也是推荐的本地编辑工作区：在根目录放 `.env`，用 `python skills/gtnh-wiki-editing/scripts/wiki.py` 拉取和保存页面，
本地镜像在 `wikitext/`，每个任务的日志在 `logs/<日期>-<任务名>/`。这三者都在 `.gitignore` 中，不会被提交。
详见[自动化编辑流程](skills/gtnh-wiki-editing/references/automation.md#工作区)。

## 自动发布

`main` 分支上 `skills/` 目录有改动时，`.github/workflows/notify-publish.yml` 会通知
[GTNH-Huijiwiki-Actions](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Actions)，
由那边的发布流程把每个技能同步为维基页面：`SKILL.md` 发布为 `Project:编辑技能/<技能名>`，
其他 `.md` 文件发布为以其一级标题命名的子页面。

请在本仓库修改技能；维基上的对应页面会在下次发布时被覆盖。

### 需要的配置

| 位置 | 名称 | 说明 |
|---|---|---|
| 本仓库 Secrets | `ACTIONS_DISPATCH_TOKEN` | 细粒度 PAT 或 GitHub App 令牌，只授权 GTNH-Huijiwiki-Actions，权限 Contents: Read and write |
