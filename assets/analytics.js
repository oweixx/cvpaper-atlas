'use strict';
let geoData, worldMap, geographyPromise, researchRows = [], countryRows = [];
const regionNames = new Intl.DisplayNames(['en'], {type:'region'});
const countryName = code => {try{return regionNames.of(code)||code;}catch{return code;}};
const percent = (n,d) => d ? 100*n/d : null;
const pct = value => value === null ? 'N/A' : value.toFixed(1)+'%';
const hasTopic = (p,t) => !t || p.topics.includes(t) || p.subtopics.includes(t);

function scope(prefix) {
  const from=Math.max(summary.min_year,Number($(prefix+'-from').value)||summary.min_year);
  const to=Math.min(summary.max_year,Number($(prefix+'-to').value)||summary.max_year);
  const venue=$(prefix+'-venue').value;
  return {from,to,venue,rows:papers.filter(p=>p.year>=from&&p.year<=to&&(!venue||p.venue===venue))};
}
function kpis(id,items){$(id).innerHTML=items.map(([label,value,note])=>`<div class="stat"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-foot">${esc(note)}</div></div>`).join('');}
function topicStats(rows,level='topics') {
  const counts=new Map();for(const p of rows)for(const t of p[level])counts.set(t,(counts.get(t)||0)+1);
  return [...counts].map(([name,count])=>({name,count,share:percent(count,rows.length)})).sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name));
}
function bars(id,items,attribute) {
  $(id).innerHTML=items.length ? items.map((t,i)=>`<button class="share-row" ${attribute}="${esc(t.name)}"><span class="share-label">${esc(t.name)}</span><span class="share-track"><i style="width:${t.share}%;background:hsl(${215+i*9},65%,53%)"></i></span><b>${pct(t.share)}</b><small>${fmt(t.count)}</small></button>`).join('') : '<div class="empty">No papers in this selection.</div>';
}
function lineChart(id,series,measure='share') {
  const points=series.filter(p=>p.value!==null),W=900,H=240,L=52,R=24,T=18,B=34;
  if(!points.length){$(id).innerHTML='<div class="empty">No data in this selection.</div>';return;}
  const ymax=Math.max(1,...points.map(p=>p.value))*1.1;
  const x=i=>series.length===1?(L+W-R)/2:L+(W-L-R)*i/(series.length-1),y=v=>H-B-v/ymax*(H-B-T);
  let svg='';for(let i=0;i<=4;i++){const v=ymax*i/4;svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#e8edf4"/><text x="${L-8}" y="${y(v)+3}" text-anchor="end" fill="#687b8d" font-size="10">${measure==='share'?v.toFixed(1)+'%':fmt(Math.round(v))}</text>`;}
  let path='',active=false;
  series.forEach((p,i)=>{if(p.value===null){active=false;return;}path+=`${active?'L':'M'}${x(i)},${y(p.value)} `;active=true;});
  svg+=`<path d="${path}" fill="none" stroke="#2563eb" stroke-width="2.5"/>`;
  series.forEach((p,i)=>{if(p.value!==null)svg+=`<circle cx="${x(i)}" cy="${y(p.value)}" r="4" fill="#2563eb"><title>${p.year}: ${measure==='share'?pct(p.value):fmt(p.value)} (${fmt(p.count)} / ${fmt(p.total)} papers)</title></circle>`;if(i%Math.max(1,Math.ceil(series.length/12))===0||i===series.length-1)svg+=`<text x="${x(i)}" y="${H-10}" text-anchor="middle" font-size="10" fill="#687b8d">${p.year}</text>`;});
  $(id).innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Annual ${measure==='share'?'topic share':'paper count'}; gaps mean no indexed papers">${svg}</svg>`;
}
function annualSeries(rows,topic,from,to,measure='share') {
  const totals=new Map(),matches=new Map();
  for(const p of rows){totals.set(p.year,(totals.get(p.year)||0)+1);if(hasTopic(p,topic))matches.set(p.year,(matches.get(p.year)||0)+1);}
  if(from>to)return [];
  return Array.from({length:to-from+1},(_,i)=>{const year=from+i,total=totals.get(year)||0,count=matches.get(year)||0;return {year,total,count,value:total?(measure==='count'?count:percent(count,total)):null};});
}
function exportStats(filename,columns,rows){
  const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
  const blob=new Blob(['\ufeff'+[columns,...rows].map(r=>r.map(quote).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function initializeAnalytics(){
  for(const prefix of ['research','world']){
    $(prefix+'-from').value=Math.max(2018,summary.min_year);$(prefix+'-to').value=summary.max_year;
    for(const suffix of ['from','to']){$(prefix+'-'+suffix).min=summary.min_year;$(prefix+'-'+suffix).max=summary.max_year;}
    $(prefix+'-venue').innerHTML='<option value="">All six venues</option>'+venues.map(v=>`<option>${v}</option>`).join('');
  }
  updateResearchOptions();
  $('world-topic').innerHTML='<option value="">All research topics</option><optgroup label="Research areas">'+summary.topics.map(t=>`<option>${esc(t)}</option>`).join('')+'</optgroup><optgroup label="Detailed topics">'+summary.subtopics.filter(t=>t!=='Other / Unclassified').map(t=>`<option>${esc(t)}</option>`).join('')+'</optgroup>';
  $('world-topic').value='3D Vision';
}
function updateResearchOptions(){const old=$('research-focus').value,level=$('research-level').value;$('research-focus').innerHTML=summary[level].map(t=>`<option>${esc(t)}</option>`).join('');$('research-focus').value=summary[level].includes(old)?old:level==='topics'?'3D Vision':summary.subtopics[0];}
function renderResearch(){
  if(!papers.length)return;
  const s=scope('research'),level=$('research-level').value,focus=$('research-focus').value,measure=$('research-measure').value;
  researchRows=topicStats(s.rows,level);const n=s.rows.filter(p=>hasTopic(p,focus)).length;
  const series=annualSeries(s.rows,focus,s.from,s.to,measure),observed=series.filter(p=>p.total);
  const change=observed.length>1?percent(observed.at(-1).count,observed.at(-1).total)-percent(observed[0].count,observed[0].total):null;
  kpis('research-kpis', [['Papers in period',fmt(s.rows.length),s.venue||'All six venues'],['Focus topic papers',fmt(n),focus],['Share of period papers',pct(percent(n,s.rows.length)),'Multi-label topic share'],['First-to-last share change',change===null?'N/A':(change>=0?'+':'')+change.toFixed(1)+' pp',observed.length>1?observed[0].year+' to '+observed.at(-1).year:'Two observed years needed']]);
  $('research-chart-title').textContent=focus+' over time';$('research-denominator').textContent='Denominator: all selected-venue papers in each year. Gaps mean no indexed papers; current-year data may be incomplete.';
  $('research-scope').textContent=s.from+'–'+s.to;
  lineChart('research-chart',series,measure);bars('research-bars',researchRows.slice(0,12),'data-research-topic');
  $('research-table').innerHTML=researchRows.map(t=>`<tr><td><button class="table-button" data-research-topic="${esc(t.name)}">${esc(t.name)}</button></td><td>${fmt(t.count)}</td><td>${pct(t.share)}</td></tr>`).join('')||'<tr><td colspan="3">No papers in this selection.</td></tr>';
}
async function loadGeography(){
  if(!geographyPromise)geographyPromise=Promise.all([getJSON('data/geography.json'),getJSON('data/world.json')]).then(([g,w])=>{geoData=g;worldMap=w;});
  try{await geographyPromise;}catch(e){geographyPromise=null;throw e;}
}
function summarizeCountries(rows,topic){
  const groups=new Map();let matched=0,mapped=0,authorships=0,known=0;
  for(const p of rows){const entry=geoData.papers[p.id];if(!entry)continue;matched++;authorships+=entry.authors;known+=entry.known_authors;if(Object.keys(entry.countries).length)mapped++;
    for(const [code,ids] of Object.entries(entry.countries)){
      if(!groups.has(code))groups.set(code,{code,rows:[],selected:[],authors:new Set()});const g=groups.get(code);g.rows.push(p);
      if(hasTopic(p,topic)){g.selected.push(p);for(const id of ids)g.authors.add(id);}
    }
  }
  const countries=[...groups.values()].map(g=>({...g,name:countryName(g.code),share:percent(g.selected.length,g.rows.length),leading:topicStats(g.rows)[0]})).sort((a,b)=>b.authors.size-a.authors.size||a.name.localeCompare(b.name));
  return {countries,matched,mapped,authorships,known};
}
function mapPath(feature){
  const polygons=feature.type==='Polygon'?[feature.coordinates]:feature.coordinates;
  return polygons.map(polygon=>polygon.map(ring=>ring.map(([lon,lat],i)=>`${i?'L':'M'}${((lon+180)*2.5).toFixed(2)},${((85-lat)*2.5).toFixed(2)}`).join(' ')+'Z').join(' ')).join(' ');
}
function drawWorld(countries){
  const metric=$('world-measure').value,selected=$('world-country').value;
  const value=g=>metric==='authors'?g.authors.size:metric==='papers'?g.selected.length:g.share;
  const index=new Map(countries.map(g=>[g.code,g])),max=Math.max(1,...countries.map(value));
  const shapes=worldMap.features.map(f=>{const g=index.get(f.code),v=g?value(g):0,ratio=metric==='share'?v/max:Math.log1p(v)/Math.log1p(max);const color=g&&g.selected.length?`hsl(215,72%,${91-ratio*53}%)`:'#e6ebf0';const label=`${countryName(f.code)}: ${g?(metric==='share'?pct(v):fmt(v)):'no indexed affiliations'}`;return `<path d="${mapPath(f)}" fill="${color}" stroke="${f.code===selected?'#e58b2b':'white'}" stroke-width="${f.code===selected?2.3:.6}" data-country="${f.code}" role="button" tabindex="0" aria-label="${esc(label)}" aria-pressed="${f.code===selected}"><title>${esc(label)}</title></path>`;}).join('');
  $('world-map').innerHTML=`<svg viewBox="0 0 900 385" role="group" aria-label="Affiliation country map; countries are also available in the table">${shapes}</svg>`;
  $('world-scale').textContent=(metric==='share'?'0–'+max.toFixed(1)+'%':'1–'+fmt(max)+' '+(metric==='authors'?'authors':'papers')+' · log color scale');
  $('world-map-caption').textContent=($('world-topic').value||'All topics')+' · '+$('world-measure').selectedOptions[0].text+'. Select a country for its research profile.';
}
function renderCountry(){
  const code=$('world-country').value,g=countryRows.find(g=>g.code===code),s=scope('world'),topic=$('world-topic').value;
  $('country-heading').textContent=g?g.name+' · research profile':'No country data';
  $('country-denominator').textContent=g?`Shares of all ${fmt(g.rows.length)} papers with an affiliation in ${g.name}, within the selected venue and period.`:'Try a broader period or another country.';
  bars('country-bars',g?topicStats(g.rows).slice(0,10):[],'data-world-topic');
  $('country-trend-title').textContent=(g?g.name+' · ':'')+(topic||'All topics');
  lineChart('country-chart',annualSeries(g?g.rows:[],topic,s.from,s.to));
  const coverage=annualSeries(s.rows,'',s.from,s.to).filter(y=>y.total).map(y=>{const mapped=s.rows.filter(p=>p.year===y.year&&Object.keys(geoData.papers[p.id]?.countries||{}).length).length;return `${y.year}: ${pct(percent(mapped,y.total))}`;});
  $('country-year-coverage').textContent='Country-data coverage among all selected-venue papers by year: '+coverage.join(' · ')+'. Coverage differences can affect trends.';
}
async function renderWorld(){
  if(!papers.length)return;
  try{await loadGeography();}catch(e){$('world-coverage').textContent='Affiliation data could not be loaded. '+e.message;return;}
  const s=scope('world'),topic=$('world-topic').value,stats=summarizeCountries(s.rows,topic);countryRows=stats.countries;
  $('world-coverage').textContent=`Affiliation coverage: ${fmt(stats.mapped)} / ${fmt(s.rows.length)} papers (${pct(percent(stats.mapped,s.rows.length))}) have a known country/region; ${fmt(s.rows.length-stats.mapped)} remain unknown. ${fmt(stats.matched)} papers matched the affiliation snapshot. Country available for ${pct(percent(stats.known,stats.authorships))} of returned authorships. ${geoData.collection_complete?'Collection requests completed.':'Partial source collection: API quota limited this snapshot; this is not a complete geographic census.'}`;
  $('world-coverage').classList.toggle('coverage-warning',!geoData.collection_complete);
  const previous=$('world-country').value;$('world-country').innerHTML=countryRows.map(g=>`<option value="${g.code}">${esc(g.name)}</option>`).join('');
  if(countryRows.some(g=>g.code===previous))$('world-country').value=previous;
  const authors=new Set(countryRows.flatMap(g=>[...g.authors])),mappedTopic=new Set(countryRows.flatMap(g=>g.selected.map(p=>p.id)));
  kpis('world-kpis',[['Countries / regions',fmt(countryRows.filter(g=>g.selected.length).length),'With matching topic papers'],['Unique author IDs',fmt(authors.size),'Known affiliations; deduplicated globally'],['Topic papers with country',fmt(mappedTopic.size),topic||'All research topics'],['Paper country coverage',pct(percent(stats.mapped,s.rows.length)),`${fmt(stats.mapped)} of ${fmt(s.rows.length)} papers`]]);
  $('world-table').innerHTML=countryRows.map(g=>`<tr><td><button class="table-button" data-country="${g.code}">${esc(g.name)}</button></td><td>${fmt(g.authors.size)}</td><td>${fmt(g.selected.length)}</td><td>${fmt(g.rows.length)}</td><td>${pct(g.share)}</td><td>${esc(g.leading?.name||'Unclassified')} <small>${pct(g.leading?.share??null)}</small></td></tr>`).join('')||'<tr><td colspan="6">No affiliation data in this selection.</td></tr>';
  drawWorld(countryRows);renderCountry();
}
for(const id of ['research-from','research-to','research-venue','research-focus','research-measure'])$(id).addEventListener('change',renderResearch);
$('research-level').onchange=()=>{if(summary){updateResearchOptions();renderResearch();}};
for(const id of ['world-from','world-to','world-venue','world-topic','world-measure'])$(id).addEventListener('change',renderWorld);
$('world-country').onchange=()=>{drawWorld(countryRows);renderCountry();};
$('research-papers').onclick=()=>{const s=scope('research'),focus=$('research-focus').value;resetFilters();$('year-from').value=s.from;$('year-to').value=s.to;document.querySelectorAll('#venue-filters input').forEach(e=>e.checked=!s.venue||e.value===s.venue);$($('research-level').value==='topics'?'topic':'subtopic').value=focus;showView('explore');filterPapers();};
$('research-export').onclick=()=>{const s=scope('research');exportStats('research_areas.csv',['topic','papers','share_percent','denominator_papers','from','to','venue'],researchRows.map(t=>[t.name,t.count,t.share,s.rows.length,s.from,s.to,s.venue||'all']));};
$('world-export').onclick=()=>{const s=scope('world');exportStats('country_research.csv',['country_code','country_name','unique_authors','topic_papers','all_area_papers','topic_share_percent','topic','from','to','venue'],countryRows.map(g=>[g.code,g.name,g.authors.size,g.selected.length,g.rows.length,g.share,$('world-topic').value||'all',s.from,s.to,s.venue||'all']));};
document.addEventListener('click',e=>{
  const r=e.target.closest('[data-research-topic]');if(r){$('research-focus').value=r.dataset.researchTopic;renderResearch();}
  const t=e.target.closest('[data-world-topic]');if(t){$('world-topic').value=t.dataset.worldTopic;renderWorld();}
  const c=e.target.closest('[data-country]');if(c){const code=c.dataset.country;if(countryRows.some(g=>g.code===code)){$('world-country').value=code;drawWorld(countryRows);renderCountry();}}
});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('path[data-country]')){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
