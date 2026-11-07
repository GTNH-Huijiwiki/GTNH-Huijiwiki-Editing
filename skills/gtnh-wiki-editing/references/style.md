# 推荐编辑规范

返回[技能首页](../SKILL.md)。本页讲两件最要紧的事：**怎样核查事实**，以及**维基上最重要的数据库联动模板**。条目的具体写法以条目模板的文档为准，这里只列要点。

## 事实核查

适用：所有编辑者。

写进页面的每个数字、配方和机制，都要能指出它来自哪份数据或哪段源码。不知道就去查；查不到依据就不写，并说清楚缺什么证据。AI 代理不得凭记忆或推测补全事实。

### 第一步：查线上数据库

物品、配方、矿辞、材料、任务、维度等导出数据都在线上数据库里，先用简单的查询核对。最省事的办法是用 [scripts/wiki.py](../scripts/wiki.py) 的 `lua` 命令，在 Scribunto 控制台里调用现成模块。它不需要登录，也不会保存任何页面：

```bash
# 按精确中文名找物品，确认 key 和所属模组
python wiki.py lua "local D=require('Module:Database'); for key,item in pairs(D.queryIngredients{translatedNames={'粗氮冰'}}) do if key==item.key then mw.log(key,item.translatedName,item.mod) end end"

# 名称记不准时模糊搜索
python wiki.py lua "local found=require('Module:Database').queryIngredientsAdvanced{translatedNames={'氧气罐'},nameFuzzy=true,limit=20}; for key,item in pairs(found) do if key==item.key then mw.log(key,item.translatedName) end end"

# 按配方类型查某个物品的配方数量
python wiki.py lua "mw.log(#require('Module:Recipe').query{output='@GalacticraftCore:tile.oxygenPipe',type='压模机'})"

# 查 GT 材料的各形态
python wiki.py lua "mw.logObject(require('Module:Database').queryMaterial('氮').OrePrefixes)"
```

也可以把一段模板调用写进文件，用 `python wiki.py preview -f 文件` 看渲染结果，例如 `{{Recipe|output=氧气管道|type=压模机}}`；或者直接写到[自己的沙盒](#在沙盒里测试)里保存后查看。

查询时注意：

- **配方要按类型查**：不指定类型的查询不保证返回所有类型的配方，不能据此断定「没有配方」。配方类型名见[模块:Recipe/MachineMapping](https://gtnh.huijiwiki.com/wiki/模块:Recipe/MachineMapping)。
- **同名物品**：同一个中文名可能对应多个物品，例如不同储量的氧气罐、任务占位物品，要用 `@物品key` 精确指定。
- **数据版本**：查询默认使用 `default` 数据库，核对其他版本时要显式指定版本，见[维基技术现状](wiki-tech.md#数据库版本)。

### 第二步：拿不准就看源码

数据库里只有导出的结果。机制、公式、数值规则、触发条件，都要看源码才能确定。

- 遇到数据库回答不了的问题时，**必须请用户把相关仓库克隆到本地**再查，例如 GTNewHorizons 组织下的 [GT5-Unofficial](https://github.com/GTNewHorizons/GT5-Unofficial)、[Galacticraft](https://github.com/GTNewHorizons/Galacticraft)、[NewHorizonsCoreMod](https://github.com/GTNewHorizons/NewHorizonsCoreMod)，以及对应的附属模组仓库。AI 代理要明确告诉用户需要哪个仓库、为什么需要；在拿到源码之前，不给出结论。
- 以与当前整合包版本对应的源码为准，注意区分开发分支和已发布版本。
- 引用源码时，在页面中用 `<ref>` 注明文件和方法。

### 大规模核对：用本地导出

需要核对成百上千条物品或配方时（例如检查一整类条目、生成统计表），**必须请用户先用 [GTNH-Dumper](https://github.com/GTNH-Huijiwiki/GTNH-Dumper) 在游戏内导出一份数据到本地**，再用脚本批量查询本地导出文件。不要对线上数据库发起大量查询：每页的 Lua 执行时间有上限，大量请求既慢又容易超时。导出方法和目录约定见[工具链的说明](https://github.com/GTNH-Huijiwiki/GTNH-Huijiwiki-Toolchain)。

### 写进页面之前

- 从旧版本页面、社区讨论、英文维基搬来的内容，要先按上面的方法核对，并注明来源和时效（英文维基的写法见[参考英文维基](#参考英文维基)）。
- 只在某个版本成立的内容（引入、移除、改动、旧版限制），写进[历史章节](#历史章节)，正文只写当前版本的事实。

## 在沙盒里测试

适用：所有编辑者。

`Project:沙盒/<你的用户名>/` 下的页面可以**自由创建、修改和删除**，用来试写条目、试用模板、测试脚本的保存流程，不需要事先征求同意，也不会影响正式条目。例如 `Project:沙盒/张三/火箭草稿`。拿不准写法时，先在沙盒里写好、看过渲染结果，再搬到正式页面。

## 数据库联动模板

适用：所有编辑者。下面这几个模板直接读取线上数据库，是写条目时最常用的工具，使用前先读一遍各自的模板文档：

| 模板 | 用途 |
|---|---|
| [模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目) | 条目页的统一框架，汇总各条目类型、通用规则和校验提示，见下文[条目要点](#条目要点) |
| [模板:Item](https://gtnh.huijiwiki.com/wiki/模板:Item) | 在正文中显示物品、方块、维度的图标、名称和链接；重名时用 `@物品key` |
| [模板:Recipe](https://gtnh.huijiwiki.com/wiki/模板:Recipe) | 按配方类型、输入或输出查询并绘制配方 |
| [模板:IconList](https://gtnh.huijiwiki.com/wiki/模板:IconList) | 以配方槽位的样式列出一组物品 |

所有与数据库联动的模板和模块都在[分类:支持数据库的模板或模块](https://gtnh.huijiwiki.com/wiki/分类:支持数据库的模板或模块)中，需要其他功能时先到这里找。

## 条目要点

适用：所有编辑者。完整规范以[模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目)及各类型模板（如[条目/可获得对象](https://gtnh.huijiwiki.com/wiki/模板:条目/可获得对象)）的文档为准，这里只列最常出错的几点：

- 页面名就是对象的精确中文名，需要消歧义时加全角括号后缀，例如「锻造锤（机器）」。
- 副关联的每个中文名都要建立重定向指向本条目。
- 注释、导航等通用章节自动生成，不要手写。
- 页首的校验提示要逐条处理，代码含义见模板文档的「校验分类」。
- `索引-内容版本` 填你实际核对过的游戏版本。
- 版本变动一律写在 `章节-历史`，写法见[历史章节](#历史章节)。

## 写作风格

适用：所有编辑者。

- 物品、方块、维度一律用 `{{Item}}`，不要只写纯文字名称。
- 否定说法统一为「**主语**不会……」「**主语**无法……」，主语加粗。
- 链接写到页面的实际标题，不要链到重定向；新条目要加进所属导航，做法见[维基技术现状](wiki-tech.md#分类关联与导航)。

### 历史章节

正文描述当前版本的事实，版本变动只写在历史章节（条目页为 `章节-历史`）。

- **版本标记**：用 [模板:VersionLabel](https://gtnh.huijiwiki.com/wiki/模板:VersionLabel)，标签内只写版本号，例如 `{{VersionLabel|2.9.0}}`；「及以后」「以前」等说明写在模板外。
- **正文不出现版本号标记**：`{{VersionLabel}}`、`{{Label|2.9.0}}` 之类的标签只能出现在历史章节。条目模块会把在历史章节以外使用版本标签的页面归入[分类:在历史章节外使用版本标签的页面](https://gtnh.huijiwiki.com/wiki/分类:在历史章节外使用版本标签的页面)。数据查询的 `version` 参数、文件名、旧版页面链接不算版本标记。
- **正文不写变动**：「改为」「已经变动」「新版本已经……」「旧版本曾经……」这类夹杂在正文里的新旧对比都不规范。正文直接写现在是什么；以前是什么、何时变的，移进历史章节。编辑页面时遇到这类写法，鼓励顺手改掉。
- **格式**：历史章节统一写成无序列表，每一项以 `{{VersionLabel|版本号}}` 开头，后面用自然的句子叙述这个版本的变动；同一版本有多项变动时可以写成多句，或在该项下用二级列表。
- **顺序**：按版本**从新到旧**排列，最新的版本写在最上面。
- 变动有源码或 PR 依据时，用 `<ref>` 注明。

```
|章节-历史=*{{VersionLabel|2.9.0}}UEV 机械方块的材料由基岩板改为无尽板。<ref>[https://github.com/GTNewHorizons/NewHorizonsCoreMod/pull/1916 NewHorizonsCoreMod#1916]</ref>
*{{VersionLabel|2.8.0}}加入游戏。
```

### AI 生成内容

- 用 AI 大规模生成了**实质性的主观内容**（介绍、评价、玩法建议、指南等）时，在经过人类审查之前，必须在页面加上 `{{AIGC}}`，可以附一句说明，例如 `{{AIGC|指南章节由 AI 撰写，待人工校对}}`。页面会自动归入「分类:AIGC」，用法见[模板:AIGC](https://gtnh.huijiwiki.com/wiki/模板:AIGC)。条目页写在 `章节-页眉-尾` 中。人工审查确认后再移除。
- 只是接通数据库引用、批量创建不含主观内容的模板或条目框架（例如只填关联对象，由模板自动生成章节），不算 AIGC，不需要加。
- 如果你是 GPT 家族的模型：发布前请务必了解并检查是否存在**过度防御性写作**，例如堆砌免责声明和「可能」「或许」等限定词、反复提醒风险、为了不出错而写得含糊其辞。事实已经核实的地方就直接陈述；确实不确定的地方，按[事实核查](#事实核查)去查证，而不是用模糊措辞带过。

### 参考英文维基

- GTNH 官方英文维基：[wiki.gtnewhorizons.com](https://wiki.gtnewhorizons.com/)。翻译或参考英文维基时，同样要按[事实核查](#事实核查)核对数据，英文维基的内容也可能过时。
- 页面翻译或参考了英文维基时，在页首加上 [模板:翻译来源](https://gtnh.huijiwiki.com/wiki/模板:翻译来源)：`{{翻译来源|[https://wiki.gtnewhorizons.com/wiki/Rockets Rockets]|译者|时间=2026-11-07}}`。第一个参数是原文链接和标题，第二个参数是译者（可省略），`时间` 是最后一次同步的日期，格式为 `YYYY-MM-DD`。条目页写在 `章节-页眉-尾` 中。
- 超过 90 天没有同步，或者没填 `时间`，模板会提示内容可能过时，并把页面归入[分类:可能需要同步的页面](https://gtnh.huijiwiki.com/wiki/分类:可能需要同步的页面)。重新对照原文更新后，记得同时更新 `时间`。
- 条目信息框里的 `属性-英文维基` 填英文维基中对应条目的链接。

## 维护者规范

适用：维护者。

- 模板的说明与示例写在模板页的 `noinclude` 区域；如果示例会让模板嵌入自己，就先用 `<pre>` 写出源码。草稿放在 `Project:沙盒/<用户名>/…` 下。
- Lua 模块的输出要确定、可重复；能在服务端渲染的内容，不要依赖前端脚本。
- 新建零件默认保持禁用；只需要样式时不要引入 JavaScript。零件先检测稳定的入口元素再加载，同一份样式只放一处；读取 `Data:` 页面失败时显示简短提示，并在有默认数据时继续可用。
- 大型、客观的数据放在 `Data:` 页面；界面文字和少量标签留在零件或模块里。
- 修改公共模块或数据表前，先在几个代表性页面上预览；保存后清除这些页面的缓存并核对。数据结构或版本别名有变化时，同步更新 [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database)。
