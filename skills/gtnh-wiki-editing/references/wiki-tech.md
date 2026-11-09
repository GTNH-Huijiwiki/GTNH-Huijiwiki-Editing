# 维基技术现状

返回[技能首页](../SKILL.md)。本页说明维基的数据从哪里来、怎样被查询，以及条目模板怎样使用这些数据。

数据库每个版本都有人持续上传和维护，版本号、数据集和字段都会变化。本页只讲结构与查法；文中标注“截至某日”的数字只是举例，动手前务必按[查看当前版本](#查看当前版本)的方法确认现状。

## 灰机 MongoDB

适用：维护者。编辑者了解即可。

灰机 Wiki 为每个站点提供一个 MongoDB 数据库：

- `Data:` 命名空间中的 JSON 与表格（`.tabx`、`.tab`）页面保存后，会被灰机写入数据库，文档的 `_id` 就是页面标题。
- Lua 模块用 `mw.huiji.db.find`、`mw.huiji.db.aggregate` 查询。查询时先用 `_id` 正则把范围限定在某个版本的数据目录，再展开、筛选需要的记录，不要做不限范围的全库扫描。
- 页面保存到入库之间有延迟。数据分片刚上传时可能暂时查不到，相关模块对此有补读源页的兜底。

开发时要记住的平台限制：

| 限制 | 影响 |
|---|---|
| 单个页面不超过 2 MB | 大数据集必须拆成编号连续的分片，例如 `Items/0.json`、`Items/1.json`…… |
| 每页 Lua 执行时间与内存有上限 | 一页里查询的物品、配方要批量查询，并复用已取得的记录 |
| 每页“高开销函数”最多 100 次 | `title.exists` 等每次计 1 次；`title.redirectTarget`、`title:getContent()` 不计。关联对象多的页面不要逐个调用 `exists` |

## 数据库版本

适用：维护者。编辑者了解即可。

### 查看当前版本

- [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database)：页首实时显示各来源当前使用的数据库版本，正文说明各数据集的路径与字段。
- [Data:Version.tab](https://gtnh.huijiwiki.com/wiki/Data:Version.tab)：GTNH 的版本表。`released` 表示是否已发布，`databaseSchema` 是数据结构版本（`none` 表示该版本没有数据库），`databaseAliases` 给出别名。附属模组（PH、TST、GTNL、EXTRA NERF 等）各有自己的 `Data:Version/<来源>.tab`。
- [模块:Database/Versions](https://gtnh.huijiwiki.com/wiki/模块:Database/Versions)：读取上述版本表，把别名和版本号解析成 `Data:Versions/<来源>/<版本>/` 数据目录。

### 别名

条目和模板通常不写死版本号，而是使用别名：

| 别名 | 含义 |
|---|---|
| `default` | 默认数据库。条目不填 `索引-数据版本` 时使用 |
| `legacy` | 旧结构的历史数据库，供旧版本子页使用 |
| `test` | 测试用数据库，可能为空 |
| `ph`、`tst`、`gtnl` 等 | 各附属模组自己的当前数据库 |

举例（截至 2026-11-07）：`default` 指向 GTNH 2.9.0，结构为 `v2`；`legacy` 指向 GTNH 2.8.4，结构为 `v1`。

### 新版本上线

适用：维护者。

1. 用 [GTNH-Dumper](https://github.com/GTNH-Huijiwiki/GTNH-Dumper) 在游戏内导出数据。
2. 用 [GTNH-Huijiwiki-Toolchain](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain) 拆分并上传到 `Data:Versions/<来源>/<版本>/`，同时生成该版本的配置模块。
3. 在[模块:Database/Versions](https://gtnh.huijiwiki.com/wiki/模块:Database/Versions)登记新版本，在版本表中填写 `databaseSchema`，确认无误后再把 `default` 等别名切换过去。
4. 同步更新 [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database)，写清这次改变了什么。

## 数据集

适用：维护者。编辑者了解即可。

每个版本目录下按数据集分子目录。具体有哪些数据集、每个字段的含义，以 [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database) 和实际 `Data:` 页面为准。常见数据集：

| 数据集 | 内容 |
|---|---|
| `Items`、`ItemNames` | 物品与流体：key、中英文名、Tooltip、模组、图标文件名、神秘时代要素等；`ItemNames` 用于按名称查找 |
| `Recipes/<模组>/<处理器>/` | NEI 中的全部配方，按配方处理器分目录 |
| `OreDictionary` | 矿物词典：矿辞名 → 物品 key 列表 |
| `Gtmaterial`、`Ticmaterial` | GT 材料与匠魂材料属性，包括材料各形态（`OrePrefixes`）和矿物处理配方 |
| `Ores` | 矿石辅助表，供矿物处理相关工具使用 |
| `Quests`、`QuestLines` | 任务书的任务与章节 |
| `gtnhdimension` | 维度属性：缩写、ID、星系环境参数等 |
| `Aspects`、`Tc4research` | 神秘时代要素与研究 |

物品图标保存在 `File:` 命名空间，文件名形如 `icon_<模组>_<物品>.png`；很多中文图片名是指向这些文件的重定向。写模板或计算器时优先用物品记录里的 `iconName` 精确取图，给编辑者看的示例可以用更易读的中文图片名。

### 字段速查

Project:Database 的字段说明有时落后于实际数据。写模块前，先用一条查询看实际记录有哪些字段。举例（截至 2026-11-07 的 `default` 数据库）：

- **物品记录**：`key`、`rawKey`、`translatedName`、`originalName`、`tooltips`、`tooltipStats`、`mod`、`iconName`、`frameCount`、`size`、`aspect` 等。图标字段现在是 `iconName`，旧文档里写的 `icon` 已不再使用。
- **配方记录**：`inputItems`、`outputItems`、`inputFluids`、`outputFluids`、`eut`（EU/t）、`duration`（tick）、`nbtSensitive`、`sourceMod`、`index`。物品槽位可能是字符串、带 `key`／`amount`／`chance` 的对象，或候选物品数组。
- **专有字段**：部分处理器的配方带有 `metadata` 等专有字段，例如光束加工、大型强子对撞机。写这类机器的计算器前，先查看对应配方页的 `metadata` 和物品 Tooltip，不要只凭显示名称推断规则。

## 查询模块

适用：维护者。

模板和模块按层次调用，越往上越接近页面展示：

| 层次 | 模块 | 作用 |
|---|---|---|
| 数据访问 | [模块:Database](https://gtnh.huijiwiki.com/wiki/模块:Database) | 解析版本范围，执行查询：物品、配方、材料、矿辞、任务、维度 |
| 展示接口 | [模块:DatabaseInterfaces](https://gtnh.huijiwiki.com/wiki/模块:DatabaseInterfaces) | 把原始记录整理成可显示的数据：候选物品、概率、NBT、Tooltip |
| 配方 | [模块:Recipe](https://gtnh.huijiwiki.com/wiki/模块:Recipe)、[模板:Recipe](https://gtnh.huijiwiki.com/wiki/模板:Recipe) | 按配方类型、输入、输出查询并绘制配方；配方类型的中文名在[模块:Recipe/MachineMapping](https://gtnh.huijiwiki.com/wiki/模块:Recipe/MachineMapping)中登记 |
| 物品显示 | [模块:ItemDisplay](https://gtnh.huijiwiki.com/wiki/模块:ItemDisplay)、[模板:Item](https://gtnh.huijiwiki.com/wiki/模板:Item) | 显示物品图标与名称 |
| 名称规则 | [模块:ItemAbbreviation](https://gtnh.huijiwiki.com/wiki/模块:ItemAbbreviation) | 决定物品名链接到哪个页面，例如各种矿石、粗矿石都链接到材料页 |

全部读取数据库的模板与模块列在[分类:支持数据库的模板或模块](https://gtnh.huijiwiki.com/wiki/分类:支持数据库的模板或模块)。

查配方时要按配方类型分别查询：不指定类型的查询不保证返回该物品在所有配方类型中的配方，不能据此判断“没有配方”。

## 条目模板与数据库的关联

适用：维护者需要全部掌握；编辑者至少了解“主关联、副关联、校验提示”三点。

### 条目类型

条目页统一使用 `{{条目/<类型>}}` 模板，由[模块:条目](https://gtnh.huijiwiki.com/wiki/模块:条目)驱动。通用规则与校验代码见[模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目)，各类型的参数见对应模板页：

| 模板 | 介绍对象 | 读取的数据 |
|---|---|---|
| [条目/可获得对象](https://gtnh.huijiwiki.com/wiki/模板:条目/可获得对象) | 物品或一组物品，包括单方块机器、工具等 | `Items`、`Recipes`、`Quests` |
| [条目/材料](https://gtnh.huijiwiki.com/wiki/模板:条目/材料) | GT 材料族系 | `Gtmaterial`、`Ticmaterial`、`Items`、矿脉生成配方 |
| [条目/多方块结构](https://gtnh.huijiwiki.com/wiki/模板:条目/多方块结构) | 多方块机器 | `Items`、`Recipes` |
| [条目/维度](https://gtnh.huijiwiki.com/wiki/模板:条目/维度) | 维度 | `gtnhdimension`、矿脉生成配方 |
| [条目/生物](https://gtnh.huijiwiki.com/wiki/模板:条目/生物) | 生物 | [Data:生物实体.tabx](https://gtnh.huijiwiki.com/wiki/Data:生物实体.tabx)、页面内的生物信息框，以及按实体反查的 `Quests` |
| [条目/任务章节](https://gtnh.huijiwiki.com/wiki/模板:条目/任务章节) | 任务书章节 | `QuestLines`、`Quests` |
| [条目/Infobox](https://gtnh.huijiwiki.com/wiki/模板:条目/Infobox) | 机制、综述等无关联物品的页面 | 不查询数据库 |

### 关联与版本

- **主关联、副关联**：填物品（或材料、维度）的精确中文名，重名时用 `@物品key`。副关联的每个中文名都必须有一个重定向指向本条目，否则会提示 `missing-redirect`。
- **数据版本**：`索引-数据版本` 决定查询哪个数据库，留空即使用 `default`。
- **内容版本**：`索引-内容版本` 是人工内容最后一次校对时的游戏版本，必须由编辑者确认后填写，不会自动更新。
- **合成表类型**：`控制-合成表类型` 决定“获取”章节查询哪些配方类型，填写[模块:Recipe/MachineMapping](https://gtnh.huijiwiki.com/wiki/模块:Recipe/MachineMapping)中登记的类型名。

### 自动章节

列表、获取、任务、注释、导航等章节会根据数据自动生成。人工填写某个章节会整体覆盖自动内容；只想补充时用 `章节-XX-首`、`章节-XX-尾`。注释和导航章节不要手写。

### 分类关联与导航

- `索引-分类关联`、`索引-模组关联` 为条目添加分类，并选择底部导航。
- 导航内容保存在数据表模块 `模块:Navbox/<名称>` 中，由 `{{#invoke:Navbox|module|<名称>}}` 绘制；要嵌进其他导航框时写 `{{#invoke:Navbox|module|<名称>|border=subgroup}}`。写法见 [Project:沙盒/navbox](https://gtnh.huijiwiki.com/wiki/Project:沙盒/navbox)。
- 条目会检查自己是否被所属导航收录（链接必须与页面全名完全一致），未收录时提示 `navbox-missing`。

### 校验提示

条目在页首列出校验提示，并加入[分类:条目警告](https://gtnh.huijiwiki.com/wiki/分类:条目警告)、[分类:条目错误](https://gtnh.huijiwiki.com/wiki/分类:条目错误)的子分类。每个代码的含义、触发条件和处理办法见[模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目)的“校验分类”一节。维护者可以定期检查这些分类，作为待办清单。

## 维护者检查清单

适用：维护者。

- 改模块前，先查清有哪些页面嵌入它（[特殊:链入页面](https://gtnh.huijiwiki.com/wiki/Special:WhatLinksHere)），挑几个有代表性的页面作为测试页。
- 用 `wiki.py preview` 或 Scribunto 控制台在保存前测试，保存后清除测试页缓存并核对。
- 新增或调整数据集、字段、版本别名后，同步更新 [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database)。
- 模板的用法与示例写在模板页的 `noinclude` 区域，不要只写在沙盒里。
- 新建零件默认保持禁用；用户只要求 CSS 时不要引入 JavaScript。
