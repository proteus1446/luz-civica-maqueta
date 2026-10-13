/* Distribuciones de registros originales. Los cálculos están en Python;
   la interfaz solo selecciona grupos, presenta cifras y exporta agregados. */
(function (root) {
  'use strict';
  const money = n => Number.isFinite(n) ? '$' + Math.round(n).toLocaleString('es-CL') : 'Sin dato';
  const number = n => Number.isFinite(n) ? n.toLocaleString('es-CL') : 'Sin dato';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function key(nombre) {
    let s = nombre.replace(/^(Ilustre\s+)?(I\.\s*)?Municipalidad de\s+/i, '').replace(/\s*\([^)]*\)/g, '').trim().toUpperCase();
    s = s.replace(/Ñ/g, '\u0001').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\u0001/g, 'Ñ');
    const aliases = {'CABO DE HORNOS Y ANTARTICA':'CABO DE HORNOS','LA CALERA':'CALERA','LLAY LLAY':'LLAILLAY','MARCHIGE':'MARCHIHUE','OHIGGINS':'O´HIGGINS','PAIHUANO':'PAIGUANO','PUERTO NATALES':'NATALES','SAN VICENTE DE TAGUA TAGUA':'SAN VICENTE'};
    return aliases[s] || s;
  }
  function resolveCode(organismos, comuna) {
    return Object.keys(organismos).find(code => key(organismos[code].nombre) === comuna) || null;
  }
  function csvRows(source, code, year, area, vinculo) {
    const entry = source.organismos[code];
    const rows = [['organismo_codigo','organismo','anio','origen_declarado','vinculo','unidad_analisis','indicador','valor','unidad']];
    const data = entry?.anios[year]?.distribuciones[area]?.[vinculo];
    if (!data) return rows;
    for (const field of ['n','total','min','p10','p25','mediana','p75','p90','max','top10_n','top10_pct']) {
      rows.push([code,entry.nombre,year,area,vinculo,'registros de pago positivos',field,data[field],field==='top10_pct'?'porcentaje':field==='n'||field==='top10_n'?'registros':'pesos nominales']);
    }
    return rows;
  }
  function csv(rows) {
    // Impide que etiquetas de una fuente externa se interpreten como fórmulas.
    return '\ufeff' + rows.map(row => row.map(value => {
      let s = String(value ?? '');
      if (typeof value === 'string' && /^[=+@-]/.test(s)) s = "'" + s;
      return '"' + s.replace(/"/g, '""') + '"';
    }).join(';')).join('\r\n');
  }
  const api = { money, key, resolveCode, csvRows, csv };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.LuzDistribucion = api;
  if (typeof document === 'undefined' || typeof DISTRIBUCION_REGISTROS === 'undefined') return;
  const source = DISTRIBUCION_REGISTROS;
  const comunaSelect = document.getElementById('sel-comuna');
  const yearSelect = document.getElementById('sel-anio');
  const body = document.getElementById('dist-contenido');
  const title = document.getElementById('dist-periodo');
  if (!body || !comunaSelect || !yearSelect) return;
  let code = null;
  function refreshGeneral() {
    code = resolveCode(source.organismos, comunaSelect.value);
    render();
    if (typeof prepararCasosHonorarios === 'function') prepararCasosHonorarios();
    if (typeof renderGasto === 'function') renderGasto();
  }
  function metric(label, value) {
    return `<div class="dist-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }
  function render() {
    const year = yearSelect.value;
    const entry = source.organismos[code]?.anios[year];
    const d = entry?.distribuciones['Todas']?.['Todos'];
    const original = typeof COMUNAS_REM !== 'undefined' ? COMUNAS_REM[comunaSelect.value] : null;
    const aviso = document.getElementById('detalle-periodo-aviso');
    if (aviso && original) {
      aviso.textContent = original._sinDetalle ? `Esta comuna tiene pagos registrados, pero no un detalle de grupos salariales en la salida anterior. Las cifras de esta vista corresponden a ${year}; los meses y áreas disponibles pueden ser parciales.` : `Los grupos salariales y sus casos destacados corresponden a ${original.anyo}. La distribución, el gasto y los casos puntuales de honorarios corresponden a ${year}. Puedes consultar los máximos históricos por separado.`;
    }
    title.textContent = `${source.organismos[code]?.nombre || comunaSelect.value} · ${year} · vista general`;
    if (!d) {
      const metodo = document.getElementById('metodo-cifras-actuales');
      if (metodo) metodo.textContent = 'Sin registros positivos para la selección actual.';
      body.innerHTML = '<p>No hay registros de pago positivos para esta selección. Esto no significa que no exista personal.</p>';
      return;
    }
    let contenido = '<div class="dist-metrics">' + [
      metric('Registros de pago', number(d.n)), metric('Mediana por registro', money(d.mediana)),
      metric('Mitad central de los pagos (P25–P75)', `${money(d.p25)} – ${money(d.p75)}`),
      metric('Pago máximo registrado', money(d.max))
    ].join('') + '</div>';
    const limits = source.meta.limites_histograma;
    const peak = Math.max(...d.histograma, 1);
    contenido += '<h3 class="dist-h3">Distribución de los pagos registrados</h3><div class="dist-hist">';
    d.histograma.forEach((n, i) => {
      const label = i === limits.length - 1 ? `${money(limits[i])} o más` : `${money(limits[i])} a menos de ${money(limits[i+1])}`;
      contenido += `<div class="dist-hist-row"><span>${esc(label)}</span><div class="dist-hist-track"><div style="width:${n/peak*100}%"></div></div><b>${esc(number(n))}</b></div>`;
    });
    contenido += '</div>';
    contenido += `<h3 class="dist-h3">Pagos de mayor monto</h3><p class="dist-note">El 10% de los registros con mayor monto (${number(d.top10_n)} pagos) reúne el ${number(d.top10_pct)}% del importe total seleccionado.</p>`;
    const metodo = document.getElementById('metodo-cifras-actuales');
    if (metodo) metodo.innerHTML = `<p><b>En la selección actual (${esc(year)} · vista general):</b> ${number(d.n)} registros; P10 ${money(d.p10)}, P25 ${money(d.p25)}, mediana ${money(d.mediana)}, P75 ${money(d.p75)} y P90 ${money(d.p90)}. Mínimo ${money(d.min)}; máximo ${money(d.max)}; suma ${money(d.total)}. Todos los importes en CLP.</p><p>Concentración: ${number(d.n)} × 10% = ${number(d.n * .1)}; redondeamos hacia arriba a ${number(d.top10_n)} pagos. Suma de esos pagos ÷ suma de todos los pagos × 100 = ${number(d.top10_pct)}%.</p>`;
    body.innerHTML = contenido;
  }
  [document.getElementById('sel-region'), comunaSelect, yearSelect].filter(Boolean).forEach(select => select.addEventListener('change', refreshGeneral));
  refreshGeneral();
})(typeof globalThis !== 'undefined' ? globalThis : this);
