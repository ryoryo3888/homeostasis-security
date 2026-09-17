/* Future content enters named research slots; an empty manifest changes nothing. */
(() => {
  'use strict';
  const layout=window.HomeostasisLayout;
  if(!layout) throw Error('Content slots require the structural guard');
  const registry=Object.freeze({
    STORY_OBSERVATION:'.rn-intro',
    TURN_OBSERVATION:'.rn-turns',
    RESEARCH_FINDINGS:layout.version==='v1'?'.rn-findings':'.rn-say',
    EXPERIMENT_COMPARISON:layout.version==='v1'?'.rn-findings':'.rn-compare',
    DEEP_RESEARCH:'#rnD > details',
    NEXT_WORLD:'.rn-next'
  });
  const used=new Set();
  const validate=(slot,content)=>{
    if(!Object.hasOwn(registry,slot)) throw Error('Unknown content slot');
    if(!content || Object.getPrototypeOf(content)!==Object.prototype) throw Error('Content must be a plain record');
    if(Object.keys(content).some(k=>!['id','title','paragraphs','evidence'].includes(k))) throw Error('Unrecognized content field');
    if(typeof content.id!=='string' || !/^[a-z][a-z0-9-]{0,63}$/.test(content.id) || used.has(content.id)) throw Error('Invalid/duplicate content id');
    if(typeof content.title!=='string' || !content.title.trim() || content.title.length>200) throw Error('Invalid title');
    if(!Array.isArray(content.paragraphs) || !content.paragraphs.length || content.paragraphs.length>20 || content.paragraphs.some(p=>typeof p!=='string'||p.length>4000)) throw Error('Invalid paragraphs');
    if(typeof content.evidence!=='string' || !/^(?:docs|results)\/[a-zA-Z0-9_./-]+$/.test(content.evidence) || content.evidence.split('/').includes('..')) throw Error('Evidence must be a local docs/results path');
  };
  const addContent=(slot,content)=>{
    validate(slot,content);layout.assertIntegrity();
    const root=document.querySelector('#homeostasisResearchLayer');
    const targets=root?.querySelectorAll(registry[slot]);
    if(!targets || targets.length!==1) throw Error('Slot not ready/ambiguous: '+slot);
    const article=document.createElement('article');
    article.dataset.contentSlot=slot;article.dataset.contentId=content.id;
    const title=document.createElement('h3');title.textContent=content.title;article.append(title);
    for(const text of content.paragraphs){const p=document.createElement('p');p.textContent=text;article.append(p)}
    const link=document.createElement('a');link.href=content.evidence;link.textContent=content.evidence;article.append(link);
    targets[0].append(article);used.add(content.id);layout.assertIntegrity();
    return article;
  };
  Object.defineProperty(window,'HomeostasisContent',{value:Object.freeze({addContent,slots:Object.freeze(Object.keys(registry))}),writable:false,configurable:false});
  async function load(){
    const response=await fetch('ui/content.json');
    if(!response.ok) throw Error('Content manifest unavailable');
    const manifest=await response.json();
    if(Object.keys(manifest).sort().join(',')!=='schema_version,v1,v2' || manifest.schema_version!==1 || !Array.isArray(manifest[layout.version])) throw Error('Invalid content manifest');
    const records=manifest[layout.version];
    if(!records.length)return;
    // Validate every record before mutating the page.
    const ids=new Set();
    for(const item of records){if(Object.keys(item).sort().join(',')!=='content,slot')throw Error('Unknown manifest fields');validate(item.slot,item.content);if(ids.has(item.content.id))throw Error('Duplicate manifest id');ids.add(item.content.id)}
    await new Promise((resolve,reject)=>{
      const ready=()=>records.every(item=>document.querySelector('#homeostasisResearchLayer')?.querySelector(registry[item.slot]));
      if(ready())return resolve();
      const timer=setTimeout(()=>{observer.disconnect();reject(Error('Content slots not ready'))},10000);
      const observer=new MutationObserver(()=>{if(ready()){observer.disconnect();clearTimeout(timer);resolve()}});
      observer.observe(document.body,{childList:true,subtree:true});
    });
    for(const item of records)addContent(item.slot,item.content);
  }
  window.HomeostasisContentReady=load();
})();
