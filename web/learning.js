/* 新人入门与案例导学；只在明确载入时替换工作台模型。 */
(() => {
  "use strict";
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt = v => v == null ? "未知" : Number(v).toLocaleString("zh-CN", {maximumFractionDigits:6});
  const link = (path, title) => `<a href="/reader?path=${encodeURIComponent(path)}" target="_blank" rel="noopener">${esc(title)}</a>`;
  const key = "carbonfact.concepts.v1";
  let data, options, lesson = 0, snapshot, revision = 0;
  function readProgress() { try {const a=JSON.parse(localStorage.getItem(key)||"[]");return new Set(Array.isArray(a)?a.filter(x=>typeof x==="string"):[]);} catch {return new Set();} }
  const progress = readProgress();
  function writeProgress() {try {localStorage.setItem(key, JSON.stringify([...progress]));} catch { /* 私密模式下仍可阅读。 */ }}
  function showProgress() {const e=document.querySelector("#concept-progress");if(e)e.textContent=`已读 ${data.concepts.filter(c=>progress.has(c.id)).length} / ${data.concepts.length} 张 · 保存在本浏览器`;}
  function renderStart() {
    document.querySelector("#start-content").innerHTML=`<section class="welcome-band"><div><p class="eyebrow">从这里开始 · 无需先懂 LCA</p><h2>先弄懂一个概念，再算清一件产品</h2><p>这里保存公开工序结果、方法学与中文解释。用一件 T 恤，把数据、工序、数量与证据连起来。</p><div class="welcome-actions"><button class="primary" data-learn-action="case">跟着 T 恤学一遍</button><a class="button-link" href="/demo" target="_blank" rel="noopener">打开从 0 到 1 演示 ↗</a><button data-learn-action="workbench">直接进入产品工作台</button></div></div><div class="welcome-summary"><strong>12 类工序资料</strong><span>304 条公开记录 · 16 项原始影响值</span><span>当前产品引擎汇总 GHG</span><small>原始来源与中文应用分别维护</small></div></section>
    <div class="journey-strip"><span>01 理解概念</span><span>02 跟读案例</span><span>03 浏览因子与来源</span><span>04 独立完成一遍</span><span>05 使用自己的模型</span></div>
    <div class="section-title"><div><h2>先建立共同语言</h2><p class="hint">每张卡都对应同一件 T 恤。展开阅读后可以标记已读。</p></div><span id="concept-progress" class="hint"></span></div>
    <div class="concept-grid">${data.concepts.map((c,i)=>`<article class="concept-card"><span class="card-index">${String(i+1).padStart(2,"0")} / ${esc(c.group)}</span><h3>${esc(c.title)}</h3><p>${esc(c.summary)}</p><details><summary>用 T 恤理解</summary><div class="example-note">${esc(c.example)}</div><p><b>容易混淆：</b>${esc(c.misconception)}</p><div class="learn-links">${link(c.document,"继续阅读依据")}<button data-learn-action="case">进入贯穿案例</button></div></details><label class="check"><input type="checkbox" data-concept-id="${esc(c.id)}" ${progress.has(c.id)?"checked":""}>我已理解这张卡</label></article>`).join("")}</div>
    <section class="panel learning-map"><h2>项目里的东西怎样协作</h2><div class="map-grid"><div><b>来源资料</b><p>CSV / PDF / README</p><small>数值与方法依据</small></div><div><b>中文因子目录</b><p>名称 / 单位 / 范围 / 来源</p><small>检索与选择候选</small></div><div><b>产品模型</b><p>重量 / 配比 / 工序链</p><small>记录本次采用什么</small></div><div><b>Python 核算</b><p>反推数量 / 检查缺项</p><small>同一模型可重新计算</small></div></div><p class="hint">模板不是企业实测事实；有数值也可能仍缺原料、工序或边界复核。</p></section>`;
    showProgress();
  }
  function renderCase() {
    const s=data.lessons[lesson],r=snapshot?.result||data.case.result;
    document.querySelector("#case-content").innerHTML=`<section class="panel"><div class="section-title"><div><p class="eyebrow">一件 T 恤贯穿始终</p><h2>140 g 棉 T 恤：从一条因子到一条工序链</h2></div><span class="badge partial">教学模板 · 保留缺项</span></div><p>60% 有机棉 / 40% 再生棉，原料至成衣出厂。重量、配比与工艺都是结构演示设定，须替换为真实产品依据。</p><div class="lesson-nav">${data.lessons.map((x,i)=>`<button data-learn-step="${i}" class="${i===lesson?"active":""}" aria-current="${i===lesson?"step":"false"}">${i+1}. ${esc(x.title)}</button>`).join("")}</div><div class="lesson-focus"><span class="card-index">第 ${lesson+1} 步 / ${data.lessons.length}</span><h3>${esc(s.title)}</h3><p>${esc(s.body)}</p><p class="task-line">现在做：${esc(s.action)}</p><div class="welcome-actions">${link(s.document,"阅读本步依据")}<button data-learn-action="dyeing">打开染色因子</button><button data-learn-action="next">${lesson===data.lessons.length-1?"回到第一步":"下一步 →"}</button></div></div></section>
    <div class="case-columns"><section class="panel"><h2>从成衣向前反推</h2><p class="hint">投入 = 产出 × 投入比；加工贡献 = 本环节产出 × GHG。以下由 Python 引擎计算。</p><div class="table-wrap"><table><thead><tr><th>工序</th><th>产出 kg</th><th>投入 kg</th><th>损失 kg</th></tr></thead><tbody>${r.chain_quantities.map(q=>`<tr><td>${esc(q.name)}</td><td>${fmt(q.output_kg)}</td><td>${fmt(q.input_kg)}</td><td>${fmt(q.waste_kg)}</td></tr>`).join("")}</tbody></table></div><p class="hint">前处理投入比 1 为模板假设，不表示实际零损耗或零排放。</p></section>
    <section class="panel case-result"><span class="card-index">当前情景的已覆盖小计</span><div class="result-value">${r.valid?fmt(r.subtotal_ghg):"待修正"}</div><p>${esc(r.unit)} · ${esc(r.label)}</p><p>起始投入 ${fmt(r.initial_input_kg)} kg；${r.missing.length} 条缺项/待确认。</p><div class="welcome-actions"><button data-learn-action="load-case" class="primary">将当前案例载入产品工作台</button><a href="/demo" class="button-link">进入独立演示</a></div><p class="hint">载入按钮会明确替换工作台当前输入；案例浏览和练习本身不会改工作台。</p></section></div>
    <section class="panel"><div class="section-title"><div><h2>三个单变量练习</h2><p class="hint">先预测，再看结果。基线固定为 140 g、60/40。</p></div><label>练习情景<select id="case-scenario">${Object.entries(data.scenarios).map(([id,n])=>`<option value="${id}" ${id===(snapshot?.state.scenario||"baseline")?"selected":""}>${esc(n)}</option>`).join("")}</select></label></div><p id="case-explanation">${explanation(snapshot?.state.scenario||"baseline")}</p><div class="contribution-grid">${r.contributions.map(c=>`<div><b>${esc(c.name)}</b><strong>${fmt(c.ghg)}</strong><small>${fmt(c.quantity)} ${esc(c.unit)} × ${fmt(c.factor_ghg)}</small><button data-learn-factor="${esc(c.factor_id)}">看数值与来源</button></div>`).join("")}</div><details><summary>当前缺什么，下一步做什么</summary><ul class="result-list">${r.missing.map(m=>`<li>${esc(m.message)}</li>`).join("")}</ul></details></section>`;
  }
  function explanation(id) {return {baseline:"默认约 1.75876 kg CO₂e/件，仅为当前已覆盖部分；原料与前处理等仍待补充。",weight_double:"仅将重量翻倍为 280 g，当前已覆盖质量项同比增加；不能推导完整产品差异。",shares_80_20:"改为 80/20 后当前加工小计不变：原料因子尚缺，工艺参数也未随两种材料分别变化。这不表示现实配比没有影响。",loss_20:"纯教学假设：装配按投入损耗 20%，投入比为 1.25；上游所需量增加，但加工因子本身没有重新建模。"}[id];}
  async function scenario(id) {
    const current=++revision;
    document.querySelector("#case-explanation").textContent="正在用同一 Python 引擎重算…";
    const button=document.querySelector('[data-learn-action="load-case"]');if(button)button.disabled=true;
    try {const res=await fetch("/api/demo/calculate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({state:{scenario:id}})});const next=await res.json();if(!res.ok)throw new Error(next.error);if(current!==revision)return;snapshot=next;renderCase();}
    catch(error){if(current===revision){renderCase();document.querySelector("#case-explanation").textContent="重算失败，已恢复上次成功情景："+error.message;}}
  }
  function mount(config) {
    options=config;
    fetch("/api/learning").then(r=>{if(!r.ok)throw new Error(r.status===404?"未找到新版学习接口，请停止旧 Python 服务并重新运行 python app.py 后刷新":"学习资料请求失败");return r.json();}).then(value=>{data=value;renderStart();renderCase();}).catch(error=>{document.querySelector("#start-content").textContent=error.message+"；可继续使用产品工作台。";});
    document.addEventListener("change",event=>{
      if(event.target.dataset.conceptId){const id=event.target.dataset.conceptId;if(event.target.checked)progress.add(id);else progress.delete(id);writeProgress();showProgress();}
      if(event.target.id==="case-scenario")scenario(event.target.value);
    });
    document.addEventListener("click",event=>{
      const e=event.target.closest("button");if(!e)return;
      if(e.dataset.learnStep!==undefined){lesson=Number(e.dataset.learnStep);renderCase();return;}
      if(e.dataset.learnFactor){options.showFactor(e.dataset.learnFactor);return;}
      const a=e.dataset.learnAction;
      if(a==="case")options.navigate("case");
      if(a==="workbench")options.navigate("model");
      if(!data)return;
      if(a==="next"){lesson=(lesson+1)%data.lessons.length;renderCase();}
      if(a==="dyeing")options.showFactor(data.case.model.chain[3].factor_id);
      if(a==="load-case")options.loadModel(JSON.parse(JSON.stringify(snapshot?.model||data.case.model)));
      if(e.dataset.copyDescriptor)navigator.clipboard?.writeText(e.dataset.copyDescriptor).catch(()=>{});
    });
  }
  window.CFLearning={mount,caseUsage(fid){if(!data)return "";const s=data.case.model.chain.find(x=>x.factor_id===fid);return s?`T 恤教学模板用于：${s.name}`:"";}};
})();
