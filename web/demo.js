/* 独立演示控制器；业务模型由后台从模板与白名单参数组装。 */
(() => {
  "use strict";
  const $=s=>document.querySelector(s),esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt=v=>v==null?"未知":Number(v).toLocaleString("zh-CN",{maximumFractionDigits:6});
  const storageKey="carbonfact.demo.v1",clone=x=>JSON.parse(JSON.stringify(x));
  let content,state,last=null,revision=0,blocked=null;
  const initial=()=>({schema_version:1,catalog_digest:content.catalog_digest,current_step:0,done:[],trace:[],factor_reviewed:false,
    params:{catalog_digest:content.catalog_digest,task:"学习一件 140 g 棉 T 恤怎样核算",weight_g:"140",organic_share:"60",recycled_share:"40",scenario:"baseline",dyeing_selected:true,review_note:"",review_status:"pending"}});
  const doc=(p,t)=>`<a href="/reader?path=${encodeURIComponent(p)}" target="_blank" rel="noopener">${esc(t)}</a>`;
  const field=(id,title,value,type="text")=>`<label>${esc(title)}<input id="demo-${id}" data-param="${id}" type="${type}" ${type==="number"?'step="any" min="0"':''} value="${esc(value)}"></label>`;
  function notice(text){$("#demo-notice").textContent=text;}
  function save(){try{localStorage.setItem(storageKey,JSON.stringify(state));$("#demo-save-status").textContent="本浏览器进度已保存";}catch{$("#demo-save-status").textContent="浏览器存储不可用；请导出 JSON 保存";}}
  function trace(action){state.trace.push({step:state.current_step+1,action,at:new Date().toISOString()});state.trace=state.trace.slice(-100);save();}
  async function request(path,payload){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw new Error(data.error||"请求失败");return data;}
  function summary(){const r=last?.result;$("#demo-summary").innerHTML=`<div>任务<strong>${esc(state.params.task||"待填写")}</strong></div><div>输入重量<strong>${esc(state.params.weight_g)} g</strong></div><div>计算状态<strong>${r?esc(r.label):"等待重算"}</strong></div><div>已覆盖小计<strong>${r&&r.valid?fmt(r.subtotal_ghg):"—"}</strong></div><div>完成步骤<strong>${state.done.length} / 7</strong></div>`;}
  function navigation(){
    $("#demo-steps").innerHTML=content.demo_steps.map((name,i)=>`<button class="demo-step ${i===state.current_step?"active":""} ${state.done.includes(i)?"done":""}" data-demo-step="${i}" aria-current="${i===state.current_step?"step":"false"}"><span class="step-number">${state.done.includes(i)?"✓":i+1}</span>${esc(name)}</button>`).join("");
    $("#demo-progress").textContent=`已完成 ${state.done.length} / 7 步`;
    $("#demo-prev").disabled=state.current_step===0;
    $("#demo-next").textContent=state.current_step===6?"记录本次学习已完成":"完成本步并继续 →";
    }
  function render(){
    navigation();summary();const p=state.params,r=last?.result;
    const candidate=last?.candidate||content.case.selected_source_records.find(f=>f.category==="dyeing");
    const title=`<span class="card-index">第 ${state.current_step+1} 步 / 7</span><h2>${esc(content.demo_steps[state.current_step])}</h2>`;
    const sections=[
      `<p>先把一句想法变成可执行的任务：希望理解一件棉 T 恤，从原料到成衣出厂的哪些排放已经可算、还缺什么。</p>${field("task","我的教学任务",p.task)}<div class="example-note"><b>固定教学边界：</b>原料至成衣出厂；每件结果；单一主布质量链。实际多部件、企业条件与完整生命周期需要独立建模。</div><h3>最终得到什么</h3><p>一份产品模型、可复算的已覆盖小计、所选公开证据、缺项与下一步采数清单。学习完成不等于获得完整认证结果。</p>${doc("docs/中文入门.md","先了解数据库、因子与工序")}`,
      `<p><b>示例生产表达：</b>一件 140 g 棉 T 恤，60% 有机棉与 40% 再生棉，经过纺纱、圆机针织、前处理、活性染色、柔软整理与装配。</p><p class="hint">这是模板表达。下面由你调整结构化事实；本演示不声称自动解析任意企业原文。</p><div class="form-grid">${field("weight_g","每件成品质量（g）",p.weight_g,"number")}${field("organic_share","有机棉占比（%）",p.organic_share,"number")}${field("recycled_share","再生棉占比（%）",p.recycled_share,"number")}</div><div class="example-note">已知结构：每件、主布链、kg 产出。待确认：真实工艺适用性、材料生产因子、前处理因子与真实投入比。</div><button data-demo-action="calculate" class="secondary">检查输入并查看后台结果</button>${r&&!r.valid?`<ul class="result-list errors">${r.errors.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:""}`,
      `<p>先检查对象、功能单位、设备与包含项，再决定采用哪条代表记录。六个工序沿用 T 恤模板，前处理保持缺因子。</p><div class="journey-strip">${content.case.model.chain.map(s=>`<span>${esc(s.name)}</span>`).join("")}</div><div class="choice-card"><span class="badge">可研究的代表候选</span><h3>${esc(candidate.activity_zh)}</h3><p><b>GHG 原值：${esc(candidate.impacts.GHG)} kg CO₂e/kg 产出</b> · 投入比 ${esc(candidate.input_ratio)}</p><p class="hint source-path">${esc(candidate.id)} · CSV 逻辑记录 ${esc(candidate.source.csv_record)} · ${doc(candidate.source.unit_evidence,"核对单位原文")}</p><p>功能单位：kg 工序产出。中等色深、活性染料、柔流喷射；并非企业专属实测。</p><p>${doc("docs/processes/dyeing.md","阅读中文染色卡")} · <a href="/evidence/upstream/carbonfact/datasets/dyeing/impact-scores.csv" target="_blank" rel="noopener">查看原始 CSV</a></p><label class="check"><input type="checkbox" id="demo-dyeing-selected" data-param="dyeing_selected" ${p.dyeing_selected?"checked":""}>采用模板的活性染色代表因子；不选则保留缺项</label><label class="check"><input type="checkbox" id="demo-factor-reviewed" ${state.factor_reviewed?"checked":""}>我已阅读适用条件，理解这只是教学选择</label></div><div class="choice-card excluded"><b>为什么不选另一类染色？</b><p>涤纶等合成纤维的分散染记录不直接用于当前棉/纤维素对象。候选不是按 GHG 最小值自动批准。</p></div>`,
      `<p>每道工序加工量取自己的产出质量，并从成衣向前反推投入。下面只让同一 Python 引擎计算。</p><label>选择练习情景<select id="demo-scenario" data-param="scenario">${Object.entries(content.scenarios).map(([id,name])=>`<option value="${id}" ${id===p.scenario?"selected":""}>${esc(name)}</option>`).join("")}</select></label><p class="hint">重量翻倍以第 2 步当前输入为基线；80/20 会采用指定配比；损耗 20% 是教学假设，并不重建公开加工模型。</p><button class="primary" data-demo-action="calculate">运行并更新结果</button>${calculationHtml()}`,
      `<p>把“还不能算”的原因变成下一轮资料需求。当前有缺项是教学结果的一部分。</p>${r?`<div class="table-wrap"><table><thead><tr><th>当前问题</th><th>下一步取得什么</th></tr></thead><tbody>${last.gap_actions.map(x=>`<tr><td>${esc(x.issue)}</td><td>${esc(x.next_action)}</td></tr>`).join("")}</tbody></table></div>`:'<div class="demo-placeholder">参数尚未计算。<button data-demo-action="calculate">先运行当前任务</button></div>'}<p class="hint">原料因子不能用纺纱加工代替；装配已列包装、缝线等包含项，补充前先核查重复。</p>`,
      `<p>假如新资料指出模板某项假设不适合你的工厂，先记录证据与修正建议，再决定下一轮怎样处理。</p><label>来源或复核意见<textarea id="demo-review-note" data-param="review_note" rows="5" placeholder="例如：前处理投入比 1 只是结构假设；下一轮需要企业称重或有来源的清单。">${esc(p.review_note)}</textarea></label><label>本演示的处理状态<select id="demo-review-status" data-param="review_status"><option value="pending" ${p.review_status==="pending"?"selected":""}>待核对</option><option value="accepted" ${p.review_status==="accepted"?"selected":""}>演示采纳：列入下一轮</option><option value="rejected" ${p.review_status==="rejected"?"selected":""}>演示退回：依据不足</option></select></label><div class="example-note">此处只保存本次演示意见，不修改公共因子、原始方法学或工作台模型。状态变化也不会把 partial 自动改为 complete。</div>${doc("docs/已知差异.md","看现有来源差异怎样保留")}`,
      `<p>交付应让另一个人知道采用什么、怎么算、还缺什么，以及如何继续。</p><div class="demo-downloads"><button data-demo-action="export-json" class="primary">下载模型与证据 JSON</button><button data-demo-action="export-report">下载中文报告 Markdown</button><button data-demo-action="backup-state">下载当前演示进度</button></div><p>JSON 中的 model 可在原工作台“加载 JSON”后重算。完整演示 JSON 也可在本页导入恢复。原始 PDF 保留在项目来源层，JSON 保存所选公开记录与路径。</p><div class="demo-placeholder"><b>接下来到自己的项目</b><p>把工序的适用条件、输入/输出、单位、边界、候选映射、来源和数量规则整理成模块；再调用同一计算引擎。</p>${doc("docs/开发接续.md","查看 Python 与 API 接入方式")}</div><h3>这次怎样走过来的</h3><ol class="demo-trace">${state.trace.slice(-12).map(x=>`<li>第 ${esc(x.step)} 步：${esc(x.action)}</li>`).join("")||"<li>还没有记录操作；可从第 1 步开始。</li>"}</ol>`
    ];
    $("#demo-stage").innerHTML=title+sections[state.current_step];
  }
  function calculationHtml(){if(!last)return '<div class="demo-placeholder">参数有变化或尚未运行。点击上方按钮生成当前结果。</div>';const r=last.result;if(!r.valid)return `<div class="demo-notice">输入需要修正：<ul>${r.errors.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>`;return `<div class="source-callout"><strong>${fmt(r.subtotal_ghg)} ${esc(r.unit)}</strong> · ${esc(r.label)}<br>当前采用重量 ${esc(last.model.weight_g)} g；起始投入 ${fmt(r.initial_input_kg)} kg。<br>${esc(last.comparison.note)} ${last.comparison.comparable?`差值：${fmt(last.comparison.delta_ghg)}`:""}</div><div class="table-wrap"><table><thead><tr><th>工序</th><th>产出 kg</th><th>投入 kg</th><th>损失 kg</th></tr></thead><tbody>${r.chain_quantities.map(q=>`<tr><td>${esc(q.name)}</td><td>${fmt(q.output_kg)}</td><td>${fmt(q.input_kg)}</td><td>${fmt(q.waste_kg)}</td></tr>`).join("")}</tbody></table></div><h3>已计算贡献</h3>${r.contributions.map(c=>`<p>${esc(c.name)}：${fmt(c.quantity)} ${esc(c.unit)} × ${fmt(c.factor_ghg)} = <b>${fmt(c.ghg)} kg CO₂e</b></p>`).join("")}<p class="hint">${r.missing.length} 条缺项/待确认；详见下一步。源值保留原精度，页面仅做显示舍入。</p>`;}
  async function calculate(){
    if(blocked)throw new Error("旧进度目录不同，请先备份旧进度并重置演示。");
    const id=++revision;last=null;summary();notice("正在用 Python 引擎计算…");
    const next=await request("/api/demo/calculate",{state:state.params});
    if(id!==revision)return null;
    last=next;trace("运行："+next.scenario_label);notice(next.result.valid?"已更新当前结果；缺项继续保留。":"输入需要修正；不会显示上一次结果。");render();return next;
  }
  async function ensureResult(){if(!last)await calculate();if(!last?.result.valid)throw new Error("请修正输入并重算后继续。");}
  function download(name,text,type="application/json;charset=utf-8"){const u=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement("a");a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
  async function exportFile(kind){await ensureResult();const data=await request("/api/demo/export",{state:state.params});trace("导出："+(kind==="export-json"?"模型与证据":"中文报告"));data.packet.demo_ui={current_step:state.current_step,done:state.done,factor_reviewed:state.factor_reviewed};data.packet.demo_trace=clone(state.trace);if(kind==="export-json")download("tshirt-demo-model.json",JSON.stringify(data.packet,null,2)+"\n");else download("tshirt-demo-report.md",data.markdown+"\n学习完成步骤："+state.done.map(i=>i+1).join("、")+" / 7\n","text/markdown;charset=utf-8");notice("已下载；模型 JSON 可在工作台重算，报告仍保留教学标记与缺项。");render();}
  function cleanTrace(items){return Array.isArray(items)?items.filter(x=>x&&typeof x.action==="string"&&Number.isInteger(x.step)&&x.step>=1&&x.step<=7).slice(-100).map(x=>({step:x.step,action:x.action.slice(0,400),at:typeof x.at==="string"?x.at.slice(0,80):""})):[];}
  function changed(element){if(element.id==="demo-factor-reviewed"){state.factor_reviewed=element.checked;state.done=state.done.filter(i=>i<2);save();navigation();summary();return;}const key=element.dataset.param;if(!key)return;const invalidate={task:0,weight_g:1,organic_share:1,recycled_share:1,dyeing_selected:2,scenario:3,review_note:5,review_status:5}[key]??0;state.done=state.done.filter(i=>i<invalidate);state.params[key]=element.type==="checkbox"?element.checked:element.value;revision++;last=null;save();navigation();summary();notice("输入已变；请重新运行，导出前也会核对当前结果。");}
  function stable(value){return JSON.stringify(value,(key,v)=>v&&typeof v==="object"&&!Array.isArray(v)?Object.keys(v).sort().reduce((o,k)=>(o[k]=v[k],o),{}):v);}
  async function importFile(file){
    if(file.size>2_000_000)throw new Error("演示文件不能超过 2 MB");
    const parsed=JSON.parse((await file.text()).replace(/^\uFEFF/,""));
    const params=parsed.demo_state||parsed.state?.params||parsed.params;
    if(!params)throw new Error("这不是演示进度或演示模型包；自定义产品请在原工作台加载。");
    const next=await request("/api/demo/calculate",{state:params});if(!next.result.valid)throw new Error("导入参数需修正："+next.result.errors.join("；"));
    if(parsed.model&&stable(parsed.model)!==stable(next.model))throw new Error("模型与演示参数不一致；自定义模型请在原工作台加载。");
    const ui=parsed.demo_ui||parsed.state||parsed;state=initial();state.params=next.state;
    state.current_step=Number.isInteger(ui.current_step)&&ui.current_step>=0&&ui.current_step<7?ui.current_step:0;
    state.done=Array.isArray(ui.done)?[...new Set(ui.done.filter(x=>Number.isInteger(x)&&x>=0&&x<7))]:[];
    state.factor_reviewed=ui.factor_reviewed===true;state.trace=cleanTrace(parsed.demo_trace||parsed.state?.trace);
    blocked=null;revision++;last=next;trace("导入演示并按当前参数重算");render();notice("演示已恢复；原工作台内容保持独立。");
  }
  function reset(){state=initial();blocked=null;last=null;revision++;trace("重置为新的教学任务");notice("已重置本页演示；原工作台未受影响。");render();}
  async function start(){try{
    const r=await fetch("/api/learning");if(!r.ok)throw new Error("学习资料请求失败");content=await r.json();state=initial();
    try{const stored=JSON.parse(localStorage.getItem(storageKey)||"null");if(stored){if(stored.catalog_digest!==content.catalog_digest){blocked=stored;notice("旧进度目录版本不同。可先下载旧进度，再重置继续。");}else if(stored.schema_version===1&&stored.params){state={...state,...stored,params:{...state.params,...stored.params}};state.factor_reviewed=stored.factor_reviewed===true;state.current_step=Number.isInteger(stored.current_step)&&stored.current_step>=0&&stored.current_step<7?stored.current_step:0;state.done=Array.isArray(stored.done)?[...new Set(stored.done.filter(x=>Number.isInteger(x)&&x>=0&&x<7))]:[];state.trace=cleanTrace(stored.trace);}}}catch{notice("旧浏览器进度无法读取，已打开新任务；可导入已保存的 JSON。");}
    render();
    document.addEventListener("input",e=>{if(e.target.dataset.param&&e.target.tagName!=="SELECT"&&e.target.type!=="checkbox")changed(e.target);});
    document.addEventListener("change",e=>{if(e.target.tagName==="SELECT"||e.target.type==="checkbox")changed(e.target);});
    document.addEventListener("click",async e=>{const b=e.target.closest("button");if(!b)return;try{if(b.dataset.demoStep!==undefined){state.current_step=Number(b.dataset.demoStep);save();render();return;}const a=b.dataset.demoAction;if(a==="calculate")await calculate();if(a==="export-json"||a==="export-report")await exportFile(a);if(a==="backup-state"){download("tshirt-demo-progress.json",JSON.stringify({state:blocked||state},null,2)+"\n");notice("当前进度已下载。");}}catch(error){notice(error.message);}});
    $("#demo-prev").onclick=()=>{state.current_step=Math.max(0,state.current_step-1);save();render();};
    $("#demo-next").onclick=async()=>{try{if(blocked)throw new Error("请先下载旧进度并重置。");if(state.current_step===0&&!state.params.task.trim())throw new Error("请填写本次学习任务。");if(state.current_step>=1)await ensureResult();if(state.current_step===2&&state.params.dyeing_selected&&!state.factor_reviewed)throw new Error("请先阅读因子适用条件并勾选教学阅读确认，或保留缺因子。");if(state.current_step===5&&state.params.review_status==="accepted"&&!state.params.review_note.trim())throw new Error("演示采纳前请填写依据或下一轮修正意见。");if(!state.done.includes(state.current_step))state.done.push(state.current_step);trace("完成："+content.demo_steps[state.current_step]);state.current_step=Math.min(6,state.current_step+1);save();render();notice(state.done.length===7?"七步已记录完成；结果仍以当前缺项和范围为准。":"已记录本步，可以继续。");}catch(error){notice(error.message);}};
    $("#demo-reset").onclick=reset;$("#demo-import").onclick=()=>$("#demo-file").click();
    $("#demo-file").onchange=async e=>{try{if(e.target.files[0])await importFile(e.target.files[0]);}catch(error){notice("导入失败："+error.message);}finally{e.target.value="";}};
    if(!blocked){await calculate();notice(state.trace.length>1?"已恢复本浏览器任务并重新计算。":"已载入新教学任务；从第 1 步开始。");}
  }catch(error){notice("演示初始化失败："+error.message);}}
  start();
})();
