/* 轻量 DOM 事件模拟器；不模拟布局、CSS 或真实浏览器文件对话框。 */
"use strict";
const fs=require("node:fs"),vm=require("node:vm");
class Storage{constructor(){this.values=new Map();}getItem(k){return this.values.get(k)??null;}setItem(k,v){this.values.set(k,String(v));}removeItem(k){this.values.delete(k);}}
function makeBrowser({html,scripts,base,pathname="/",search="",storage=new Storage()}){
  const captures=[],downloads=[],blobs=new Map(),listeners={},all=[],elements=new Map();let document;
  class Element{
    constructor(tag="DIV",owner=null){this.tagName=tag.toUpperCase();this.owner=owner;this.dataset={};this.hidden=false;this.disabled=false;this.checked=false;this.value="";this.textContent="";this._html="";this.listeners={};this.className="";this.classList={toggle:(name,on)=>{const set=new Set(this.className.split(/\s+/).filter(Boolean));if(on)set.add(name);else set.delete(name);this.className=[...set].join(" ");}};}
    set innerHTML(value){this._html=String(value);for(let i=all.length-1;i>=0;i--)if(all[i].owner===this){if(all[i].id)elements.delete("#"+all[i].id);all.splice(i,1);}parse(this._html,this);}
    get innerHTML(){return this._html;}
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
    closest(selector){return selector==="button"&&this.tagName!=="BUTTON"?null:this;}
    append(){}remove(){}showModal(){this.open=true;}close(){this.open=false;}
    click(){if(this.tagName==="A"&&this.download)downloads.push({name:this.download,blob:blobs.get(this.href)});if(this.onclick)return this.onclick({target:this});}
  }
  const decode=v=>v.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&amp;/g,"&");
  function parse(source,owner){for(const m of source.matchAll(/<([a-z][\w-]*)([^>]*?)>/gi)){const e=new Element(m[1],owner),attrs=m[2];for(const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){const k=a[1],v=decode(a[2]);if(k.startsWith("data-"))e.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;else if(k==="class")e.className=v;else e[k]=v;}e.checked=/(?:^|\s)checked(?:\s|$)/.test(attrs);e.hidden=/(?:^|\s)hidden(?:\s|$)/.test(attrs);e.disabled=/(?:^|\s)disabled(?:\s|$)/.test(attrs);if(e.tagName==="SELECT"){const tail=source.slice(m.index+m[0].length).split(/<\/select>/i)[0];const opts=[...tail.matchAll(/<option([^>]*)>/gi)];const opt=opts.find(x=>/\bselected\b/.test(x[1]))||opts[0];if(opt)e.value=decode(opt[1].match(/value="([^"]*)"/)?.[1]??"");}all.push(e);if(e.id)elements.set("#"+e.id,e);}}
  function match(e,selector){if(selector.startsWith("#"))return e.id===selector.slice(1);const a=selector.match(/^\[data-([\w-]+)="([^"]*)"\]$/);if(a)return e.dataset[a[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]===a[2];if(selector===".tab-panel")return e.className.split(/\s+/).includes("tab-panel");if(selector===".tabs button")return e.tagName==="BUTTON"&&e.dataset.tab;return false;}
  document={querySelector:s=>{const found=s.startsWith("#")?elements.get(s):all.find(e=>match(e,s));return found||null;},querySelectorAll:s=>all.filter(e=>match(e,s)),addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn),createElement:tag=>new Element(tag),body:new Element("BODY")};
  parse(html,null);
  class BrowserURL extends URL{static createObjectURL(blob){const u="blob:test/"+blobs.size;blobs.set(u,blob);return u;}static revokeObjectURL(){}}
  const window={document,console,setTimeout,clearTimeout,Blob,URL:BrowserURL,URLSearchParams,Map,Set,Date,JSON,Number,String,Promise,localStorage:storage,location:{origin:base,pathname,search},navigator:{clipboard:{writeText:async()=>{}}},fetch:async(url,opts)=>{const r=await fetch(new URL(url,base),opts);const data=await r.json();captures.push({url,request:opts?.body?JSON.parse(opts.body):null,body:data});return {ok:r.ok,json:async()=>data};}};
  window.window=window;
  const context=vm.createContext(window);
  for(const script of scripts)vm.runInContext(fs.readFileSync(script,"utf8"),context,{filename:script});
  const q=s=>{const e=document.querySelector(s);if(!e)throw new Error("找不到模拟元素 "+s);return e;};
  async function click(selector){const e=q(selector);if(e.disabled)throw new Error("按钮不可用 "+selector);if(e.onclick)await e.onclick({target:e});for(const fn of listeners.click||[])await fn({target:e});}
  async function change(selector,value,event="change"){const e=q(selector);if(e.type==="checkbox")e.checked=Boolean(value);else e.value=value;for(const fn of e.listeners[event]||[])await fn({target:e});for(const fn of listeners[event]||[])await fn({target:e});}
  return {context,document,q,click,change,captures,downloads,storage};
}
async function until(fn,label,timeout=10000){const start=Date.now();while(!fn()){if(Date.now()-start>timeout)throw new Error("等待超时："+label);await new Promise(r=>setTimeout(r,30));}}
module.exports={makeBrowser,Storage,until};
