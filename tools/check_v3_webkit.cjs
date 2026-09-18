// Optional cross-engine regression check; requires Playwright + WebKit. No remote requests.
const {webkit}=require('playwright');
const http=require('http'),fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const root=path.resolve(__dirname,'..'), blocked=[];
 const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname;
  if(name.startsWith('/ui/v3/')){blocked.push(name);res.writeHead(503);return res.end('Simulated separate asset failure');}
  const file=path.join(root,name);
  try{res.setHeader('Content-Type',file.endsWith('.html')?'text/html':file.endsWith('.png')?'image/png':'text/plain');res.end(fs.readFileSync(file));}catch{res.writeHead(404);res.end();}
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;
 try{
  browser=await webkit.launch({headless:true});
  for(const [width,height] of [[1440,1000],[1024,1366],[768,1024],[390,844]]){
   const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(`http://127.0.0.1:${server.address().port}/dashboard_v3.html?utm_source=chatgpt.com`);
   await page.waitForFunction(()=>window.V3Candidate?.ready);
   const result=await page.evaluate(()=>{
    const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
    return {earth:rect('#v3-earth'),image:rect('#v3-earth img'),aurora:rect('.v3-aurora'),nodes:document.querySelectorAll('.state-node').length,routes:document.querySelectorAll('.route').length,error:!document.querySelector('#load-error').hidden,animation:getComputedStyle(document.querySelector('.aurora-ribbon')).animationName,overflow:document.documentElement.scrollWidth>innerWidth};
   });
   assert.equal(result.nodes,8);assert.equal(result.routes,18);assert(!result.error&&!result.overflow);assert.equal(result.animation,'none');
   for(const item of [result.image,result.aurora])for(const k of ['x','y','w','h'])assert(Math.abs(item[k]-result.earth[k])<1);
   assert(Math.abs(result.earth.w-result.earth.h)<1);assert.deepEqual(errors,[]);
   await page.screenshot({path:path.join(root,`.artifacts/layout/v3-webkit-${width}.png`)});
   await page.emulateMedia({reducedMotion:'no-preference'});
   assert.equal(await page.locator('.aurora-ribbon').first().evaluate(n=>getComputedStyle(n).animationName),'aurora-drift');
   const motion=()=>page.locator('.aurora-ribbon').last().evaluate(n=>({transform:getComputedStyle(n).transform,opacity:getComputedStyle(n).opacity}));
   const before=await motion();await page.waitForTimeout(900);const after=await motion();
   assert.notEqual(before.transform,after.transform);assert.notEqual(before.opacity,after.opacity);
   console.log('WEBKIT PASS',width,height,JSON.stringify(result));await page.close();
  }
  assert.deepEqual(blocked,[]);console.log('No separate CSS, script or baseline requests required.');
 }finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
