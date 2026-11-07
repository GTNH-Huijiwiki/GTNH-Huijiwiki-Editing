"""工作区入口：转发到 skills/gtnh-wiki-editing/scripts/wiki.py。

在仓库根目录直接使用，命令行和库用法都与技能中的 wiki.py 完全相同：
    python wiki.py whoami
    python wiki.py pull 火箭
    import wiki; wiki.login()

源码只有技能中的那一份，修改请改 skills/gtnh-wiki-editing/scripts/wiki.py。
这里没有使用符号链接：Windows 默认不允许普通用户创建符号链接，
git 在这类环境中会把链接检出成一行路径文本，导致无法运行。
"""

import importlib.util
import os
import sys

_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "skills", "gtnh-wiki-editing", "scripts", "wiki.py")
_spec = importlib.util.spec_from_file_location("gtnh_wiki_editing_wiki", _TARGET)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

if __name__ == "__main__":
    _module.main()
else:
    sys.modules[__name__] = _module
