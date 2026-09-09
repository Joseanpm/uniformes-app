-- Esquema de Supabase (Postgres) para el Sistema de Entrega e Inventario de Uniformes.
--
-- Cómo usarlo: Supabase → tu proyecto → SQL Editor → pega todo este archivo → Run.
-- Es el mismo patrón que ya usaste para la quiniela: correrlo desde el SQL Editor
-- en vez de un script local, para no depender de la red de Danone.
--
-- Equivalente al esquema SQLite de la versión local (uniformes_app/db.py), más una
-- tabla `usuarios` para el login (esta versión sí necesita login porque queda
-- expuesta en internet, a diferencia de la versión local que solo vive en tu WiFi).

create extension if not exists pgcrypto;

create table if not exists config (
    clave text primary key,
    valor text
);
insert into config (clave, valor) values ('cedis', 'CEDIS Mérida ONE')
    on conflict (clave) do nothing;

create table if not exists usuarios (
    id bigint generated always as identity primary key,
    usuario text not null unique,
    nombre text not null,
    password_hash text not null,
    activo boolean not null default true,
    creado_en timestamptz not null default now()
);

create table if not exists prendas (
    id bigint generated always as identity primary key,
    nombre text not null unique,
    categoria text,
    tipo_talla text not null default 'Ropa (XS-XXL)',
    stock_minimo_default integer not null default 0,
    activo boolean not null default true
);

create table if not exists variantes (
    id bigint generated always as identity primary key,
    prenda_id bigint not null references prendas(id),
    talla text not null,
    stock_minimo integer not null default 0,
    unique (prenda_id, talla)
);

create table if not exists empleados (
    id bigint generated always as identity primary key,
    numero_empleado text unique,
    nombre text not null,
    puesto text,
    area text,
    fecha_ingreso date,
    activo boolean not null default true
);

create table if not exists movimientos_inventario (
    id bigint generated always as identity primary key,
    variante_id bigint not null references variantes(id),
    tipo text not null check (tipo in ('entrada', 'salida', 'ajuste')),
    cantidad integer not null,
    fecha date not null,
    motivo text,
    referencia text,
    registrado_por text,
    creado_en timestamptz not null default now()
);

create table if not exists entregas (
    id bigint generated always as identity primary key,
    empleado_id bigint not null references empleados(id),
    variante_id bigint not null references variantes(id),
    cantidad integer not null,
    fecha date not null,
    motivo text,
    entregado_por text,
    notas text,
    movimiento_id bigint references movimientos_inventario(id),
    firma_png_b64 text,
    creado_en timestamptz not null default now()
);

-- Índices para las consultas más comunes (historial por fecha/empleado).
create index if not exists idx_entregas_fecha on entregas (fecha desc);
create index if not exists idx_entregas_empleado on entregas (empleado_id);
create index if not exists idx_movimientos_variante on movimientos_inventario (variante_id);

-- Vista con el stock actual por variante (prenda+talla), calculada sumando
-- entradas/salidas/ajustes. PostgREST expone las vistas igual que las tablas,
-- así que db.py simplemente hace select() sobre "v_stock_actual".
create or replace view v_stock_actual as
select v.id as variante_id, p.nombre as prenda, p.categoria, v.talla, v.stock_minimo,
       coalesce(sum(case when m.tipo = 'entrada' then m.cantidad
                          when m.tipo = 'salida' then -m.cantidad
                          when m.tipo = 'ajuste' then m.cantidad
                          else 0 end), 0) as stock
from variantes v
join prendas p on p.id = v.prenda_id
left join movimientos_inventario m on m.variante_id = v.id
where p.activo = true
group by v.id, p.nombre, p.categoria, v.talla, v.stock_minimo;

-- Nota de seguridad: esta app usa la llave "anon" de Supabase desde el propio
-- Streamlit (no hay backend intermedio), así que el control de acceso real lo
-- da el login de la app (tabla `usuarios`), no Postgres. Si más adelante quieres
-- una segunda capa de seguridad a nivel de base de datos, se puede activar Row
-- Level Security (RLS) por tabla — no es indispensable para el tamaño de este
-- equipo, pero queda como posible siguiente paso.
