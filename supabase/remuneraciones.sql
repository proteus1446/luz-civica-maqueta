-- Ejecutar en SQL Editor de Supabase. Tablas nuevas de esta entrega.
create table if not exists public.rem_organismos (
 organismo_codigo text primary key,
 organismo_nombre text not null
);
create table if not exists public.rem_distribuciones (
 organismo_codigo text not null references public.rem_organismos,
 organismo_nombre text not null, anio integer not null,
 area text not null, vinculo text not null,
 n bigint not null check(n>0), total numeric not null,
 min numeric not null, p10 numeric not null, p25 numeric not null,
 mediana numeric not null, p75 numeric not null, p90 numeric not null, max numeric not null,
 top10_n bigint not null, top10_pct numeric not null,
 primary key(organismo_codigo,anio,area,vinculo),
 check(min<=p10 and p10<=p25 and p25<=mediana and mediana<=p75 and p75<=p90 and p90<=max),
 check(top10_n between 1 and n and top10_pct between 0 and 100)
);
create table if not exists public.rem_mensual (
 organismo_codigo text not null references public.rem_organismos,
 anio integer not null, mes integer not null check(mes between 1 and 12),
 n bigint not null check(n>0), total numeric not null,
 primary key(organismo_codigo,anio,mes)
);
create table if not exists public.rem_histogramas (
 organismo_codigo text not null references public.rem_organismos,
 anio integer not null, area text not null,vinculo text not null,
 tramo integer not null check(tramo between 0 and 9),
 desde_clp numeric not null,hasta_clp numeric,n bigint not null check(n>=0),
 primary key(organismo_codigo,anio,area,vinculo,tramo)
);
create table if not exists public.rem_casos_puntuales (
 organismo_codigo text not null references public.rem_organismos,
 organismo_nombre text not null,anio integer not null,
 posicion integer not null check(posicion between 1 and 5),
 nombre text not null,vinculo text not null,
 meses_informados integer not null check(meses_informados between 1 and 2),
 registros bigint,monto_total_clp numeric not null,
 primary key(organismo_codigo,anio,posicion)
);
-- Lectura pública de los resúmenes de Transparencia Activa.
-- Escrituras reservadas al administrador: el navegador no usa contraseña ni service_role.
alter table public.rem_organismos enable row level security;
alter table public.rem_distribuciones enable row level security;
alter table public.rem_mensual enable row level security;
alter table public.rem_histogramas enable row level security;
alter table public.rem_casos_puntuales enable row level security;
drop policy if exists lectura_publica on public.rem_organismos;
create policy lectura_publica on public.rem_organismos for select to anon, authenticated using (true);
grant select on public.rem_organismos to anon, authenticated;
drop policy if exists lectura_publica on public.rem_distribuciones;
create policy lectura_publica on public.rem_distribuciones for select to anon, authenticated using (true);
grant select on public.rem_distribuciones to anon, authenticated;
drop policy if exists lectura_publica on public.rem_mensual;
create policy lectura_publica on public.rem_mensual for select to anon, authenticated using (true);
grant select on public.rem_mensual to anon, authenticated;
drop policy if exists lectura_publica on public.rem_histogramas;
create policy lectura_publica on public.rem_histogramas for select to anon, authenticated using (true);
grant select on public.rem_histogramas to anon, authenticated;
drop policy if exists lectura_publica on public.rem_casos_puntuales;
create policy lectura_publica on public.rem_casos_puntuales for select to anon, authenticated using (true);
grant select on public.rem_casos_puntuales to anon, authenticated;
