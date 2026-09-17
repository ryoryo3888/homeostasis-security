(config => {
  const one = selector => {
    const nodes = document.querySelectorAll(selector);
    if (nodes.length !== 1) throw Error(`Expected one ${selector}, found ${nodes.length}`);
    return nodes[0];
  };
  // Include hidden evidence layers; scripts/styles are not displayed copy.
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  let rendered='',textNode;
  while(textNode=walker.nextNode()) if(!textNode.parentElement.closest('script,style')) rendered+=textNode.textContent;
  if(/(?:[0-9０-９〇○一二三四五六七八九十]+\s*秒で(?:理解|分かる|わかる)|読み方|初見|初心者|研究者向け|まず.{0,30}(?:見て|見よう|読む)|詳しく知りたい人)/.test(rendered)) throw Error('Viewer-directive meta copy');
  if(one('.rn-intro h3').textContent!=='世界の構成' || document.querySelector('.rn-intro aside')) throw Error('World composition copy contract');
  const research=one('#homeostasisResearchLayer').textContent;
  if(!research.includes(document.querySelector('.hero')?'局所危機から地球規模の回復へ':'この8ターンで何が起きた？')) throw Error('Research heading lost');
  const rect = node => {
    const r = node.getBoundingClientRect();
    return {x:r.x + scrollX, y:r.y + scrollY, width:r.width, height:r.height};
  };
  const path = node => {
    if (!node || node === document) return '';
    const siblings = [...node.parentElement?.children || []].filter(n => n.tagName === node.tagName);
    return `${node.tagName.toLowerCase()}${node.id ? '#' + node.id : ''}.${[...node.classList].join('.')}:${siblings.indexOf(node)}`;
  };
  const styleKeys = ['display','position','gridTemplateColumns','gridTemplateRows','gap','padding','margin','fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','color','backgroundColor','borderRadius','transform','overflowX'];
  const nodes = Object.fromEntries(config.inspect.map(selector => {
    const node = one(selector), style = getComputedStyle(node);
    return [selector, {parent:path(node.parentElement), tag:node.tagName, classes:node.className,
      bounds:rect(node), styles:Object.fromEntries(styleKeys.map(k=>[k,style[k]])),
      text:node.textContent.trim(), before:getComputedStyle(node,'::before').content, after:getComputedStyle(node,'::after').content}];
  }));
  for (const [child,parent] of Object.entries(config.parents)) {
    if (one(child).parentElement !== one(parent)) throw Error(`Parent contract: ${child} -> ${parent}`);
  }
  const frame = config.frame.map(one);
  for (let i=1;i<frame.length;i++) {
    if (!(frame[i-1].compareDocumentPosition(frame[i]) & Node.DOCUMENT_POSITION_FOLLOWING)) throw Error('Frame order');
    const a=rect(frame[i-1]),b=rect(frame[i]);
    if (a.y+a.height > b.y+.5) throw Error('Frame overlap');
  }
  const earth=one('.earth-panel'), world=frame.at(-1), narrative=one('#homeostasisResearchLayer');
  if (!world.contains(earth) || !(world.compareDocumentPosition(narrative)&Node.DOCUMENT_POSITION_FOLLOWING)) throw Error('Earth/narrative order');
  if (rect(world).y+rect(world).height > rect(narrative).y+.5) throw Error('Narrative intrudes into world');
  const recovery=document.querySelector('.rn-recovery');
  if(recovery){
    const flow=one('.rn-chain'), metrics=one('.rn-recovery>.rn-metrics'), cards=[...metrics.querySelectorAll('.rn-metric')];
    const a=rect(flow),b=rect(metrics);
    if(cards.length!==3 || flow.parentElement!==recovery || metrics.parentElement!==recovery) throw Error('Recovery composition');
    if(innerWidth>760 && (Math.abs(a.y-b.y)>.5 || Math.abs(a.width-b.width)>.5 || Math.abs(a.height-b.height)>.5)) throw Error('Recovery columns');
    if(innerWidth>760 && cards.some(c=>Math.abs(rect(c).height-a.height/3)>.5)) throw Error('Equal metric rows');
    if(innerWidth<=760 && b.y<a.y+a.height-.5) throw Error('Stacked recovery');
  }
  const heading=document.querySelector('.control-name,.control-heading'), hs=getComputedStyle(heading);
  for(const [k,v] of Object.entries({fontSize:'17px',fontWeight:'800',letterSpacing:'1.36px',lineHeight:'26.35px',color:'rgb(103, 232, 249)',transform:'none'})) if(hs[k]!==v) throw Error(`Typography ${k}: ${hs[k]}`);
  return {nodes,turn:one(config.turn_selector).textContent.trim(), mainOrder:[...one('main').children].filter(n=>!['SCRIPT','STYLE','LINK'].includes(n.tagName)).map(path)};
})
