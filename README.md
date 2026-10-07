# Carbonfact 中文工序工作台

**中文应用 v0.1.0｜本地运行｜Python 3.10+｜无第三方运行依赖**

这个项目帮助你读懂鞋服工序数据，把因子组合成有边界、有缺项、有来源的产品估算。完整上游快照位于 [upstream/carbonfact](upstream/carbonfact/README.md)；新增中文解释、数据工具和核算页面与它分别维护。

## 先运行

在项目根目录打开终端：

```powershell
python app.py
```

Windows 若 `python` 不可用，可用 `py -3 app.py`。浏览器地址为 `http://127.0.0.1:8768`，终端按 Ctrl+C 停止。端口占用时运行 `python app.py --port 8769`。无需 pip 安装，无需数据库服务器。

已有旧版 Git 项目，请**先读 [覆盖升级指南](docs/覆盖升级指南.md)**。单纯复制新版文件不会清理旧位置；不要删除整个项目。

## 按什么顺序理解

1. [PROJECT.md](PROJECT.md)：项目是什么、对你的业务有什么用。
2. [中文入门](docs/中文入门.md)：结果因子、活动量、工序边界和模型公开程度。
3. [12 类工序卡](docs/processes/README.md)：按业务工序找资料，染色/整理/装配有深入解读。
4. [字段字典](docs/字段字典.md)及[核算规则](docs/核算规则.md)：知道一条记录怎么用。
5. [开发接续](docs/开发接续.md)：把数据和核算模块接到自己的项目。

## 页面能做什么

- 浏览 304 条有效记录，按中文、英文、原始标识、类别、单位检索；查看 16 项原始影响值和证据。
- 载入 T 恤、涤纶染整或企业投入清单结构；调整质量、材料比例、工序顺序与投入产出依据。
- 从成品质量向上游反推活动量；显示阶段贡献、缺项、可能重叠及单位错误。
- 手工补入有来源的外部因子；保存模型、结果与所选来源记录为 JSON；加载后重算。
- 保存一个比较基线。边界或缺项不同会限制比较结论。

默认 T 恤模板缺原料、棉前处理、配件/包装/运输和损失材料处理数据；染整模板也缺损失材料处理因子。默认显示的是**已覆盖部分排放**。企业投入模板不填虚构的用电、用热或化学品数据。

## 命令行入口

```powershell
python tools/data_workbench.py audit
python tools/data_workbench.py validate
python tools/calculate.py examples/tshirt.json --output local-data/tshirt-result.json
python -m unittest discover -s tests -v
```

修改中文映射或类别元数据后运行 `python tools/data_workbench.py build`，然后重新匹配模型。目录版本变化会被旧模型检测出来。[验证报告](docs/验收报告.md)区分已验证行为和待完成的本机检查。

## 目录职责

| 路径 | 职责 |
|---|---|
| `upstream/carbonfact/` | 上传来源的 116 个文件，保留原始字节与内部路径 |
| `data/` | 来源哈希、中文映射、类别元数据、整理后的 CSV/JSON |
| `carbonfact_app/` | 数据目录、确定性核算、结构模板 |
| `web/`、`app.py` | 中文本地页面与 HTTP 接口 |
| `tools/`、`tests/` | 盘点、构建、校验、核算、升级工具与规则验证 |
| `docs/` | 中文业务、操作和开发资料 |
| `PROJECT.md`、`WORKLOG.md`、`MEMORY.md` | 项目入口、当前状态和稳定规则 |
| `topics/`、`docs/adr/` | 独立议题及已采纳的长期决策 |
| `examples/` | 三个空缺明确的结构模型 |
| `local-data/` | 建议存个人模型/结果的位置；不随项目包提供 |

## 来源、许可和修改说明

数据来自 [Carbonfact 上游仓库](https://github.com/carbonfact/lca-database-footwear-apparel)及[官方数据库说明](https://www.carbonfact.com/database)，许可为 **CC BY-SA 4.0**，保留根 [LICENSE](LICENSE)。作者和 DOI 原样保留在 [CITATION.cff](upstream/carbonfact/CITATION.cff)：Vincent Carrières、Gustavo Vieira、Laurent Vandepaer；`10.5281/zenodo.21102755`。

本应用新增中文展示、字段归一、质量链及投入清单核算，没有修改上游影响值。引用文件标注上游 1.1.0，快照含 Unreleased，提交号未知；它与中文应用版本不同。[许可与来源](docs/许可与来源.md)给出对外使用的署名入口。
