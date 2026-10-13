-- La reconciliación debe devolver cero filas.
select d.organismo_codigo,d.anio,d.n,sum(m.n) n_mensual,d.total,sum(m.total) total_mensual
from public.rem_distribuciones d join public.rem_mensual m using(organismo_codigo,anio)
where d.area='Todas' and d.vinculo='Todos'
group by d.organismo_codigo,d.anio,d.n,d.total
having d.n<>sum(m.n) or abs(d.total-sum(m.total))>0.1;
-- Ejemplo de consulta general de Ñuñoa (MU186):
select * from public.rem_distribuciones
where organismo_codigo='MU186' and anio=2025 and area='Todas' and vinculo='Todos';
select nombre,vinculo,meses_informados,monto_total_clp
from public.rem_casos_puntuales where organismo_codigo='MU186' and anio=2025 order by posicion;
