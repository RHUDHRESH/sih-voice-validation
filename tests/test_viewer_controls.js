/* Isolated DOM/control-logic checks. NOT real-browser visual or accessibility QA. */
'use strict';
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm'), assert=require('node:assert/strict');
const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.className='';this.disabled=true;this.hidden=true;}
  addEventListener(type, fn){this.listeners[type]=fn;}
  append(...nodes){this.children.push(...nodes);if(this.tag==='select'&&!this.value&&nodes.length)this.value=nodes[0].value;}
  replaceChildren(...nodes){this.children=[];if(this.tag==='select')this.value='';this.append(...nodes);}
  getContext(){return new Proxy({}, {get:(object,key)=>key in object?object[key]:(()=>{}),set:(object,key,value)=>(object[key]=value,true)});}
}
const ids=['scenario','description','play','reset','next','end','speed','clock','timeline','duration','provenance','error'];
for(const policy of ['naive','buffered'])for(const suffix of ['state','canvas','ring','backlog','received','final','loss','reason','events'])ids.push(policy+'-'+suffix);
const elements=Object.fromEntries(ids.map(id=>[id,new Element(['scenario','speed'].includes(id)?'select':'div')]));elements.speed.value='1';
const frames=[];
const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)},
  fetch:async()=>({ok:true,json:async()=>fixture}),requestAnimationFrame:fn=>frames.push(fn),console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../viewer/app.js'),'utf8'), context);
const event=(id,type='click')=>{assert.equal(typeof elements[id].listeners[type],'function');elements[id].listeners[type]();};
const select=name=>{elements.scenario.value=name;event('scenario','change');};
const checks=[];
function check(label, fn){fn();checks.push({check:label,status:'pass'});}
setImmediate(()=>{
  check('loads all recorded scenarios and synthetic label data',()=>{assert.equal(elements.scenario.children.length,fixture.cases.length);assert.equal(elements.play.disabled,false);assert.equal(elements['naive-state'].textContent,'LISTENING');});
  check('golden final contrasts actual recorded command integrity',()=>{event('end');assert.match(elements['naive-final'].textContent,/0 of 1/);assert.match(elements['naive-loss'].textContent,/3,200/);assert.equal(elements['buffered-final'].textContent,'Complete command preserved');assert.match(elements['buffered-loss'].textContent,/^0 onset/);});
  check('restart and next-event use the same source clock',()=>{event('reset');assert.match(elements.clock.textContent,/sample 0$/);event('next');assert.match(elements.clock.textContent,/19,200/);assert.equal(elements['naive-state'].textContent,'REQUESTED');assert.equal(elements['buffered-state'].textContent,'REQUESTED');});
  check('scrub updates panels and pauses playback',()=>{elements.timeline.value='24000';event('timeline','input');assert.match(elements.clock.textContent,/24,000/);assert.equal(elements['buffered-state'].textContent,'STREAMING');assert.equal(elements.play.textContent,'Play replay');});
  check('play speed and pause advance deterministically in isolated clock',()=>{event('reset');elements.speed.value='4';event('play');frames.shift()(1);frames.shift()(101);assert.match(elements.clock.textContent,/6,400/);event('play');const before=elements.clock.textContent;frames.shift()(201);assert.equal(elements.clock.textContent,before);assert.equal(elements.play.textContent,'Play replay');});
  check('overflow shows explicit abort rather than success',()=>{select('acceptance_capacity_plus_one');event('end');assert.equal(elements['buffered-state'].textContent,'ABORTED');assert.match(elements['buffered-reason'].textContent,/BUFFER_OVERFLOW_PENDING/);assert.match(elements['buffered-final'].textContent,/0 of 1/);});
  check('multi-command resume does not erase prior command failure',()=>{select('mute_then_fresh_session');event('end');assert.match(elements['buffered-final'].textContent,/1 of 2/);assert.match(elements['buffered-reason'].textContent,/COMPLETE/);});
  check('every scenario final verdict matches artifact aggregate',()=>{for(const c of fixture.cases){select(c.config.scenario_id);event('end');for(const policy of ['naive','buffered']){const good=c.outputs[policy].metrics.command_integrity_status==='pass';assert.equal(elements[policy+'-final'].className,good?'verdict good':'verdict bad');}}});
  console.log(JSON.stringify({status:'pass',scope:'isolated DOM/control logic; not a browser rendering test',node:process.version,checks},null,2));
});
