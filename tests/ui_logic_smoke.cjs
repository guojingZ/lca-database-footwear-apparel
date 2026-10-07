/* 可选 Node 检查：模拟 DOM 事件 + 实际 Python HTTP，不代表浏览器布局验收。 */
"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),assert=require("node:assert/strict"),{spawn}=require("node:child_process");
const root=path.resolve(__dirname,".."),port=18768;
const server=spawn(process.env.CARBONFACT_TEST_PYTHON||"python3",["-u","app.py","--no-browser","--port",String(port)],{cwd:root,stdio:["ignore","pipe","pipe"]});
let stderr="";server.stderr.on("data",b=>stderr+=b);
let window,context,document;const tested=[],captured=[];

class Element {
  constructor(id=""){this.id=id;this.innerHTML="";this.textContent="";this.value="";this.hidden=false;this.dataset={};this.listeners={};this.classList={toggle(){}};this.tagName="DIV";this.type="";}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  append(){} remove(){} click(){if(this.onclick)this.onclick({target:this});}
  closest(){return this;} showModal(){this.open=true;} close(){this.open=false;}
}
function dom(){
  const html=fs.readFileSync(path.join(root,"web/index.html"),"utf8"),elements=new Map();
  for(const match of html.matchAll(/\bid="([^"]+)"/g))elements.set("#"+match[1],new Element(match[1]));
  elements.get("#template").value="tshirt";
  const tabs=["model","catalog","learn"].map(name=>{const e=new Element();e.dataset.tab=name;return e;});
  const panels=["model","catalog","learn"].map(name=>elements.get("#"+name+"-tab"));
  const listeners={};
  return {elements,listeners,querySelector:s=>{if(!elements.has(s))throw new Error("未登记 DOM 路径 "+s);return elements.get(s);},
    querySelectorAll:s=>s===".tab-panel"?panels:s===".tabs button"?tabs:[],
    addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn),createElement:()=>new Element(),body:new Element()};
}
async function waitUntil(fn,description,timeout=8000){const start=Date.now();while(!fn()){if(Date.now()-start>timeout)throw new Error("超时："+description+"\n"+stderr);await new Promise(resolve=>setTimeout(resolve,25));}}
const q=selector=>document.querySelector(selector);
async function update(field,value,type="text",event="change"){
  const e=new Element();e.dataset.path=field;e.value=value;e.type=type;e.tagName="INPUT";e.checked=value===true;
  for(const fn of document.listeners[event]||[])fn({target:e});
  await settle();
}
async function action(action,index,id){const e=new Element();e.tagName="BUTTON";e.dataset={action,index:String(index),id};for(const fn of document.listeners.click||[])fn({target:e});await settle();}
async function settle(){await new Promise(resolve=>setTimeout(resolve,160));await vm.runInContext("evaluate()",context);}
function state(){return JSON.parse(vm.runInContext("JSON.stringify(model)",context));}
function pass(name){tested.push(name);}

(async()=>{
  try{
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error("服务启动超时\n"+stderr)),10000);server.stdout.on("data",b=>{if(String(b).includes("http://127.0.0.1:")){clearTimeout(timer);resolve();}});server.on("error",reject);server.on("exit",code=>{if(code)reject(new Error("服务启动失败 "+code+"\n"+stderr));});});
    document=dom();
    window={document,console,setTimeout,clearTimeout,Blob,URL,Map,Date,JSON,Number,String,Promise,
      fetch:async(url,options)=>{const response=await fetch(`http://127.0.0.1:${port}${url}`,options);const body=await response.json();captured.push({url,body});return {ok:response.ok,json:async()=>body};}};
    context=vm.createContext(window);vm.runInContext(fs.readFileSync(path.join(root,"web/app.js"),"utf8"),context);
    await waitUntil(()=>q("#result-status").textContent==="已覆盖部分排放","首屏初始化");
    assert.equal(state().chain.length,6);assert.match(q("#result").innerHTML,/1\.75876/);pass("初始化、6 段 T 恤链及部分结果");
    await update("weight_g","280","number","input");assert.match(q("#result").innerHTML,/3\.51752/);pass("修改重量后后台结果同比更新");
    q("#set-baseline").click();await settle();await update("weight_g","140","number","input");assert.match(q("#result").innerHTML,/基线比较/);assert.match(q("#result").innerHTML,/-1\.75876/);pass("基线保存与差值更新");
    await action("down",0);assert.equal(state().chain[1].id,"spinning");pass("工序顺序调整");
    await action("remove-stage",0);assert.match(q("#result").innerHTML,/必需工序缺失/);pass("删必需工序仍保留缺项");
    q("#category-filter").value="finishing";q("#search").value="热定型";vm.runInContext("renderCatalog()",context);assert.equal(q("#filter-count").textContent,"1 条");pass("中文与类别检索");
    const realFactor=vm.runInContext("catalog.factors.find(f=>f.category==='finishing' && f.activity_en.includes('Heat setting')).id",context);
    await action("detail",undefined,realFactor);assert.equal(q("#factor-dialog").open,true);assert.match(q("#factor-detail").innerHTML,/0\.4593358479382707/);assert.match(q("#factor-detail").innerHTML,/逻辑记录/);q("#close-dialog").click();pass("因子原值、来源、弹窗关闭");
    await q("#save-model").onclick();const packet=captured.findLast(v=>v.url==="/api/export").body;
    assert.equal(packet.attribution.license,"CC BY-SA 4.0");assert.ok(packet.selected_source_records.length>0);pass("导出模型、结果和来源记录");
    const original=JSON.stringify(state());await update("weight_g","300","number","input");
    await q("#file-input").onchange({target:{files:[{text:async()=>JSON.stringify(packet)}],value:"file.json"}});assert.equal(JSON.stringify(state()),original);pass("加载保存 JSON 并重算复现");
    const wrong=structuredClone(packet);wrong.model.catalog_digest="different";
    await q("#file-input").onchange({target:{files:[{text:async()=>JSON.stringify(wrong)}],value:"file.json"}});assert.match(q("#notice").textContent,/目录版本不同/);assert.equal(JSON.stringify(state()),original);pass("目录不匹配拒绝载入");
    q("#template").value="factory";q("#reset-template").click();await settle();assert.equal(state().chain.length,3);assert.match(q("#result").innerHTML,/665\.49914/);pass("涤纶染整模板");
    await update("chain.1.ratio_mode","loss");await update("chain.1.loss_percent","20","number");await update("chain.1.ratio_note","测试损耗定义");assert.match(q("#chain").innerHTML,/投入质量为分母/);assert.equal(captured.findLast(v=>v.url==="/api/compare").body.current.valid,true);pass("损耗模式、依据输入与后台校验");
    q("#template").value="inventory";q("#reset-template").click();await settle();assert.equal(state().chain[0].inventory.length,6);assert.match(q("#result").innerHTML,/待定/);assert.equal(captured.findLast(v=>v.url==="/api/compare").body.current.subtotal_ghg,null);pass("企业清单缺量时不显示假零");
    q("#add-factor").click();const fi=state().external_factors.length-1;
    for(const [key,value] of Object.entries({name:"逻辑测试电力",ghg:"0.5",unit:"kWh",source:"合成测试夹具",scope:"仅程序校验",status:"hypothetical"}))await update(`external_factors.${fi}.${key}`,value);
    const fid=state().external_factors[fi].id;await update("chain.0.inventory.0.factor_id",fid);await update("chain.0.inventory.0.quantity","2","number");
    assert.match(q("#result").innerHTML,/假设因子/);assert.match(q("#result").innerHTML,/100/);pass("外部假设因子与每 kg 投入量计算");
    q("#add-extra").click();assert.equal(state().additional_items.length,1);await action("remove-extra",0);assert.equal(state().additional_items.length,0);pass("独立定量项目增删");
    const report={ok:true,type:"模拟 DOM 事件 + 实际 Python HTTP；未执行真实浏览器布局/下载对话框验收",checks:tested};
    console.log(JSON.stringify(report,null,2));
    if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(report,null,2)+"\n");
  }finally{if(server.exitCode===null)server.kill("SIGTERM");}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
