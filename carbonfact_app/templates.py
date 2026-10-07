"""结构模板；缺项保持空值，不使用虚构默认因子。"""

import copy


def templates(catalog):
    def find(fragment, extra=""):
        return next(f["id"] for f in catalog["factors"] if fragment in f["descriptor"] and extra in f["descriptor"])

    def stage(sid, name, factor_id=None, ratio_note=None):
        value = {"id": sid, "name": name, "mode": "factor", "factor_id": factor_id,
                 "ratio_mode": "factor"}
        if ratio_note:
            value.update(ratio_mode="ratio", input_ratio="1", ratio_note=ratio_note)
        return value

    base = {"schema_version": 1, "catalog_digest": catalog["catalog_digest"],
            "boundary_reviewed": False, "external_factors": [], "waste_factor_id": None,
            "additional_items": [], "materials": []}
    tshirt = {**copy.deepcopy(base), "name": "140 g 棉 T 恤结构模板", "weight_g": "140", "result_basis": "item",
              "boundary": "原料至成衣出厂；单一主布链，配件/包装/运输另列", "include_materials": True,
              "materials": [{"name": "有机棉（因子待补）", "share_percent": "60", "factor_id": None},
                            {"name": "再生棉（因子待补）", "share_percent": "40", "factor_id": None}],
              "chain": [stage("spinning", "纺纱", find("SPINNING/FOR_KNIT/RING#PLANT_FIBERS/COTTON?DTEX=200")),
                        stage("knitting", "圆机针织", find("KNITTING/CIRCULAR#ANY?DTEX=200")),
                        stage("preparation", "棉前处理/漂白（因子待补）", None, "结构演示暂按不损失质量；需以真实数据替换"),
                        stage("dyeing", "活性染色", find("DYEING/FABRIC/REACTIVE/BATCH/SOFTFLOW_JET")),
                        stage("finishing", "柔软整理", find("FINISHING/SOFTENING/PAD_DRY")),
                        stage("assembly", "T 恤装配", find("ASSEMBLY/GENERIC#TSHIRT"))],
              "additional_items": [{"id": "trims", "name": "其他配件/辅料（核对内含缝线）", "quantity": None, "unit": "kg", "factor_id": None},
                                   {"id": "packaging", "name": "补充包装（仅内含范围外）", "quantity": None, "unit": "kg", "factor_id": None},
                                   {"id": "transport", "name": "边界内运输", "quantity": None, "unit": "tkm", "factor_id": None}]}
    factory = {**copy.deepcopy(base), "name": "100 kg 涤纶染整结构模板", "weight_g": "100000", "result_basis": "batch",
               "boundary": "坯布进入至染整成品出厂；不含来料布生产，包含损失材料处理", "include_materials": False,
               "chain": [stage("desizing", "聚酯连续退浆", find("PREPARATION/DESIZING")),
                         stage("dyeing", "常规喷射分散染色", find("DYEING/FABRIC/DISPERSE/BATCH/CONVENTIONAL_JET")),
                         stage("heatsetting", "聚酯 190°C 热定型", find("FINISHING/HEAT_SETTING"))]}
    inventory = {**copy.deepcopy(base), "name": "企业染色投入清单空白示例", "weight_g": "100000", "result_basis": "batch",
                 "boundary": "染色投入清单；电/热/水/染料/助剂/废水；来料布生产另属上游", "include_materials": False,
                 "chain": [{"id": "dyeing", "name": "企业染色清单", "mode": "inventory", "factor_id": None,
                            "ratio_mode": "ratio", "input_ratio": "1", "ratio_note": "空白结构暂设 1；需实测投入产出",
                            "inventory_complete": False,
                            "inventory": [{"name": n, "quantity": None, "unit": u, "factor_id": None}
                                          for n, u in [("电力", "kWh"), ("热", "MJ"), ("工艺水", "L"),
                                                       ("染料", "kg"), ("助剂", "kg"), ("废水处理", "m3")]]}]}
    for model in (tshirt, factory, inventory):
        model["required_stages"] = [{"id": s["id"], "name": s["name"]} for s in model["chain"]]
    return {"tshirt": tshirt, "factory": factory, "inventory": inventory}
