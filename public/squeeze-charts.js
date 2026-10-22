/* Shared price/volume visualization only. Scores come exclusively from the server. */
(function(){'use strict';const S=window.SqueezeGeometry,E=escapeHtml,n=(v,u='',d=2)=>S.finite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d})+(u?'('+u+')':''):'수집 대기';let period='1M',fx=null;
function price(v){return n(v,'달러',4)+(fx?.rate&&S.finite(v)?' <small>(약 '+n(v*fx.rate,'원',0)+')</small>':'')}
function candleChart(a){
 const lengths={'1D':1,'5D':5,'1M':21,'3M':63,'6M':126,'1Y':252},all=a.bars,bars=all.slice(-lengths[period]);
 if(!bars.length)return '<div class="sq-empty">유효한 OHLCV 일봉 데이터 없음</div>';
 const w=960,h=440,L=62,R=20,T=25,B=330,volTop=355,volBottom=410,span=w-L-R,step=span/bars.length;
 const min=Math.min(...bars.map(x=>x.low),a.metrics.support||Infinity),max=Math.max(...bars.map(x=>x.high),a.metrics.resistance||0),pad=(max-min)*.06||max*.02,lo=Math.max(0,min-pad),hi=max+pad,y=v=>T+(hi-v)/(hi-lo||1)*(B-T),x=i=>L+(i+.5)*step,maxV=Math.max(...bars.map(b=>b.volume),1);
 let out='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="선택 종목 '+E(period)+' 일봉 캔들·거래량 및 이동평균"><title>실제 IEX 일봉 · 분봉 아님</title>';
 for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4,yy=y(v);out+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+yy+'" y2="'+yy+'" stroke="#304766" stroke-width=".6"/><text x="3" y="'+(yy+4)+'" fill="#9EB0C8" font-size="11">'+v.toFixed(4)+'</text>'}
 const series=[['VWAP','#F4BE55',b=>b.vwap],['MA5','#65A7FF',(_,index)=>index>=4?all.slice(index-4,index+1).reduce((v,b)=>v+b.close,0)/5:null],['MA20','#FFB547',(_,index)=>index>=19?all.slice(index-19,index+1).reduce((v,b)=>v+b.close,0)/20:null],['MA60','#b39af5',(_,index)=>index>=59?all.slice(index-59,index+1).reduce((v,b)=>v+b.close,0)/60:null]];
 for(const [_,color,get] of series){let pts=bars.map((b,i)=>{let v=get(b,all.length-bars.length+i);return S.finite(v)?x(i).toFixed(1)+','+y(v).toFixed(1):null}).filter(Boolean);if(pts.length>1)out+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+color+'" stroke-width="1.5"/>'}
 for(const [v,color,label] of [[a.metrics.support,'#19D79B','지지'],[a.metrics.resistance,'#FF5268','저항']])if(S.finite(v))out+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="'+color+'" stroke-dasharray="5 5"/><text x="'+(L+4)+'" y="'+(y(v)-5)+'" fill="'+color+'" font-size="10">'+label+' '+v.toFixed(4)+'</text>';
 bars.forEach((b,i)=>{let color=b.close>=b.open?'#19D79B':'#FF5268',xx=x(i),bw=Math.min(12,step*.65);out+='<g><title>'+E(b.time)+' O '+b.open+' H '+b.high+' L '+b.low+' C '+b.close+' / 거래량 '+b.volume+'(주)</title><line x1="'+xx+'" x2="'+xx+'" y1="'+y(b.high)+'" y2="'+y(b.low)+'" stroke="'+color+'"/><rect x="'+(xx-bw/2)+'" y="'+Math.min(y(b.open),y(b.close))+'" width="'+bw+'" height="'+Math.max(1,Math.abs(y(b.open)-y(b.close)))+'" fill="'+color+'"/><rect x="'+(xx-bw/2)+'" y="'+(volBottom-b.volume/maxV*(volBottom-volTop))+'" width="'+bw+'" height="'+b.volume/maxV*(volBottom-volTop)+'" fill="'+color+'" opacity=".6"/></g>'});
 out+='<text x="'+L+'" y="437" fill="#9EB0C8" font-size="11">'+E(bars[0].time.slice(0,10))+'</text><text text-anchor="end" x="'+(w-R)+'" y="437" fill="#9EB0C8" font-size="11">'+E(bars.at(-1).time.slice(0,10))+'</text></svg>';
 return out;
}
function zoneMap(a,p){
 const z=S.zones(a.bars,p);if(!z.length)return '<p class="sq-fine">유효 일봉이 5개 이상 있어야 구간을 계산합니다.</p>';
 const colors=['#FF5268','#FFB547','#19D79B'],names=['1차 · 과거 저가 거래 구간','2차 · 중간 거래·저항 구간','3차 · 상단 저항·추가 반응 구간'];
 const lo=Math.min(z[0].from,p)*.96,hi=Math.max(z[2].to,p)*1.04,y=v=>15+(hi-v)/(hi-lo||1)*220;
 let svg='<svg viewBox="0 0 420 250" role="img" aria-label="가격·거래량 기반 3단계 추정 구간 맵">';
 z.forEach((q,i)=>{svg+='<rect x="80" y="'+y(q.to)+'" width="250" height="'+Math.max(1,y(q.from)-y(q.to))+'" fill="'+colors[i]+'" fill-opacity=".12" stroke="'+colors[i]+'"/><text x="90" y="'+((y(q.from)+y(q.to))/2)+'" font-size="12" fill="'+colors[i]+'">'+(i+1)+'차 추정 구간</text><text x="74" y="'+(y(q.to)+5)+'" text-anchor="end" font-size="11" fill="#9EB0C8">'+q.to.toFixed(4)+'</text>'});
 svg+='<line x1="65" x2="400" y1="'+y(p)+'" y2="'+y(p)+'" stroke="#FFD77D" stroke-dasharray="4 3"/><text x="338" y="'+(y(p)-5)+'" fill="#FFD77D" font-size="11">최근가</text></svg>';
 return svg+z.map((q,i)=>'<div class="sq-zone" style="border-color:'+colors[i]+'"><strong>'+names[i]+'</strong><p>'+price(q.from)+' ~ '+price(q.to)+'</p><p>하단까지 '+n(q.distance_pct,'%')+' · '+(q.breakout?'상단 위':'범위 내·하단 또는 아래')+' · 대표가격 거래량 근사 '+n(q.volume_proxy,'주',0)+'</p><p>최근 표본 가격 반응 '+n(q.reaction_pct,'%')+' · 거래량 변화 '+n(q.volume_change_pct,'%')+' · 표본 '+q.samples+'(일봉) · 신뢰도 '+q.confidence+'</p></div>').join('');
}
window.BHChart={render:(stock,analysis,p,exchange,asOf)=>{period=p;fx=exchange;const a={bars:S.validBars(stock,Date.parse(asOf)),metrics:{support:analysis.market?.support,resistance:analysis.market?.resistance}};return {price:candleChart(a),map:zoneMap(a,stock.price)}}};})();
