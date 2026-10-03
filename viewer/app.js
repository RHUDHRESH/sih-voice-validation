'use strict';
const $ = id => document.getElementById(id);
let data, current, cursor = 0, duration = 1, playing = false, lastFrame = 0;
const fmt = n => Number(n).toLocaleString('en-US');
const important = new Set(['ORACLE_TRIGGER','ACCEPT','ABORT','COMPLETE','MUTE','UNMUTE','TRIGGER_REJECTED','TRIGGER_IGNORED','ORACLE_ENDPOINT','PACKET_DROPPED']);
function stop(){playing=false; $('play').textContent='Play replay';}
function choose(){
  stop(); cursor=0; current=data.cases.find(c=>c.config.scenario_id===$('scenario').value);
  duration=Math.max(...current.config.utterances.map(u=>u.command_end),...Object.values(current.outputs).flatMap(o=>[...o.telemetry.map(t=>Number(t.at_sample)),...o.events.map(e=>Number(e.at_sample))]));
  $('timeline').max=String(duration); $('description').textContent=current.config.description;
  $('duration').textContent=(duration/16000).toFixed(3)+' s';
  $('provenance').textContent=`Paired PCM SHA-256: ${current.outputs.naive.metrics.input_sha256} · seed ${current.config.seed} · ${data.cases.length} scenarios · expected-behavior suite ${data.summary_status.toUpperCase()}`;
  for(const policy of ['naive','buffered']){
    const m=current.outputs[policy].metrics, commands=m.commands, good=commands.filter(c=>c.command_integrity_status==='pass').length;
    const verdict=$(policy+'-final'); verdict.textContent=good===commands.length?'Complete command preserved':`${good} of ${commands.length} complete commands`;
    verdict.className='verdict '+(good===commands.length?'good':'bad');
    $(policy+'-loss').textContent=commands.map(c=>`${commands.length>1?c.utterance_id+': ':''}${fmt(c.onset_lost_samples)} onset samples missing (${c.onset_lost_ms.toFixed(2)} ms)`).join(' · ');
    $(policy+'-reason').textContent=`Last handoff: ${m.handoff_status.toUpperCase()}${m.reason?' · '+m.reason:''} · PCM ring ${fmt(m.ring_pcm_payload_bytes)} B (not total application RAM)`;
  }
  render();
}
function atNow(output){
  const t=output.telemetry.filter(r=>Number(r.at_sample)<=cursor).at(-1);
  const s=output.metrics.sessions.filter(s=>s.requested_at<=cursor).at(-1);
  let state='LISTENING';
  if(s) state=s.finished_at!==null && s.finished_at<=cursor?s.state:(s.accepted_at!==null&&s.accepted_at<=cursor?'STREAMING':'REQUESTED');
  const mute=output.events.filter(e=>Number(e.at_sample)<=cursor&&(e.event==='MUTE'||e.event==='UNMUTE')).at(-1);
  if(mute?.event==='MUTE') state='MUTED';
  const accepted=output.packets.filter(p=>p.disposition==='ACCEPTED'&&Number(p.at_sample)<=cursor&&p.session_id===s?.session_id);
  const received=accepted.reduce((sum,p)=>sum+Number(p.sample_count),0);
  return {t,s,state,received};
}
function draw(policy, view){
  const canvas=$(policy+'-canvas'), ctx=canvas.getContext('2d'), W=1080, H=330, left=205, right=1040, color=policy==='naive'?'#c36522':'#2563eb';
  ctx.clearRect(0,0,W,H); ctx.font='22px system-ui';
  const x=sample=>left+sample/duration*(right-left);
  for(let i=0;i<=4;i++){const xx=left+(right-left)*i/4;ctx.strokeStyle='#e0e7ea';ctx.beginPath();ctx.moveTo(xx,35);ctx.lineTo(xx,272);ctx.stroke();ctx.fillStyle='#64757e';ctx.font='18px system-ui';ctx.fillText((duration/16000*i/4).toFixed(2)+' s',xx-25,306);}
  const bar=(label,y,start,end,fill)=>{ctx.fillStyle='#52656f';ctx.font='21px system-ui';ctx.fillText(label,18,y+20);if(start!==null&&end>start){ctx.fillStyle=fill;ctx.fillRect(x(start),y,Math.max(1,x(end)-x(start)),28);}};
  bar('Command',57,null,null,'');for(const u of current.config.utterances){ctx.fillStyle='#163c37';ctx.fillRect(x(u.command_start),57,x(u.command_end)-x(u.command_start),28);}
  bar('Ring retained',117,view.t?Number(view.t.ring_oldest):null,view.t?Number(view.t.ring_end):null,'#aebfc6');
  bar('Session received',177,view.s?.requested_start??null,view.s?view.s.requested_start+view.received:null,color);
  const events=current.outputs[policy].events.filter(e=>Number(e.at_sample)<=cursor&&['ORACLE_TRIGGER','ACCEPT','ABORT','MUTE','COMPLETE'].includes(e.event));
  for(const e of events){const xx=x(Number(e.at_sample));ctx.fillStyle=e.event==='ABORT'||e.event==='MUTE'?'#a82222':color;ctx.beginPath();ctx.arc(xx,241,6,0,Math.PI*2);ctx.fill();}
  const xx=x(cursor);ctx.strokeStyle='#162f3c';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(xx,30);ctx.lineTo(xx,267);ctx.stroke();ctx.lineWidth=1;
  ctx.fillStyle='#52656f';ctx.font='19px system-ui';ctx.fillText('Events',18,248);
}
function render(){
  $('timeline').value=String(Math.round(cursor));$('clock').textContent=(cursor/16000).toFixed(3)+' s · sample '+fmt(Math.round(cursor));
  for(const policy of ['naive','buffered']){
    const output=current.outputs[policy], v=atNow(output);$(policy+'-state').textContent=v.state;
    $(policy+'-ring').textContent=fmt(v.t?.ring_retained_samples??0)+' / '+fmt(current.config.ring_samples);
    $(policy+'-backlog').textContent=fmt(v.t?.unacknowledged_backlog_samples??0)+' samples';
    $(policy+'-received').textContent=fmt(v.received)+' samples';
    const events=output.events.filter(e=>Number(e.at_sample)<=cursor&&important.has(e.event)).slice(-5);
    const list=$(policy+'-events');list.replaceChildren();
    if(!events.length){const li=document.createElement('li');li.textContent='Waiting for the first recorded lifecycle event';list.append(li);}
    for(const e of events){const li=document.createElement('li'),time=document.createElement('time'),label=document.createElement('span');time.textContent=(Number(e.at_sample)/16000).toFixed(3)+' s';label.textContent=e.event+(e.detail?' · '+e.detail:'');if(e.event==='ABORT'||e.event==='TRIGGER_REJECTED')li.className='critical';li.append(time,label);list.append(li);}
    draw(policy,v);
  }
}
function animate(ts){if(playing){if(lastFrame)cursor=Math.min(duration,cursor+(ts-lastFrame)*16*Number($('speed').value));render();if(cursor>=duration)stop();}lastFrame=ts;requestAnimationFrame(animate);}
$('play').addEventListener('click',()=>{if(playing){stop();}else{if(cursor>=duration)cursor=0;playing=true;lastFrame=0;$('play').textContent='Pause replay';}});
$('reset').addEventListener('click',()=>{stop();cursor=0;render();});
$('end').addEventListener('click',()=>{stop();cursor=duration;render();});
$('next').addEventListener('click',()=>{stop();const times=Object.values(current.outputs).flatMap(o=>o.events.filter(e=>important.has(e.event)).map(e=>Number(e.at_sample))).filter(t=>t>cursor);cursor=times.length?Math.min(...times):duration;render();});
$('timeline').addEventListener('input',()=>{stop();cursor=Number($('timeline').value);render();});
$('scenario').addEventListener('change',choose);
fetch('/api/data').then(r=>{if(!r.ok)throw Error('Result bundle unavailable');return r.json();}).then(value=>{data=value;const select=$('scenario');select.replaceChildren();for(const c of data.cases){const o=document.createElement('option');o.value=c.config.scenario_id;o.textContent=c.config.scenario_id.replaceAll('_',' ');select.append(o);}for(const id of ['scenario','play','reset','next','end','timeline'])$(id).disabled=false;choose();requestAnimationFrame(animate);}).catch(error=>{$('error').hidden=false;$('error').textContent='Could not load saved results: '+error.message;});
