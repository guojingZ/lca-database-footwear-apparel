"""中文学习内容与隔离的教学场景；所有数值仍由原核算引擎产生。"""

from copy import deepcopy
from decimal import Decimal, InvalidOperation

from carbonfact_app import __version__
from carbonfact_app.engine import calculate, compare, export_model
from carbonfact_app.templates import templates


CONCEPTS = [
    ("library", "资料库与核算工具", "CSV 保存公开结果，方法学解释结果怎样建立，工作台把这些记录用于产品模型。", "T 恤既使用染色 CSV，也回查染色方法学。", "有一份因子表，不等于已有企业实测清单。", "docs/中文入门.md"),
    ("process", "生产工序与工序模块", "工序是实际加工；工序模块把相关对象、数据、规则、边界和依据组织起来。", "棉织物活性染色需要说明设备、色深、投入与包含项。", "中文名称相似，不足以证明两条记录适用同一工艺。", "docs/processes/dyeing.md"),
    ("unit", "功能单位", "先问一条影响值对应多少、什么产出，再匹配数量。", "染色为每 kg 对应产出；鞋装配可能每双，熨烫可能每分钟。", "不能把所有记录都当作每 kg，也不能把 kg 布料误当 kg 染料。", "docs/字段字典.md"),
    ("activity", "活动量", "活动量是你的任务实际发生的加工量、材料量或服务量。", "140 g 成衣在当前模板中需要约 160.916 g 染色产出。", "有损耗时，每道工序的数量不都等于成衣净质量。", "docs/核算规则.md"),
    ("factor", "GHG 影响因子", "GHG 表示每功能单位已计算出的气候影响，通常以 kg CO₂e 表示分子。", "活性柔流喷射代表记录约为 4.001597 kg CO₂e/kg 染色产出。", "这不是每 kg 染料的排放，也不是整件衣服的结果。", "docs/中文入门.md"),
    ("boundary", "系统边界", "明确从哪里开始、到哪里结束，以及每条因子已经包括和排除什么。", "T 恤模板声明原料至成衣出厂；使用阶段不在当前链内。", "增加工序越多不一定越完整，包含项重叠会重复计算。", "docs/processes/textile-assembly.md"),
    ("loss", "投入产出比与损耗", "投入比等于投入质量除以产出质量；损耗率必须明确分母。", "装配投入比 1.1494：0.14 kg 成衣需要 0.160916 kg 面料。", "按投入损耗 20% 对应投入比 1.25，不是 1.20。", "docs/核算规则.md"),
    ("inventory", "投入清单与整项因子", "可以用整项工序结果，也可以用各项耗用与因子建立企业清单。", "染色选整项 GHG，或填每 kg 产出的电、热、水、助剂等。", "同一范围两种路径不能叠加；清单数量也不能把整批当每 kg。", "docs/processes/dyeing.md"),
    ("missing", "未知、零与明确排除", "不知道的量或因子保持缺失；零和排除都需要真实依据。", "T 恤原料因子待补，所以只能报告已覆盖小计。", "缺失不是零；删掉一行也不能自动使必需范围消失。", "docs/核算规则.md"),
    ("evidence", "来源与版本", "保存记录标识、单位、原文位置、方法学和数据版本，别人才能复算。", "导出 T 恤模型同时保留所选公开记录及来源路径。", "只保存一个中文名和碳值，会丢失适用条件与追溯依据。", "docs/字段字典.md"),
    ("quality", "DQR 与不确定性", "DQR 描述时间、地域、技术等数据质量维度，不直接给数值误差条。", "详情保留评分；数据年份未知就显示未知。", "不能把 DQR 换成 ± 百分比，也不能用发布年代替数据年。", "docs/字段字典.md"),
    ("comparison", "情景比较", "比较时保持边界、每件/批次口径和缺项范围一致，并解释变化变量。", "将同一模板从 140 g 改为 280 g，观察已覆盖部分翻倍。", "小计差值不能自动解释为完整产品减排，工艺适用性仍需审阅。", "docs/核算规则.md"),
]

LESSONS = [
    {"title": "认识这件 T 恤", "body": "140 g、60% 有机棉与 40% 再生棉，都是结构教学设定。先明确每件结果和原料至出厂边界。", "action": "查看模型中的重量、配比和六个工序。", "document": "docs/中文入门.md"},
    {"title": "读懂一条染色因子", "body": "核对纤维素织物、活性染料、柔流喷射和中等色深，再看 kg 产出分母、GHG、投入比与来源。", "action": "打开染色记录；从中文工序卡回到 CSV 和方法学。", "document": "docs/processes/dyeing.md"},
    {"title": "从成衣反推数量", "body": "生产顺序从上游到下游，计算从成衣向前反推。每环节以自己的产出量乘加工因子。", "action": "在数量表找到装配投入与染色产出，并解释为何不是每项都乘 0.14。", "document": "docs/核算规则.md"},
    {"title": "解释小计与缺项", "body": "默认有可计算贡献，也有原料、前处理等缺项。装配内含缝线/包装等，外加项须复核。", "action": "把缺项变成下一轮采数问题，未知先不填零。", "document": "docs/processes/textile-assembly.md"},
    {"title": "做单变量练习", "body": "重量翻倍、配比 80/20、装配按投入损耗 20%。先预测再计算；练习不代表实际企业条件。", "action": "切换下方情景，比较同口径的已覆盖小计。", "document": "docs/核算规则.md"},
    {"title": "保存与接续开发", "body": "导出模型、结果与所选公开记录；加载后由同一 Python 引擎重算。再整理你自己的标准工序映射。", "action": "在独立演示完成全流程，或把当前案例载入产品工作台。", "document": "docs/开发接续.md"},
]

DEMO_STEPS = ["想法与任务", "整理产品事实", "组合工序与选因子", "运行与解释计算", "缺项与资料需求", "复核与反馈", "导出与接续"]
SCENARIOS = {
    "baseline": "当前输入基线",
    "weight_double": "重量翻倍",
    "shares_80_20": "配比改为 80 / 20",
    "loss_20": "装配损耗 20%（教学假设）",
}


def learning_content(catalog):
    model = templates(catalog)["tshirt"]
    return {"version": __version__, "catalog_digest": catalog["catalog_digest"],
            "concepts": [{"id": item[0], "title": item[1], "summary": item[2], "example": item[3],
                          "misconception": item[4], "document": item[5], "group": "先懂这些" if i < 6 else "继续理解"}
                         for i, item in enumerate(CONCEPTS)],
            "lessons": LESSONS, "demo_steps": DEMO_STEPS, "scenarios": SCENARIOS,
            "case": export_model(model, catalog)}


def normalise_state(raw, catalog):
    if not isinstance(raw, dict):
        raise ValueError("演示参数必须是对象")
    if raw.get("catalog_digest", catalog["catalog_digest"]) != catalog["catalog_digest"]:
        raise ValueError("演示目录版本不同，请保留旧导出并重新核对")
    defaults = {"task": "学习一件 140 g 棉 T 恤怎样核算", "weight_g": "140", "organic_share": "60",
                "recycled_share": "40", "scenario": "baseline", "review_note": "", "review_status": "pending"}
    state = {}
    for key, default in defaults.items():
        value = raw.get(key, default)
        if isinstance(value, (dict, list, bool)) or value is None:
            raise ValueError(key + " 必须是文字或数值")
        state[key] = str(value).strip()
        if len(state[key]) > (3000 if key == "review_note" else 300 if key == "task" else 64):
            raise ValueError(key + " 内容过长")
    if state["scenario"] not in SCENARIOS:
        raise ValueError("不支持的教学情景")
    if state["review_status"] not in {"pending", "accepted", "rejected"}:
        raise ValueError("复核状态不受支持")
    if not isinstance(raw.get("dyeing_selected", True), bool):
        raise ValueError("因子选择状态必须是布尔值")
    state["dyeing_selected"] = raw.get("dyeing_selected", True)
    state["catalog_digest"] = catalog["catalog_digest"]
    return state


def demo_model(state, catalog):
    model = deepcopy(templates(catalog)["tshirt"])
    model["weight_g"] = state["weight_g"]
    model["materials"][0]["share_percent"] = state["organic_share"]
    model["materials"][1]["share_percent"] = state["recycled_share"]
    if not state["dyeing_selected"]:
        model["chain"][3]["factor_id"] = None
    if state["scenario"] == "weight_double":
        try:
            weight = Decimal(state["weight_g"])
            if not weight.is_finite():
                raise ValueError("重量必须是有限数值")
            model["weight_g"] = str(weight * 2)
        except InvalidOperation:
            raise ValueError("重量必须是数值") from None
    elif state["scenario"] == "shares_80_20":
        model["materials"][0]["share_percent"] = "80"
        model["materials"][1]["share_percent"] = "20"
    elif state["scenario"] == "loss_20":
        model["chain"][-1].update({"ratio_mode": "loss", "loss_percent": "20",
                                   "ratio_note": "纯教学假设：按投入质量定义损耗20%；沿用公开加工因子，未重新建模工艺"})
    return model


def gap_actions(result):
    actions = []
    for gap in result["missing"]:
        key = gap["id"]
        if "原料" in key:
            question = "取得该材料生产因子的来源、单位、适用条件与分配依据；不能用纺纱加工冒充原料生产。"
        elif "quantity" in key:
            question = "取得每件（或本批次）的实际活动量；未知保持空缺，不填假零。"
        elif "overlap" in key or key == "boundary":
            question = "核对必需范围、内含包装/缝线/损失和其他项目的边界；记录不重复的依据。"
        elif "损失" in key:
            question = "核查实际废料去向、处理因子及是否已内含；分环节处置需明确范围。"
        else:
            question = "核对本项真实活动、功能单位与范围，补充匹配的因子或清单；保留来源和审阅状态。"
        actions.append({"id": key, "issue": gap["message"], "next_action": question})
    return actions


def demo_snapshot(raw, catalog):
    state = normalise_state(raw, catalog)
    model = demo_model(state, catalog)
    result = calculate(model, catalog)
    base_state = dict(state, scenario="baseline")
    comparison = compare(model, demo_model(base_state, catalog), catalog)
    source_model = templates(catalog)["tshirt"]
    dyeing_id = source_model["chain"][3]["factor_id"]
    candidate = next(f for f in catalog["factors"] if f["id"] == dyeing_id)
    unsuitable = next(f for f in catalog["factors"] if f["category"] == "dyeing" and "DISPERSE/BATCH/CONVENTIONAL_JET#SYNTHETIC_FIBERS" in f["descriptor"])
    return {"state": state, "model": model, "result": result, "comparison": comparison,
            "gap_actions": gap_actions(result), "candidate": candidate,
            "excluded_candidate": {"name": unsuitable["activity_zh"], "id": unsuitable["id"],
                                   "reason": "当前案例是棉/纤维素织物，这条分散染代表记录面向合成纤维；不因 GHG 高低替代。"},
            "scenario_label": SCENARIOS[state["scenario"]],
            "teaching_notice": "模板与参数仅用于教学；当前有缺项，不代表实际工厂、完整产品足迹或认证。"}


def demo_export(raw, catalog):
    snapshot = demo_snapshot(raw, catalog)
    if not snapshot["result"]["valid"]:
        raise ValueError("输入需要修正后才能导出：" + "；".join(snapshot["result"]["errors"]))
    packet = export_model(snapshot["model"], catalog)
    packet.update({"app_version": __version__, "demo_state": snapshot["state"],
                   "teaching_notice": snapshot["teaching_notice"], "gap_actions": snapshot["gap_actions"],
                   "demo_steps": [{"step": i + 1, "name": name} for i, name in enumerate(DEMO_STEPS)]})
    lines = ["# T 恤教学演示报告", "", snapshot["teaching_notice"], "",
             "任务：" + snapshot["state"]["task"].replace("\n", " "),
             "情景：" + snapshot["scenario_label"], "边界：" + packet["result"]["boundary"],
             "采用重量（g）：" + str(packet["model"]["weight_g"]),
             "状态：" + packet["result"]["label"],
             "已覆盖小计：" + str(packet["result"]["subtotal_ghg"]) + " " + packet["result"]["unit"],
             "目录版本：" + catalog["catalog_digest"], "", "## 已计算贡献", ""]
    for item in packet["result"]["contributions"]:
        lines.append("- " + item["name"] + "：" + item["quantity"] + " " + item["unit"] + " × " + item["factor_ghg"] + " = " + item["ghg"] + " kg CO₂e")
    lines.extend(["", "## 尚未覆盖与下一步", ""])
    for item in snapshot["gap_actions"]:
        lines.append("- " + item["issue"] + "；" + item["next_action"])
    lines.extend(["", "## 复核意见（仅本演示，不改公共资料）", "",
                  "状态：" + {"pending": "待核对", "accepted": "演示采纳：列入下一轮", "rejected": "演示退回：依据不足"}[snapshot["state"]["review_status"]], snapshot["state"]["review_note"] or "尚未填写", "",
                  "## 公开来源", ""])
    for factor in packet["selected_source_records"]:
        lines.append("- " + factor["activity_zh"] + "；" + factor["id"] + "；" + factor["source"]["csv"] + "；逻辑记录 " + str(factor["source"]["csv_record"]))
    lines.extend(["", "数据：Carbonfact；CC BY-SA 4.0。模型与确定性计算：本中文应用。", "JSON 包中的 model 可在产品工作台加载并重算。"])
    return {"packet": packet, "markdown": "\n".join(lines) + "\n"}
