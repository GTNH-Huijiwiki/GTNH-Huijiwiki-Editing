# GTNH-Huijiwiki-Editing

GTNH 中文维基的编辑技能（AI 代理可直接读取的 `SKILL.md`）。

## 目录

```
skills/
  <技能名>/
    SKILL.md    # 开头的 YAML 写 name、description，正文是技能说明
```

## 自动发布

`main` 分支上 `skills/` 目录有改动时，`.github/workflows/notify-publish.yml` 会通知
[GTNH-Huijiwiki-Actions](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Actions)，
由那边的发布流程把每个技能同步为维基页面 `Project:编辑技能/<技能名>`。

请在本仓库修改技能；维基上的对应页面会在下次发布时被覆盖。

### 需要的配置

| 位置 | 名称 | 说明 |
|---|---|---|
| 本仓库 Secrets | `ACTIONS_DISPATCH_TOKEN` | 细粒度 PAT 或 GitHub App 令牌，只授权 GTNH-Huijiwiki-Actions，权限 Contents: Read and write |
