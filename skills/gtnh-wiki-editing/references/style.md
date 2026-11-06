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

也可以把一段模板调用写进文件，用 `python wiki.py preview -f 文件` 看渲染结果，例如 `{{Recipe|output=氧气管道|type=压模机}}`、`{{Tooltip|氧气压缩机}}`。

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

- 从旧版本页面、社区讨论、英文维基搬来的内容，要先按上面的方法核对，并注明来源和时效。
- 只在某个版本成立的内容，写明版本。

## 数据库联动模板

适用：所有编辑者。下面这些模板直接读取线上数据库，是写条目时最常用的工具。使用前先读一遍各自的模板文档：

| 模板 | 用途 |
|---|---|
| [模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目) | 条目页的统一框架，汇总各条目类型、通用规则和校验提示，见下文[条目要点](#条目要点) |
| [模板:Item](https://gtnh.huijiwiki.com/wiki/模板:Item) | 在正文中显示物品、方块、维度的图标、名称和链接；重名时用 `@物品key` |
| [模板:Recipe](https://gtnh.huijiwiki.com/wiki/模板:Recipe) | 按配方类型、输入或输出查询并绘制配方 |
| [模板:Icon](https://gtnh.huijiwiki.com/wiki/模板:Icon) | 表格、流程图中的物品图标 |
| [模板:IconList](https://gtnh.huijiwiki.com/wiki/模板:IconList) | 以配方槽位的样式列出一组物品 |
| [模板:IconTabber](https://gtnh.huijiwiki.com/wiki/模板:IconTabber) | 按名称自动匹配图片的页签组 |
| [模板:Tooltip](https://gtnh.huijiwiki.com/wiki/模板:Tooltip) | 显示物品或机器的游戏内 Tooltip |
| [物品查询](https://gtnh.huijiwiki.com/wiki/ItemSearch) | 按名称、模组、Tooltip 搜索物品，适合查 key 和同名物品 |

全部读取数据库的模板与模块列在[分类:支持数据库的模板或模块](https://gtnh.huijiwiki.com/wiki/分类:支持数据库的模板或模块)。

## 条目要点

适用：所有编辑者。完整规范以[模板:条目](https://gtnh.huijiwiki.com/wiki/模板:条目)及各类型模板（如[条目/可获得对象](https://gtnh.huijiwiki.com/wiki/模板:条目/可获得对象)）的文档为准，这里只列最常出错的几点：

- 页面名就是对象的精确中文名，需要消歧义时加全角括号后缀，例如「锻造锤（机器）」。
- 副关联的每个中文名都要建立重定向指向本条目。
- 注释、导航等通用章节自动生成，不要手写。
- 页首的校验提示要逐条处理，代码含义见模板文档的「校验分类」。
- `索引-内容版本` 填你实际核对过的游戏版本。

## 写作与链接

适用：所有编辑者。

- 物品、方块、维度一律用 `{{Item}}`，不要只写纯文字名称。
- 否定说法统一为「**主语**不会……」「**主语**无法……」，主语加粗。
- 链接写到页面的实际标题，不要链到重定向；新条目要加进所属导航，做法见[维基技术现状](wiki-tech.md#分类关联与导航)。

## 维护者规范

适用：维护者。

- 模板的说明与示例写在模板页的 `noinclude` 区域；如果示例会让模板嵌入自己，就先用 `<pre>` 写出源码。草稿放在 `Project:沙盒/<用户名>/…` 下。
- Lua 模块的输出要确定、可重复；能在服务端渲染的内容，不要依赖前端脚本。
- 新建零件默认保持禁用；只需要样式时不要引入 JavaScript。零件先检测稳定的入口元素再加载，同一份样式只放一处；读取 `Data:` 页面失败时显示简短提示，并在有默认数据时继续可用。
- 大型、客观的数据放在 `Data:` 页面；界面文字和少量标签留在零件或模块里。
- 修改公共模块或数据表前，先在几个代表性页面上预览；保存后清除这些页面的缓存并核对。数据结构或版本别名有变化时，同步更新 [Project:Database](https://gtnh.huijiwiki.com/wiki/Project:Database)。
