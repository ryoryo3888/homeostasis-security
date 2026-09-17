/* Structural protection only. No styles, content, or node relocation. */
(() => {
  'use strict';
  if (window.HomeostasisLayout) throw Error('Layout guard already installed');
  const version = document.querySelector('.hero') ? 'v2' : 'v1';
  const selectors = version === 'v1'
    ? ['main','.topbar','.brand-panel','.version-switch','.global-status','.turn-panel','.simulation-control','.control-name','.turn-buttons','.main-grid','.country-a','.earth-panel','.country-b','.event-panel']
    : ['main','.mast','.brand','.origin','.version-switch','.controls','.turn-operations','.turn-label','.control-heading','.turn-buttons','.event-now','.hero','.agent-stack','.earth-panel','.earth-system-field','.earth-wrap','.earth','.primary-kpis','.coordinator'];
  const locked = selectors.map(selector => {
    const matches = document.querySelectorAll(selector);
    if(matches.length !== 1) throw Error(`Missing/ambiguous LOCKED node: ${selector}`);
    return {selector,node:matches[0],parent:matches[0].parentNode};
  });
  const violations=[];
  const fail = reason => {
    violations.push(reason);
    throw new Error('LayoutContractError: '+reason);
  };
  const containsLocked = node => node instanceof Node && locked.some(x => node===x.node || node.contains(x.node));
  const moving = nodes => {
    for(const node of nodes) if(containsLocked(node)) fail('LOCKED node relocation/removal');
  };
  const replacing = node => {
    if(locked.some(x=>x.node!==node && node.contains(x.node))) fail('LOCKED descendant replacement');
  };
  const patch = (prototype,name,check) => {
    const original=prototype[name];
    Object.defineProperty(prototype,name,{value:function(...args){check(this,args);return Reflect.apply(original,this,args)},writable:false,configurable:false});
  };
  patch(Node.prototype,'appendChild',(_,args)=>moving([args[0]]));
  patch(Node.prototype,'insertBefore',(_,args)=>moving([args[0]]));
  patch(Node.prototype,'replaceChild',(_,args)=>moving(args.slice(0,2)));
  patch(Node.prototype,'removeChild',(_,args)=>moving([args[0]]));
  for(const prototype of [Element.prototype,Document.prototype,DocumentFragment.prototype]) {
    for(const name of ['append','prepend']) patch(prototype,name,(_,args)=>moving(args));
    patch(prototype,'replaceChildren',(self,args)=>{replacing(self);moving(args)});
  }
  for(const name of ['before','after']) patch(Element.prototype,name,(_,args)=>moving(args));
  patch(Element.prototype,'replaceWith',(self,args)=>{moving([self]);moving(args)});
  patch(Element.prototype,'remove',self=>moving([self]));
  patch(Element.prototype,'insertAdjacentElement',(_,args)=>moving([args[1]]));
  for(const [prototype,name,check] of [[Element.prototype,'innerHTML',replacing],[Element.prototype,'outerHTML',node=>moving([node])],[Node.prototype,'textContent',replacing]]) {
    const descriptor=Object.getOwnPropertyDescriptor(prototype,name);
    Object.defineProperty(prototype,name,{...descriptor,configurable:false,set(value){check(this);descriptor.set.call(this,value)}});
  }
  const order=locked.flatMap((a,i)=>locked.slice(i+1).filter(b=>a.parent===b.parent).map(b=>[a,b,Boolean(a.node.compareDocumentPosition(b.node)&Node.DOCUMENT_POSITION_FOLLOWING)]));
  const assertIntegrity=()=>{
    for(const item of locked) if(!item.node.isConnected || item.node.parentNode!==item.parent || document.querySelectorAll(item.selector).length!==1 || document.querySelector(item.selector)!==item.node) fail('LOCKED identity/parent: '+item.selector);
    for(const [a,b,before] of order) if(Boolean(a.node.compareDocumentPosition(b.node)&Node.DOCUMENT_POSITION_FOLLOWING)!==before) fail('LOCKED order');
    return true;
  };
  // Detect bypasses such as Range/exotic DOM operations, including move-then-restore.
  const observer=new MutationObserver(records=>{
    for(const record of records) for(const node of record.removedNodes) {
      if(containsLocked(node)){violations.push('Observed LOCKED removal');break;}
    }
    try{assertIntegrity()}catch(error){console.error(error.message)}
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});
  Object.defineProperty(window,'HomeostasisLayout',{value:Object.freeze({version,assertIntegrity,get violations(){return [...violations]},selectors:Object.freeze([...selectors])}),writable:false,configurable:false});
})();
