"use strict";

let catalog, model, presets, baseline = null, timer, requestNumber = 0;
const viewCategory = new Map();
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clone = value => JSON.parse(JSON.stringify(value));
const fmt = (value, digits=4) => value == null ? "待定" : Number(value).toLocaleString("zh-CN", {maximumFractionDigits:digits});
const option = (value, text, selected) => `<option value="${esc(value)}" ${String(value ?? "") === String(selected ?? "") ? "selected" : ""}>${esc(text)}</option>`;
const field = (title,path,value,type="text",wide=false) => `<label class="${wide?"wide":""}">${esc(title)}<input data-path="${esc(path)}" type="${type}" value="${esc(value)}" ${type==="number"?'step="any" min="0"':''}></label>`;
const check = (title,path,value) => `<label class="check"><input type="checkbox" data-path="${esc(path)}" ${value?"checked":""}><span>${esc(title)}</span></label>`;
const select = (title,path,options) => `<label>${esc(title)}<select data-path="${esc(path)}">${options}</select></label>`;
const units = (selected) => ["kg","g","m2","pair","min","kWh","MJ","m3","L","item","km","tkm"].map(u=>option(u,{m2:"m²",pair:"双",min:"分钟",item:"件"}[u]||u,selected)).join("");
const evidenceLink = (path, text) => `<a href="${path.endsWith(".md") ? "/reader?path="+encodeURIComponent(path) : "/evidence/"+encodeURI(path)}" target="_blank" rel="noopener">${esc(text||path)}</a>`;

async function api(path, data) {
  const response = await fetch(path, data ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败");
  return result;
}
function notify(message) { $("#notice").textContent = message; }
function allFactors() {
  return [...catalog.factors, ...model.external_factors.map(f=>({id:f.id,activity_zh:f.name,activity_en:f.source,
    kind:f.kind,unit:f.unit,category:"external",mass_chain_allowed:true,impacts:{GHG:f.ghg},source:{reference:f.source,scope:f.scope},status:f.status}))];
}
function factorOptions(selected, predicate=()=>true) {
  return option("", "缺因子 / 待补充", selected) + allFactors().filter(predicate).map(f=>option(f.id,`${f.activity_zh} [${f.unit}]`,selected)).join("");
}
function factorSelect(title,path,selected,predicate=()=>true) {
  return select(title,path,factorOptions(selected,predicate));
}
function refreshFactorLists() {
  document.querySelectorAll('select[data-path$="factor_id"]').forEach(element=>{
    const path=element.dataset.path,selected=getPath(path),parts=path.split(".");
    let predicate=()=>true;
    if(parts[0]==="chain" && parts.length===3){
      const stage=model.chain[Number(parts[1])];
      const category=viewCategory.get(stage.id)||allFactors().find(f=>f.id===stage.factor_id)?.category||"dyeing";
      predicate=f=>f.category===category&&f.kind==="process"&&f.unit==="kg"&&f.mass_chain_allowed;
    }else if(parts[0]==="materials")predicate=f=>f.kind==="material"&&f.unit==="kg";
    else if(path==="waste_factor_id")predicate=f=>f.category==="external"&&f.unit==="kg";
    element.innerHTML=factorOptions(selected,predicate);
  });
}
function prepareModel(candidate) {
  if(!candidate || typeof candidate!=="object" || candidate.schema_version!==1)throw new Error("模型结构不受支持。");
  if(candidate.catalog_digest!==catalog.catalog_digest)throw new Error("模型目录版本不同；旧因子不会被自动替换。请按来源重新匹配。");
  for(const key of ["chain","materials","external_factors","additional_items","required_stages"]){
    candidate[key]??=[];
    if(!Array.isArray(candidate[key])||candidate[key].some(item=>!item||typeof item!=="object"))throw new Error(key+" 应为对象数组。");
  }
  for(const stage of candidate.chain){stage.mode??="factor";stage.ratio_mode??="factor";if(stage.mode==="inventory")stage.inventory??=[];}
  return candidate;
}
function detailButton(fid) { return fid ? `<button data-action="detail" data-id="${esc(fid)}">数值与来源</button>` : ""; }
function getPath(path) { return path.split(".").reduce((obj,k)=>obj?.[k],model); }
function setPath(path, value) {
  const keys=path.split("."),last=keys.pop();
  const parent=keys.reduce((obj,k)=>obj[k],model);
  parent[last]=value;
}

function renderProduct() {
  $("#product-fields").innerHTML = `<div class="form-grid">${field("名称","name",model.name)}${field(model.result_basis==="item"?"每件成品质量（g）":"本批次成品质量（g）","weight_g",model.weight_g,"number")}
    ${select("结果口径","result_basis",option("item","每件",model.result_basis)+option("batch","本批次",model.result_basis))}
    ${field("核算边界（明确起点和终点）","boundary",model.boundary,"text",true)}</div>
    ${check("边界包含原料生产（缺因子时保留为缺项）","include_materials",model.include_materials)}
    ${check("我已核对必需环节、工艺条件和包含/排除项；这是我声明的模型范围","boundary_reviewed",model.boundary_reviewed)}
    <p class="hint">模板是组合结构。工序默认选项须按你的材料、设备与工艺条件核对；完整性只针对所声明边界。</p>`;
}
function renderChain() {
  $("#chain").innerHTML = model.chain.map((s,i)=>{
    const selectedFactor=allFactors().find(f=>f.id===s.factor_id);
    let category=viewCategory.get(s.id) || selectedFactor?.category || "dyeing";
    if(selectedFactor) category=selectedFactor.category;
    viewCategory.set(s.id,category);
    const categoryOptions=[...catalog.categories.map(c=>({id:c.id,name:c.name})),{id:"external",name:"人工补充因子"}].filter(c=>!["shoe-assembly","synthetic-pu-leather","natural-rubber","use-phase"].includes(c.id)).map(c=>option(c.id,c.name,category)).join("");
    const factorEditor=s.mode==="inventory" ? `<p class="inline-note">每项数量 = 每 1 kg 工序产出的活动量。后台乘以本环节产出质量。不要在这里填写整批数量。</p>
      ${(s.inventory||[]).map((item,j)=>`<div class="inventory-row"><input aria-label="投入名称" data-path="chain.${i}.inventory.${j}.name" value="${esc(item.name)}"><input aria-label="每 kg 产出活动量" type="number" step="any" min="0" placeholder="待补活动量" data-path="chain.${i}.inventory.${j}.quantity" value="${esc(item.quantity)}"><select aria-label="投入单位" data-path="chain.${i}.inventory.${j}.unit">${units(item.unit)}</select><select aria-label="投入因子" data-path="chain.${i}.inventory.${j}.factor_id">${factorOptions(item.factor_id)}</select><button data-action="remove-input" data-index="${i}" data-subindex="${j}">×</button></div>`).join("")}
      <button data-action="add-input" data-index="${i}" class="secondary">＋ 投入项</button>${check("我已核对该投入清单的覆盖完整性",`chain.${i}.inventory_complete`,s.inventory_complete)}` :
      `<div class="form-grid"><label>因子类别<select data-action="stage-category" data-index="${i}">${categoryOptions}</select></label>${factorSelect("选择公开或人工因子",`chain.${i}.factor_id`,s.factor_id,f=>f.category===category && f.kind==="process" && f.unit==="kg" && f.mass_chain_allowed)}</div>
       <div class="factor-value">${selectedFactor ? `${fmt(selectedFactor.impacts.GHG,6)} kg CO₂e/kg · 原始投入产出比 ${selectedFactor.input_ratio??"未知"}　${detailButton(s.factor_id)}` : "缺因子：先补数据；下游已知工序仍可给出部分结果。"}</div>`;
    const ratioExtra=s.ratio_mode==="loss" ? field("损耗率（投入质量为分母，%）",`chain.${i}.loss_percent`,s.loss_percent,"number") :
      s.ratio_mode==="ratio" ? field("投入质量 / 产出质量",`chain.${i}.input_ratio`,s.input_ratio,"number") : "";
    return `<div class="stage" data-stage-id="${esc(s.id)}"><div class="stage-head"><span class="number">${i+1}</span><input aria-label="工序名称" data-path="chain.${i}.name" value="${esc(s.name)}"><button aria-label="上移工序" data-action="up" data-index="${i}" ${i===0?"disabled":""}>↑</button><button aria-label="下移工序" data-action="down" data-index="${i}" ${i===model.chain.length-1?"disabled":""}>↓</button><button aria-label="移除工序" data-action="remove-stage" data-index="${i}">×</button></div>
      ${select("核算路径（同一范围只选一条）",`chain.${i}.mode`,option("factor","已发布整项工序因子",s.mode)+option("inventory","企业投入清单",s.mode))}${factorEditor}
      <div class="form-grid">${select("数量传递依据",`chain.${i}.ratio_mode`,option("factor","所选因子原始投入产出比",s.ratio_mode)+option("ratio","手动投入产出比",s.ratio_mode)+option("loss","按投入定义的损耗率",s.ratio_mode))}${ratioExtra}
      ${s.ratio_mode!=="factor"?field("数量依据或假设（必填）",`chain.${i}.ratio_note`,s.ratio_note,"text",true):""}</div>
      <details><summary>重复与边界复核依据</summary><div class="form-grid">${field("真实重复加工的说明",`chain.${i}.repeat_reason`,s.repeat_reason,"text",true)}${field("与其他工序不重叠的证据",`chain.${i}.overlap_review`,s.overlap_review,"text",true)}</div></details></div>`;
  }).join("");
}
function renderMaterials() {
  $("#materials").innerHTML = (model.include_materials ? `<h3>主布材料配比</h3><p class="hint">配比之和应为 100%。上游所需材料量来自主布链反推，棉纺纱因子不包含棉纤维生产。</p>${model.materials.map((m,i)=>`<div class="row-card"><div class="form-grid">${field("材料名称",`materials.${i}.name`,m.name)}${field("质量占比（%）",`materials.${i}.share_percent`,m.share_percent,"number")}${factorSelect("材料生产因子",`materials.${i}.factor_id`,m.factor_id,f=>f.kind==="material" && f.unit==="kg")}</div><div class="row-head">${detailButton(m.factor_id)}<button data-action="remove-material" data-index="${i}">移除材料</button></div></div>`).join("")}<button data-action="add-material" class="secondary">＋ 材料</button>` : `<p class="hint">当前边界不计算来料材料生产。质量链仍反推各工序加工数量。</p>`)+
    `<h3>损失材料处理</h3>${factorSelect("按 kg 损失材料的统一处理路线","waste_factor_id",model.waste_factor_id,f=>f.unit==="kg" && (f.category==="external"))}<p class="hint">模板没有现成的损失材料处理因子。有损耗且因子缺失时，结果保持为部分估算。</p>`;
  $("#extras").innerHTML = `<h3>独立定量项目</h3><p class="hint">适用于配件、运输、每双鞋、每 m² 合成革或使用阶段等。数量对应上面的每件或本批次口径；这里不自动反推质量。</p>` + model.additional_items.map((item,i)=>`<div class="row-card"><div class="row-head"><b>${esc(item.name)}</b><button data-action="remove-extra" data-index="${i}">移除项目</button></div><div class="form-grid">${field("项目名称",`additional_items.${i}.name`,item.name)}${field("明确活动量",`additional_items.${i}.quantity`,item.quantity,"number")}${select("活动量单位",`additional_items.${i}.unit`,units(item.unit))}${factorSelect("因子",`additional_items.${i}.factor_id`,item.factor_id)}${field("明确排除的理由（留空表示应纳入）",`additional_items.${i}.excluded_reason`,item.excluded_reason,"text",true)}</div>${detailButton(item.factor_id)}</div>`).join("");
}
function renderExternal() {
  $("#external-factors").innerHTML = model.external_factors.map((f,i)=>`<div class="external-card"><div class="row-head"><b>${esc(f.id)}</b><button data-action="remove-factor" data-index="${i}">移除因子</button></div><div class="form-grid">${field("名称",`external_factors.${i}.name`,f.name)}${field("GHG 值（kg CO₂e/活动量单位）",`external_factors.${i}.ghg`,f.ghg,"number")}${select("活动量单位",`external_factors.${i}.unit`,units(f.unit))}${select("使用类型",`external_factors.${i}.kind`,option("process","工序或投入",f.kind)+option("material","原料生产",f.kind))}${select("审阅状态",`external_factors.${i}.status`,option("pending","待审阅",f.status)+option("reviewed","已自行审阅",f.status)+option("hypothetical","假设演示",f.status))}${field("来源（报告、数据集、版本或网址）",`external_factors.${i}.source`,f.source,"text",true)}${field("适用范围与包含/排除项",`external_factors.${i}.scope`,f.scope,"text",true)}</div></div>`).join("") || `<p class="hint">当前没有人工补充因子。请使用有来源的数据；假设值会保留假设标记。</p>`;
}
function renderModel() {
  renderProduct();renderChain();renderMaterials();renderExternal();
  $("#model-json").value=JSON.stringify(model,null,2);
  $("#clear-baseline").hidden=!baseline;
}
function renderResult(result, comparison) {
  $("#result-status").className="badge "+result.status;
  $("#result-status").textContent=result.label;
  const total=Number(result.subtotal_ghg||0);
  const groups=result.contributions.reduce((map,c)=>{const key=c.stage||c.id;if(!map.has(key))map.set(key,{name:c.stage?model.chain.find(s=>s.id===c.stage)?.name:c.name,value:0,items:[]});const g=map.get(key);g.value+=Number(c.ghg);g.items.push(c);return map;},new Map());
  const bars=[...groups.values()].map(g=>`<div class="bar-row"><div class="bar-head"><span>${esc(g.name)}</span><strong>${fmt(g.value,5)}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${total>0?Math.min(100,100*g.value/total):0}%"></div></div>${g.items.map(c=>`<small>${fmt(c.quantity,6)} ${esc(c.unit)} × ${fmt(c.factor_ghg,6)} = ${fmt(c.ghg,6)}　${detailButton(c.factor_id)}</small>`).join("<br>")}</div>`).join("");
  const baselineHtml=comparison ? `<div class="baseline"><strong>基线比较</strong><p>${esc(comparison.note)}</p><p>基线：${fmt(comparison.baseline.subtotal_ghg,5)}；当前：${fmt(result.subtotal_ghg,5)}</p>${comparison.comparable?`<b>差值 ${Number(comparison.delta_ghg)>0?"+":""}${fmt(comparison.delta_ghg,5)} ${esc(result.unit)}</b>`:""}</div>` : "";
  $("#result").innerHTML=`<div class="result-value">${result.valid?fmt(result.subtotal_ghg,5):"—"}</div><div class="result-unit">${esc(result.unit)}${result.complete?"":" · 已覆盖小计"}</div><div class="result-boundary">${esc(result.boundary)}</div>${baselineHtml}
    ${result.errors.length?`<h3>需修正</h3><ul class="result-list errors">${result.errors.map(e=>`<li>${esc(e)}</li>`).join("")}</ul>`:""}
    ${result.missing.length?`<h3>尚未覆盖 / 待确认（${result.missing.length}）</h3><ul class="result-list">${result.missing.map(m=>`<li>${esc(m.message)}</li>`).join("")}</ul>`:""}
    <h3>已计算贡献</h3>${bars||'<p class="hint">尚无可计算贡献。</p>'}
    <details><summary>各工序数量与损耗</summary><div class="table-wrap"><table><thead><tr><th>工序</th><th>产出 kg</th><th>投入 kg</th><th>损失 kg</th></tr></thead><tbody>${result.chain_quantities.map(q=>`<tr><td>${esc(q.name)}</td><td>${fmt(q.output_kg,6)}</td><td>${fmt(q.input_kg,6)}</td><td>${fmt(q.waste_kg,6)}</td></tr>`).join("")}</tbody></table></div><p class="hint">所需起始投入：${fmt(result.initial_input_kg,6)} kg；损失材料：${fmt(result.total_waste_kg,6)} kg。未知环节不填 0。</p></details>
    ${result.warnings.length?`<details><summary>适用性与边界提示</summary><ul class="result-list">${result.warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></details>`:""}
    <p class="hint">确定性计算；未生成“±”误差。DQR 不等于误差条。<br>目录版本：${esc(result.catalog_digest.slice(0,12))} · 模型：${esc(result.model_sha256.slice(0,12))}</p>`;
}
async function evaluate() {
  const request=++requestNumber,hasBaseline=Boolean(baseline);
  $("#model-json").value=JSON.stringify(model,null,2);
  try {
    const data=hasBaseline?await api("/api/compare",{model,baseline}):await api("/api/calculate",{model});
    if(request!==requestNumber)return;
    renderResult(hasBaseline?data.current:data,hasBaseline?data:null);
  } catch(error) {if(request===requestNumber)notify(error.message);}
}
function schedule() {requestNumber++;clearTimeout(timer);timer=setTimeout(evaluate,120);}

function showDetail(fid) {
  const f=allFactors().find(f=>f.id===fid);
  if(!f)return notify("因子已不存在。");
  const external=f.category==="external";
  $("#factor-detail").innerHTML=`${!external?`<div class="source-callout"><b>公开结果因子</b> · 先核对对象、功能单位与包含项。${evidenceLink("docs/processes/"+f.category+".md","阅读中文工序卡")}<br>${typeof window!=="undefined"&&window.CFLearning?esc(window.CFLearning.caseUsage(f.id)):""}</div>`:""}<h3>${esc(f.activity_zh)}</h3><p class="hint">${esc(f.activity_en||"")}</p><p class="descriptor">${esc(f.descriptor||f.id)}</p>
    <dl><dt>GHG 原值</dt><dd><b>${esc(f.impacts.GHG)} kg CO₂e/${esc(f.unit_label||f.unit)}</b></dd><dt>功能单位</dt><dd>${esc(f.functional_unit_original||f.unit_label||f.unit)}</dd><dt>投入产出字段</dt><dd>${esc(f.input_ratio??"未提供")}</dd><dt>适用边界</dt><dd>${esc(f.boundary||f.source.scope)}</dd><dt>限制</dt><dd>${esc(f.limitations||f.status)}</dd><dt>地域 / 数据年</dt><dd>${esc(f.geography_tag||"人工说明")} / ${esc(f.data_year||"未知")}</dd></dl>
    ${external?`<p>人工来源：${esc(f.source.reference)}</p>`:`<h3>原始证据</h3><p>${evidenceLink(f.source.csv,"CSV（逻辑记录 "+f.source.csv_record+"）")} · ${evidenceLink(f.source.unit_evidence,"功能单位说明")}</p><p class="hint">CSV SHA256：${esc(f.source.sha256)}</p><div class="learn-links">${f.source.methods.map(p=>evidenceLink(p,p.split("/").pop())).join("")}</div><h3>16 项影响原值</h3><div class="table-wrap"><table><thead><tr><th>代码</th><th>原值（分母为本记录的功能单位）</th></tr></thead><tbody>${Object.entries(f.impacts).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div><p class="hint">DQR（1 较好，5 较弱）：${Object.entries(f.dqr).map(([k,v])=>esc(k)+"="+esc(v??"未知")).join("；")}。不直接推导数值不确定性。</p>`}
    <div class="attribution">公开来源：Carbonfact · CC BY-SA 4.0 · 中文展示为应用层解释。${evidenceLink("docs/字段字典.md","中文字段与指标说明")}</div>`;
  $("#factor-dialog").showModal();
}
function renderCatalog() {
  const query=$("#search").value.trim().toLowerCase(),category=$("#category-filter").value,unit=$("#unit-filter").value;
  const caseIds=new Set(presets.tshirt.chain.map(s=>s.factor_id));
  const rows=catalog.factors.filter(f=>(!$("#case-only").checked||caseIds.has(f.id))&&(!category||f.category===category)&&(!unit||f.unit===unit)&&(!query||[f.activity_zh,f.activity_en,f.descriptor].join(" ").toLowerCase().includes(query)));
  $("#filter-count").textContent=rows.length+" 条";
  $("#factor-rows").innerHTML=rows.map(f=>`<tr><td>${esc(f.activity_zh)}<small>${esc(f.activity_en)}</small>${presets.tshirt.chain.some(s=>s.factor_id===f.id)?'<span class="badge">T 恤教学案例</span>':''}</td><td>${esc(f.category_zh)}</td><td>${fmt(f.impacts.GHG,6)}<small>kg CO₂e/${esc(f.unit_label)}</small></td><td>${esc(f.input_ratio??"未知")}</td><td>${detailButton(f.id)}</td></tr>`).join("");
}
function renderLearn() {
  const docs=[["体验升级使用指南.md","新版入门、案例与七步演示"],["中文入门.md","先读：数据库、因子与工序"],["字段字典.md","字段、单位与 16 项指标"],["核算规则.md","数量、边界与缺项"],["开发接续.md","代码、模型及 API"],["覆盖升级指南.md","本地迁移与删除清单"],["已知差异.md","快照差异与建模缺口"]];
  $("#learn-content").innerHTML=`<section class="panel"><h2>如何在中文语境下掌握这个项目</h2><p>先看工序做什么，再看“每多少产出”的影响值，最后检查已经包含什么、还缺什么。原始数据库同时提供结果和部分建模说明；完整底层清单并未全部公开。</p><div class="learn-links">${docs.map(([p,n])=>evidenceLink("docs/"+p,n)).join("")}</div><p class="hint">中文资料可在项目 docs 文件夹中用 Markdown 编辑器阅读；原文 PDF 保留在 upstream/carbonfact。</p></section>
    <div class="learning-grid">${catalog.categories.map(c=>`<section class="panel"><h2>${esc(c.name)} <span class="badge">${catalog.factors.filter(f=>f.category===c.id).length} 条</span></h2><p>${esc(c.boundary)}</p><p>${esc(c.limitations)}</p>${evidenceLink("docs/processes/"+c.id+".md","中文工序卡")} · <button data-action="browse-category" data-id="${esc(c.id)}">浏览记录</button></section>`).join("")}</div>`;
}
function openTab(name) {
  document.querySelectorAll(".tab-panel").forEach(p=>p.hidden=p.id!==name+"-tab");
  document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));
}
function download(name, value) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json;charset=utf-8"}));
  const a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
}

document.addEventListener("change",event=>{
  const element=event.target,path=element.dataset.path;
  if(path){
    let value=element.type==="checkbox"?element.checked:element.value;
    if(path.endsWith("factor_id"))value=value||null;
    setPath(path,value);
    if(path.endsWith(".mode")){
      const i=Number(path.split(".")[1]),s=model.chain[i];
      s.factor_id=null;s.inventory=[];
      if(value==="inventory"){s.inventory_complete=false;s.ratio_mode="ratio";s.input_ratio="1";s.ratio_note="请填实测投入产出依据";}
    }
    if(path.startsWith("external_factors."))refreshFactorLists();
    else if(path.endsWith(".mode")||path.endsWith(".ratio_mode")||path.startsWith("chain.")&&path.endsWith("factor_id"))renderChain();
    else if(path==="include_materials")renderMaterials();
    else if(path==="result_basis")renderProduct();
    notify("");schedule();
  }
  if(element.dataset.action==="stage-category"){
    const i=Number(element.dataset.index);viewCategory.set(model.chain[i].id,element.value);model.chain[i].factor_id=null;renderChain();schedule();
  }
});
document.addEventListener("input",event=>{
  const path=event.target.dataset.path;
  if(path && event.target.tagName!=="SELECT" && event.target.type!=="checkbox"){
    setPath(path,event.target.value);if(path.startsWith("external_factors."))refreshFactorLists();schedule();
  }
});
document.addEventListener("click",event=>{
  const b=event.target.closest("button");if(!b)return;
  if(b.dataset.tab)return openTab(b.dataset.tab);
  const action=b.dataset.action,i=Number(b.dataset.index),j=Number(b.dataset.subindex);
  if(action==="detail")return showDetail(b.dataset.id);
  if(action==="browse-category"){$("#category-filter").value=b.dataset.id;openTab("catalog");renderCatalog();return;}
  if(action==="up"&&i>0)[model.chain[i-1],model.chain[i]]=[model.chain[i],model.chain[i-1]];
  if(action==="down"&&i<model.chain.length-1)[model.chain[i+1],model.chain[i]]=[model.chain[i],model.chain[i+1]];
  if(action==="remove-stage")model.chain.splice(i,1);
  if(action==="add-material")model.materials.push({name:"新材料",share_percent:"0",factor_id:null});
  if(action==="remove-material")model.materials.splice(i,1);
  if(action==="remove-extra")model.additional_items.splice(i,1);
  if(action==="remove-factor")model.external_factors.splice(i,1);
  if(action==="add-input")model.chain[i].inventory.push({name:"投入项",quantity:null,unit:"kg",factor_id:null});
  if(action==="remove-input")model.chain[i].inventory.splice(j,1);
  if(action){renderModel();schedule();}
});

async function start(){
  try {
    [catalog,presets]=await Promise.all([api("/api/catalog"),api("/api/templates")]);
    model=clone(presets.tshirt);
    $("#category-filter").innerHTML=option("","全部类别","")+catalog.categories.map(c=>option(c.id,c.name,"")).join("");
    renderModel();renderCatalog();renderLearn();await evaluate();
    if(typeof window!=="undefined"&&window.CFLearning)window.CFLearning.mount({showFactor:showDetail,navigate:openTab,loadModel:candidate=>{model=prepareModel(candidate);viewCategory.clear();renderModel();openTab("model");notify("已将当前教学案例载入工作台；请按你的产品复核适用性。");schedule();}});
    $("#search").addEventListener("input",renderCatalog);
    $("#case-only").addEventListener("change",renderCatalog);
    $("#category-filter").addEventListener("change",renderCatalog);
    $("#unit-filter").addEventListener("change",renderCatalog);
    $("#close-dialog").onclick=()=>$("#factor-dialog").close();
    $("#reset-template").onclick=()=>{model=clone(presets[$("#template").value]);viewCategory.clear();renderModel();notify("已载入结构模板；当前输入已替换，基线仍保留供比较。");schedule();};
    $("#add-stage").onclick=()=>{model.chain.push({id:"stage-"+Date.now(),name:"新增工序",mode:"factor",factor_id:null,ratio_mode:"factor"});renderModel();schedule();};
    $("#add-extra").onclick=()=>{model.additional_items.push({id:"extra-"+Date.now(),name:"新增独立项目",quantity:null,unit:"kg",factor_id:null});renderModel();schedule();};
    $("#add-factor").onclick=()=>{model.external_factors.push({id:"ext-"+Date.now(),name:"",ghg:"",unit:"kg",source:"",scope:"",status:"pending",kind:"process"});renderExternal();refreshFactorLists();schedule();};
    $("#set-baseline").onclick=()=>{baseline=clone(model);renderModel();notify("当前模型已设为比较基线；后续修改会与它比较。");schedule();};
    $("#clear-baseline").onclick=()=>{baseline=null;renderModel();schedule();};
    $("#save-model").onclick=async()=>{try{const value=await api("/api/export",{model});download("carbonfact-model.json",value);notify("已导出模型、结果、所选来源记录与署名。");}catch(error){notify(error.message);}};
    $("#load-model").onclick=()=>$("#file-input").click();
    $("#file-input").onchange=async event=>{
      const file=event.target.files[0];if(!file)return;
      try{const parsed=JSON.parse((await file.text()).replace(/^\uFEFF/,"")),candidate=prepareModel(parsed.model||parsed);
        await api("/api/calculate",{model:candidate});model=candidate;viewCategory.clear();renderModel();notify("模型已载入；结果由后台重新计算。");await evaluate();
      }catch(error){notify("加载失败："+error.message);}finally{event.target.value="";}
    };
    $("#apply-json").onclick=async()=>{try{const candidate=prepareModel(JSON.parse($("#model-json").value));await api("/api/calculate",{model:candidate});model=candidate;renderModel();await evaluate();notify("已应用高级模型。");}catch(error){notify("JSON 应用失败："+error.message);}};
  }catch(error){notify("应用初始化失败："+error.message);}
}
start();
