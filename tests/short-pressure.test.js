const test=require('node:test'),assert=require('node:assert/strict'),G=require('../public/squeeze-engine.js');
const now=Date.parse('2026-10-22T20:00:00Z'),date=d=>new Date(now-d*86400000).toISOString();
const bars=Array.from({length:70},(_,i)=>({time:date(70-i),open:1,high:1.15,low:.9,close:1,volume:100,vwap:1.01,complete:true}));
test('legacy browser scoring is removed, only visualization geometry remains',()=>assert.equal(G.analyze,undefined));
test('future, malformed, partial and not-yet-known bars are excluded',()=>assert.equal(G.validBars({bars:[{...bars[0],close:99},{...bars[0],complete:false},{...bars[0],time:date(-1)},{...bars[0],available_at:date(-1)}]},now).length,0));
test('insufficient observations never manufacture a zone',()=>assert.deepEqual(G.zones(bars.slice(0,3),1),[]));
test('shared zones conserve input volume under disclosed typical-price proxy',()=>{const z=G.zones(bars,1.1);assert.equal(z.length,3);assert.equal(z.reduce((v,x)=>v+x.volume_proxy,0),6000);assert(z.every(x=>x.note.includes('숏 진입가 아님')))});
