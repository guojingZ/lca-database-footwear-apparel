/* 只渲染安全的 Markdown 子集；原文 HTML 作为文字显示。 */
(() => {
  "use strict";
  const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function safeLink(href,path){
    try {const u=new URL(href,new URL("/evidence/"+path,location.origin));if(!["http:","https:"].includes(u.protocol))return "";
      if(u.origin===location.origin){if(!u.pathname.startsWith("/evidence/"))return "";const rel=decodeURIComponent(u.pathname.slice(10));if(!["docs/","upstream/carbonfact/","data/processed/"].some(p=>rel.startsWith(p)))return "";return rel.endsWith(".md")?"/reader?path="+encodeURIComponent(rel):u.href;}
      return u.href;
    }catch{return "";}
  }
  function inline(text,path){
    const tokens=[];let source=text.replace(/`([^`]+)`/g,(_,code)=>{tokens.push(`<code>${esc(code)}</code>`);return `\u0000${tokens.length-1}\u0000`;});
    source=source.replace(/!?\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g,(_,title,href)=>{const u=safeLink(href,path);tokens.push(u?`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(title||href)}</a>`:esc(title||href));return `\u0000${tokens.length-1}\u0000`;});
    return esc(source).replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>").replace(/\u0000(\d+)\u0000/g,(_,i)=>tokens[Number(i)]||"");
  }
  function render(text,path){
    const lines=text.replace(/\r\n/g,"\n").replace(/\u0000/g,"").split("\n"),out=[];let i=0;
    const cells=line=>line.trim().replace(/^\|/,"").replace(/\|$/,"").split("|");
    while(i<lines.length){const line=lines[i],trim=line.trim();if(!trim){i++;continue;}
      if(trim.startsWith("```")){const code=[];i++;while(i<lines.length&&!lines[i].trim().startsWith("```"))code.push(lines[i++]);i++;out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);continue;}
      const heading=trim.match(/^(#{1,6})\s+(.+)$/);if(heading){const n=heading[1].length;out.push(`<h${n}>${inline(heading[2],path)}</h${n}>`);i++;continue;}
      if(line.includes("|")&&i+1<lines.length&&/^\s*\|?[\s:|-]+\|\s*$/.test(lines[i+1])){const head=cells(line);i+=2;const rows=[];while(i<lines.length&&lines[i].includes("|")){rows.push(`<tr>${cells(lines[i++]).map(c=>`<td>${inline(c.trim(),path)}</td>`).join("")}</tr>`);}out.push(`<div class="table-wrap"><table><thead><tr>${head.map(c=>`<th>${inline(c.trim(),path)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`);continue;}
      if(/^[-*]\s+/.test(trim)){const items=[];while(i<lines.length&&/^\s*[-*]\s+/.test(lines[i]))items.push(`<li>${inline(lines[i++].trim().replace(/^[-*]\s+/,""),path)}</li>`);out.push(`<ul>${items.join("")}</ul>`);continue;}
      const ordered=trim.match(/^(\d+)\.\s+/);if(ordered){const items=[];while(i<lines.length&&/^\s*\d+\.\s+/.test(lines[i]))items.push(`<li>${inline(lines[i++].trim().replace(/^\d+\.\s+/,""),path)}</li>`);out.push(`<ol start="${Number(ordered[1])}">${items.join("")}</ol>`);continue;}
      if(trim.startsWith(">")){out.push(`<blockquote>${inline(trim.replace(/^>\s?/,""),path)}</blockquote>`);i++;continue;}
      out.push(`<p>${inline(line,path)}</p>`);i++;
    }return out.join("\n");
  }
  window.CFReader={render,safeLink};
  async function start(){try{const path=new URLSearchParams(location.search).get("path");if(!path)throw new Error("缺少资料路径，请从工序卡或因子详情打开。");const r=await fetch("/api/document?path="+encodeURIComponent(path));const data=await r.json();if(!r.ok)throw new Error(data.error);document.querySelector("#reader-title").textContent=data.text.match(/^#\s+(.+)$/m)?.[1]||data.path.split("/").pop();document.querySelector("#reader-source").textContent=`来源路径：${data.path} · SHA256 ${data.sha256.slice(0,16)}`;document.querySelector("#reader-kind").textContent=data.path.startsWith("upstream/")?"原始上游资料：保留原文。专属工艺说明优先核对，差异须保留记录。":"中文应用层解释：帮助理解，不替代原始因子或完整方法学。";const raw=document.querySelector("#reader-raw");raw.href="/evidence/"+encodeURI(data.path);raw.hidden=false;document.querySelector("#reader-content").innerHTML=render(data.text,data.path);}catch(error){document.querySelector("#reader-title").textContent="资料暂时无法打开";document.querySelector("#reader-content").textContent=error.message;}}
  start();
})();
