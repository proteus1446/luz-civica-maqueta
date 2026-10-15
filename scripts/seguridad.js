/* Luz Cívica: casos y recursos, sin inferencia causal. */
(async function(){
  'use strict';
  const $=id=>document.getElementById(id);
  const fmt=(n,d=0)=>n==null||!Number.isFinite(+n)?'Sin dato':(+n).toLocaleString('es-CL',{maximumFractionDigits:d});
  const fields={camaras:'Cámaras',drones:'Drones',autos:'Autos',camionetas:'Camionetas',motos:'Motos',bicicletas:'Bicicletas',inspectores:'Guardias e inspectores',profesionales:'Profesionales de seguridad',casetas:'Casetas'};
  const norm=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  try{
    if(!window.d3)throw new Error('No se pudo cargar el motor del mapa.');
    const [data,geo]=await Promise.all(['data/seguridad_comunal.json','data/seguridad_comunas.geojson'].map(async u=>{const r=await fetch(u);if(!r.ok)throw new Error('No se pudo cargar '+u);return r.json()}));
    const params=new URLSearchParams(location.search),requested=params.get('comuna');
    const initial=Object.keys(data.comunas).find(k=>k===requested||norm(data.comunas[k].clave_portal)===norm(requested||'')||norm(data.comunas[k].nombre)===norm(requested||''))||'13120';
    const state={cut:initial,year:data.anios.includes(+params.get('anio'))?+params.get('anio'):2025,region:data.comunas[initial].region,delito:-1,mode:'nivel',resource:'camaras'};
    const options=(id,rows)=>{const s=$(id);s.replaceChildren(...rows.map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o}));s.disabled=false};
    const regions=[...new Set(Object.values(data.comunas).map(c=>c.region))].sort();
    options('region',[['all','Chile continental'],...regions.map(r=>[r,Object.values(data.comunas).find(c=>c.region===r).nombre_region])]);
    options('anio',[...data.anios].reverse().map(y=>[y,y]));
    options('delito',[[-1,'Suma de las 30 categorías del GitHub'],...data.delitos.map((d,i)=>[i,d])]);
    options('resource',Object.entries(fields));
    const record=(cut,y)=>data.comunas[cut]?.anios[String(y)];
    const count=(cut,y)=>{const r=record(cut,y);return !r?null:state.delito===-1?r.casos:r.categorias[state.delito]};
    const rate=(cut,y)=>{const r=record(cut,y),n=count(cut,y);return r?.poblacion>0&&n!=null?n/r.poblacion*100000:null};
    const delta=(cut,y)=>{const v=rate(cut,y),p=rate(cut,y-1);return v==null||!(p>0)?null:(v/p-1)*100};
    const resource=(cut,y,key)=>record(cut,y)?.seguridad?.[key]??null;
    const optionComunas=()=>{options('comuna',Object.entries(data.comunas).filter(([,c])=>state.region==='all'||c.region===state.region).sort((a,b)=>a[1].nombre.localeCompare(b[1].nombre,'es')).map(([k,c])=>[k,c.nombre]));$('comuna').value=state.cut};
    function sync(){
      for(const id of ['region','anio','delito'])$(id).value=id==='anio'?state.year:state[id];
      const url=new URL(location.href);url.searchParams.set('comuna',data.comunas[state.cut].clave_portal);url.searchParams.set('anio',state.year);history.replaceState(null,'',url);
      const query='?comuna='+encodeURIComponent(data.comunas[state.cut].clave_portal)+'&anio='+state.year;
      $('volver').href='panel_comunal.html'+query;$('perfil').href='maqueta_perfil.html'+query;
    }
    function details(){
      const c=data.comunas[state.cut],r=record(state.cut,state.year),v=rate(state.cut,state.year),change=delta(state.cut,state.year);
      $('detail-title').textContent=c.nombre;$('detail-region').textContent=c.nombre_region;$('detail-period').textContent=state.year+' · '+(state.delito===-1?'Selección de 30 categorías':data.delitos[state.delito]);
      $('rate').textContent=fmt(v,1);$('count').textContent=fmt(count(state.cut,state.year));$('population').textContent=fmt(r?.poblacion);
      $('change').textContent=change==null?'Sin base para calcular cambio porcentual anual':`La tasa ${change<0?'bajó':'subió'} ${fmt(Math.abs(change),1)}% frente a ${state.year-1}.`;
      $('scope').textContent=state.delito===-1?'Suma de categorías del GitHub: incluye superposición en armas y excluye otras categorías CEAD. No es un total oficial.':'Casos registrados en esta categoría. No equivale a víctimas únicas ni a todos los hechos ocurridos.';
      $('resource-year').textContent='SINIM · mismo año seleccionado: '+state.year;
      $('resources').replaceChildren(...Object.entries(fields).slice(0,7).map(([key,label])=>{const box=document.createElement('div');box.className='resource-item';const n=document.createElement('strong');n.textContent=fmt(resource(state.cut,state.year,key));const l=document.createElement('span');l.textContent=label;box.append(n,l);const p=resource(state.cut,state.year-1,key),v=resource(state.cut,state.year,key);if(v!=null){const small=document.createElement('small');small.textContent=p==null?'Declarado en SINIM':`${v-p>=0?'+':''}${fmt(v-p)} vs. ${state.year-1}`;box.append(small)}return box}));
      $('evolution-title').textContent=c.nombre+': casos y recursos, en paralelo';
      const k=state.resource;$('resource-chart-title').textContent=fields[k]+' · SINIM';
      const changeRes=resource(state.cut,state.year,k),prevRes=resource(state.cut,state.year-1,k);
      $('reading').textContent=(changeRes!=null&&prevRes!=null?`${fields[k]}: ${fmt(prevRes)} en ${state.year-1} y ${fmt(changeRes)} en ${state.year}. `:'No hay dos años consecutivos de este recurso para comparar. ')+'Estos registros describen recursos y casos; no permiten concluir que el recurso causó la variación.';
    }
    let zoom,mapSvg,selectedPaths;
    function drawMap(){
      const area=$('mapa'),w=Math.max(260,area.clientWidth),h=state.region==='all'?560:440;
      const fs=geo.features.filter(f=>state.region==='all'?(d3.geoCentroid(f)[0]>-80&&d3.geoCentroid(f)[1]>-57):f.properties.region===state.region);
      const projection=d3.geoMercator().fitExtent([[14,14],[w-14,h-14]],{type:'FeatureCollection',features:fs});
      const path=d3.geoPath(projection);
      const vals=Object.keys(data.comunas).flatMap(k=>data.anios.map(y=>rate(k,y))).filter(v=>v!=null).sort((a,b)=>a-b),cap=d3.quantile(vals,.95)||1;
      const changes=Object.keys(data.comunas).flatMap(k=>data.anios.map(y=>delta(k,y))).filter(v=>v!=null&&Number.isFinite(v)).map(Math.abs).sort((a,b)=>a-b),deltaCap=d3.quantile(changes,.95)||1;
      const sequential=d3.scaleSequential(d3.interpolateYlOrRd).domain([0,cap]).clamp(true),diverging=d3.scaleDiverging(d3.interpolateRdBu).domain([deltaCap,0,-deltaCap]).clamp(true);
      mapSvg=d3.create('svg').attr('viewBox',`0 0 ${w} ${h}`).attr('role','img').attr('aria-label','Mapa de tasas por comuna. También puedes seleccionar la comuna en el formulario.');
      const g=mapSvg.append('g');selectedPaths=g.selectAll('path').data(fs).join('path').attr('d',path).attr('class',f=>'commune'+(f.properties.cut===state.cut?' selected':''))
      .attr('fill',f=>{const n=state.mode==='nivel'?rate(f.properties.cut,state.year):delta(f.properties.cut,state.year);return n==null?'#cbd5e1':state.mode==='nivel'?sequential(n):diverging(n)})
      .on('pointermove',(e,f)=>{const cut=f.properties.cut,t=$('tooltip'),v=state.mode==='nivel'?rate(cut,state.year):delta(cut,state.year);t.textContent=data.comunas[cut].nombre+' · '+(v==null?'Sin base de comparación':fmt(v,1)+(state.mode==='nivel'?' / 100.000':'% anual'));t.hidden=false;t.style.left=Math.min(e.clientX+12,innerWidth-245)+'px';t.style.top=Math.min(e.clientY+12,innerHeight-65)+'px'})
      .on('pointerleave',()=>{$('tooltip').hidden=true})
      .on('click',(_,f)=>{state.cut=f.properties.cut;$('comuna').value=state.cut;sync();details();drawCharts();selectedPaths.classed('selected',d=>d.properties.cut===state.cut)});
      zoom=d3.zoom().scaleExtent([1,14]).translateExtent([[0,0],[w,h]]).on('zoom',e=>g.attr('transform',e.transform));mapSvg.call(zoom);area.replaceChildren(mapSvg.node());
      const indicator=state.delito===-1?'30 categorías seleccionadas':data.delitos[state.delito];$('map-subtitle').textContent=indicator+' · '+state.year;
      $('map-title').textContent=state.mode==='nivel'?'Casos por 100.000 habitantes':'Variación de la tasa frente al año anterior';
      const legend=$('legend');legend.replaceChildren();const left=document.createElement('span'),ramp=document.createElement('span'),right=document.createElement('span'),note=document.createElement('span');ramp.className='ramp';
      if(state.mode==='nivel'){left.textContent='0';right.textContent=fmt(cap,0)+' o más';ramp.style.background='linear-gradient(to right,#ffffcc,#fd8d3c,#800026)'}else{left.textContent='Baja';right.textContent='Aumento';ramp.style.background='linear-gradient(to right,#2166ac,#f7f7f7,#b2182b)'}
      note.textContent='Escala fija entre años · extremos saturados al percentil 95'+(state.mode==='cambio'?' · gris: sin base':'');legend.append(left,ramp,right,note);
    }
    function drawChart(id,values,unit){
      const el=$(id),width=Math.max(260,el.clientWidth),height=220,m={left:58,right:20,top:22,bottom:40};
      const valid=values.filter(d=>d.value!=null),svg=d3.create('svg').attr('viewBox',`0 0 ${width} ${height}`).attr('role','img').attr('aria-label',unit+' por año');
      if(!valid.length){svg.append('text').attr('x',width/2).attr('y',100).attr('text-anchor','middle').text('Sin datos para esta serie');el.replaceChildren(svg.node());return}
      const x=d3.scaleLinear().domain([2010,2025]).range([m.left,width-m.right]);
      const y=d3.scaleLinear().domain([0,(d3.max(valid,d=>d.value)||1)*1.12]).nice().range([height-m.bottom,m.top]);
      svg.append('g').attr('transform',`translate(0,${height-m.bottom})`).call(d3.axisBottom(x).tickValues(width<400?[2010,2015,2020,2025]:[2010,2013,2016,2019,2022,2025]).tickFormat(d3.format('d')));
      svg.append('g').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).ticks(4).tickFormat(n=>fmt(n)));
      svg.append('path').datum(values).attr('fill','none').attr('stroke','#1a4a9c').attr('stroke-width',2).attr('d',d3.line().defined(d=>d.value!=null).x(d=>x(d.year)).y(d=>y(d.value)));
      svg.selectAll('circle').data(valid).join('circle').attr('cx',d=>x(d.year)).attr('cy',d=>y(d.value)).attr('r',d=>d.year===state.year?5:3).attr('fill',d=>d.year===state.year?'#f5b912':'#1a4a9c').append('title').text(d=>d.year+': '+fmt(d.value,1)+' '+unit);
      const selected=valid.find(d=>d.year===state.year);if(selected)svg.append('text').attr('x',x(selected.year)).attr('y',y(selected.value)-10).attr('text-anchor',selected.year>=2023?'end':'start').text(fmt(selected.value,1));
      el.replaceChildren(svg.node());
    }
    function drawCharts(){drawChart('chart-rate',data.anios.map(y=>({year:y,value:rate(state.cut,y)})),'casos / 100.000');drawChart('chart-resource',data.anios.map(y=>({year:y,value:resource(state.cut,y,state.resource)})),fields[state.resource])}
    function render(){sync();details();drawMap();drawCharts()}
    $('region').addEventListener('change',e=>{state.region=e.target.value;if(state.region!=='all'&&data.comunas[state.cut].region!==state.region)state.cut=Object.keys(data.comunas).find(k=>data.comunas[k].region===state.region);optionComunas();render()});
    $('comuna').addEventListener('change',e=>{state.cut=e.target.value;render()});
    $('anio').addEventListener('change',e=>{state.year=+e.target.value;render()});
    $('delito').addEventListener('change',e=>{state.delito=+e.target.value;render()});
    $('resource').addEventListener('change',e=>{state.resource=e.target.value;details();drawCharts()});
    for(const mode of ['nivel','cambio'])$(mode).addEventListener('click',()=>{state.mode=mode;$('nivel').setAttribute('aria-pressed',mode==='nivel');$('cambio').setAttribute('aria-pressed',mode==='cambio');drawMap()});
    $('chile').addEventListener('click',()=>{state.region='all';optionComunas();render()});
    $('zoom-in').onclick=()=>mapSvg.call(zoom.scaleBy,1.5);$('zoom-out').onclick=()=>mapSvg.call(zoom.scaleBy,1/1.5);$('zoom-reset').onclick=()=>mapSvg.call(zoom.transform,d3.zoomIdentity);
    $('contenido').hidden=false;$('evolution-panel').hidden=false;$('status').hidden=true;optionComunas();render();
    let previousWidth=0;new ResizeObserver(entries=>{const w=entries[0].contentRect.width;if(Math.abs(w-previousWidth)>1){previousWidth=w;drawMap();drawCharts()}}).observe($('mapa'));
  }catch(error){$('status').textContent='No se pudo abrir el mapa. '+error.message+' Recarga la página o revisa tu conexión.';$('status').setAttribute('role','alert');console.error(error)}
})();
