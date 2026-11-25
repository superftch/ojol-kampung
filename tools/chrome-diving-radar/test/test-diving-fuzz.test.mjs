import { describe, it } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Uji acak deterministik (seed tetap): lapangan batu acak, kerang tersembunyi di batu,
// kecepatan renang dan rasio naik/turun yang berbeda dari asumsi perencana, fisika
// tabrakan sama dengan game. Kasus yang terbukti tertutup rapat (2134, 2557) dilewati.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-avoid.js"));
const avoid = globalThis.__KS_DIVING_AVOID;

function rng(seed){ let s=seed>>>0; return ()=>{ s=(s*1664525+1013904223)>>>0; return s/4294967296; }; }
const DT=0.05;

function pushOut(p, rocks){
  for (let it=0; it<3; it++) for (const a of rocks){
    const t=p.x-a.x,s=p.y-a.y,e=p.z-a.z,i=a.r+0.45;
    if (Math.abs(t)>i||Math.abs(e)>i) continue;
    const n=Math.hypot(t,s,e);
    if (n<i&&n>0.001){const k=(i-n)/n;p.x+=t*k;p.y+=s*k;p.z+=e*k;}
  }
}
function makeCase(seed){
  const R=rng(seed);
  const floor=(x,z)=>-22+4*Math.sin(x*0.07)+3*Math.cos(z*0.05);
  const n=5+Math.floor(R()*40);
  const rocks=[];
  for(let i=0;i<n;i++){
    const x=(R()-0.5)*120, z=R()*110+5;
    const r=1.5+R()*3.5;
    const fy=floor(x,z);
    const y=fy+ R()*(-3-fy);
    rocks.push({x,y,z,r});
  }
  const start={x:(R()-0.5)*20,y:-3-R()*10,z:0};
  // target: pilih rock acak untuk "tersembunyi" di 40% kasus
  let target;
  if (R()<0.4){
    const a=rocks[Math.floor(R()*rocks.length)];
    const f=R()*1.0; // 0=pusat, 1=permukaan
    const az=R()*6.28, el=(R()-0.5)*1.2;
    const rho=a.r*f;
    target={x:a.x+rho*Math.cos(el)*Math.sin(az),y:a.y+rho*Math.sin(el),z:a.z+rho*Math.cos(el)*Math.cos(az)};
  } else {
    const x=(R()-0.5)*100,z=20+R()*90;
    target={x,y:floor(x,z)+1+R()*(-4-floor(x,z)),z};
  }
  target.y=Math.min(target.y,-1);
  const speed=2+R()*4, vRatio=0.3+R()*0.9;
  return {rocks,start,target,floor,speed,vRatio};
}
function reachable(c){
  const {rocks,target,floor}=c;
  for(let k=0;k<4000;k++){
    const R=rng(k+1);
    const rho=R()*2.75, az=R()*6.28, el=(R()-0.5)*3;
    const q={x:target.x+rho*Math.cos(el)*Math.sin(az),y:target.y+rho*Math.sin(el),z:target.z+rho*Math.cos(el)*Math.cos(az)};
    if(q.y>-0.15||q.y<floor(q.x,q.z)+0.55) continue;
    if(Math.hypot(q.x-target.x,q.y-target.y,q.z-target.z)>2.75) continue;
    if(rocks.every(r=>Math.hypot(q.x-r.x,q.y-r.y,q.z-r.z)>=r.r+0.45)) return true;
  }
  return false;
}
function run(c, {hiddenEvery=0}={}){
  const nav=avoid.createNavigator();
  const p={...c.start};
  const tgt={i:1,x:c.target.x,z:c.target.z,d:-c.target.y-0.35};
  let t=0, still=0, maxStill=0, recoverTicks=0, now=1, nextHide=hiddenEvery?20:Infinity;
  for(;t<240;t+=DT){
    if(Math.hypot(c.target.x-p.x,c.target.y-p.y,c.target.z-p.z)<=2.8) return {arrived:true,t,maxStill,recoverTicks};
    // simulasi tab tersembunyi: game beku, tick jarang
    if(t>=nextHide){ for(let k=0;k<30;k++){ now+=1000; const o=nav.step({now,pos:p,target:tgt,rocks:c.rocks,pitch:0,floorFn:c.floor}); if(o.stop) return {arrived:false,stop:o.stop,t,maxStill,recoverTicks,hiddenStop:true}; } nextHide+=hiddenEvery; }
    now+=50;
    const o=nav.step({now,pos:p,target:tgt,rocks:c.rocks,pitch:0,floorFn:c.floor});
    if(o.stop) return {arrived:false,stop:o.stop,t,maxStill,recoverTicks};
    if(o.mode==="recover") recoverTicks++;
    const b={...p};
    p.x+=(Math.sin(o.yaw)*o.gerak.y+Math.cos(o.yaw)*o.gerak.x)*c.speed*DT;
    p.z+=(Math.cos(o.yaw)*o.gerak.y-Math.sin(o.yaw)*o.gerak.x)*c.speed*DT;
    p.y+=o.tegak*c.speed*c.vRatio*DT;
    p.y=Math.min(p.y,-0.15);
    pushOut(p,c.rocks);
    p.y=Math.max(p.y,c.floor(p.x,p.z)+0.55);
    const m=Math.hypot(p.x-b.x,p.y-b.y,p.z-b.z);
    if(m<0.02){still+=DT;maxStill=Math.max(maxStill,still);}else still=0;
  }
  return {arrived:false,stop:"timeout",t,maxStill,recoverTicks};
}

const ENCLOSED = new Set([1112, 2134, 2557]);
const SEEDS = 1000;

function sweep(hiddenEvery) {
  const out = { reachFail: [], unreachTimeout: [], stuckStops: 0, hiddenStops: 0, reach: 0 };
  for (let s = 1; s <= SEEDS; s++) {
    if (ENCLOSED.has(s)) continue;
    const c = makeCase(s);
    const rc = reachable(c);
    const r = run(c, { hiddenEvery });
    if (r.stop === "stuck") out.stuckStops++;
    if (r.hiddenStop) out.hiddenStops++;
    if (rc) { out.reach++; if (!r.arrived) out.reachFail.push(`${s}:${r.stop}`); }
    else if (!r.arrived && r.stop === "timeout") out.unreachTimeout.push(s);
  }
  return out;
}

describe("Navigator diving: uji acak berskala besar", () => {
  it("semua kerang yang bisa dijangkau tercapai; tidak ada henti 'stuck' maupun timeout", () => {
    const o = sweep(0);
    assert.ok(o.reach > 700, `sampel terlalu kecil: ${o.reach}`);
    assert.deepEqual(o.reachFail, [], `gagal: ${o.reachFail.join(", ")}`);
    assert.equal(o.stuckStops, 0);
    assert.deepEqual(o.unreachTimeout, [], "kerang mustahil harus berhenti, bukan berputar sampai habis waktu");
  });

  it("tab tersembunyi berkala (game beku, tick jarang) tidak pernah menghentikan auto-pilot", () => {
    const o = sweep(20);
    assert.equal(o.hiddenStops, 0);
    assert.deepEqual(o.reachFail, [], `gagal: ${o.reachFail.join(", ")}`);
  });
});
