(async () => {
  const guard=window.HomeostasisLayout, content=window.HomeostasisContent;
  if(!guard || !content)throw Error('Missing protection runtime');
  await window.HomeostasisContentReady;
  if(guard.violations.length)throw Error('Runtime relocation detected during normal loading/interaction');
  const earth=document.querySelector('.earth-panel'), world=earth.parentElement;
  const attempts=[
    ()=>document.body.append(earth), ()=>document.body.prepend(earth),
    ()=>document.body.appendChild(earth), ()=>document.body.insertBefore(earth,document.body.firstChild),
    ()=>world.prepend(earth), ()=>earth.before(world), ()=>earth.after(world),
    ()=>earth.remove(), ()=>world.removeChild(earth),
    ()=>world.replaceChild(document.createElement('div'),earth),
    ()=>earth.replaceWith(document.createElement('div')),
    ()=>document.body.replaceChildren(), ()=>{world.innerHTML=''},
    ()=>{world.outerHTML=''}, ()=>{document.body.textContent=''},
    ()=>document.body.insertAdjacentElement('beforeend',earth),
    ()=>document.createElement('div').append(world)
  ];
  let checked=0;
  const rejected=fn=>{let caught=false;try{fn()}catch(error){caught=true}if(!caught)throw Error('Unsafe operation was accepted');checked++};
  for(const attack of attempts){rejected(attack);guard.assertIntegrity()}
  const sample={id:'contract-fixture',title:'<script>not executable</script>',paragraphs:['Offline contract fixture'],evidence:'docs/architecture/HOMEOSTASIS_VISUAL_CONSTITUTION.md'};
  rejected(()=>content.addContent('EARTH',sample));
  rejected(()=>content.addContent('NEXT_WORLD',{...sample,html:'<script></script>'}));
  rejected(()=>content.addContent('NEXT_WORLD',{...sample,evidence:'https://example.invalid'}));
  rejected(()=>content.addContent('NEXT_WORLD',{...sample,evidence:'docs/../private'}));
  const bounds=()=>guard.selectors.filter(s=>s!=='main').map(s=>{const r=document.querySelector(s).getBoundingClientRect();return [r.x,r.y+scrollY,r.width,r.height]});
  const before=JSON.stringify(bounds());
  const article=content.addContent('NEXT_WORLD',sample);
  if(article.querySelector('script') || article.querySelector('h3').textContent!==sample.title)throw Error('Unsafe content parsing');
  if(JSON.stringify(bounds())!==before)throw Error('Content altered the locked frame');
  rejected(()=>content.addContent('NEXT_WORLD',sample));
  article.remove();guard.assertIntegrity();
  // Same-parent move followed by restoration must also leave evidence.
  const parent=earth.parentNode,next=earth.nextSibling;
  const range=document.createRange();range.selectNode(earth);
  const fragment=range.extractContents();
  await new Promise(resolve=>setTimeout(resolve,0));
  if(!guard.violations.some(x=>x.includes('Observed LOCKED removal')))throw Error('Range bypass not detected');
  rejected(()=>guard.assertIntegrity());
  return {rejected:checked,range_bypass_detected:true,valid_slot_preserves_frame:true};
})()
