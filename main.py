"""FastAPI app — ACP Empuje Compras.

Visualiza el query completo DRV_ACP_DMP con todos los campos calculados y exporta para compra.
"""
from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from query_builder import FiltrosCompras, ejecutar_query, construir_query

app = FastAPI(title="ACP Empuje Compras")

# ── Mapas de nombre ────────────────────────────────────────────────────────────

CD_NAMES = {
    6009: "6009",
    6020: "6020",
    6003: "6003",
    6010: "6010",
    6024: "6024",
}


# ── Badges HTML ────────────────────────────────────────────────────────────────

def _doh_badge(doh, dias_inv: int, aprov: str) -> str:
    if doh is None or str(doh).strip() == "" or str(doh) == "None":
        return '<span class="text-gray-300 text-xs">—</span>'
    s = str(doh).strip()
    if s == "INV":
        return '<span class="px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">INV</span>'
    if s == "SIN VENTA":
        return '<span class="px-1.5 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500">SIN VENTA</span>'
    try:
        v = float(s)
        lim = float(dias_inv)
        ceiling = lim + 2 if aprov == "CARRUSEL" else lim * 2
        if v <= lim:
            cls = "bg-emerald-100 text-emerald-800"
        elif v <= ceiling:
            cls = "bg-amber-100 text-amber-800"
        else:
            cls = "bg-red-100 text-red-800"
        return f'<span class="px-1.5 py-0.5 rounded text-xs font-semibold {cls}">{v:.1f}d</span>'
    except ValueError:
        return f'<span class="px-1.5 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500">{s}</span>'


def _aprov_badge(aprov: str) -> str:
    if str(aprov).upper() == "STAPLE":
        return '<span class="px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">STAPLE</span>'
    return '<span class="px-1.5 py-0.5 rounded text-xs font-semibold bg-violet-100 text-violet-800">CARRUSEL</span>'


def _num(v, decimals: int = 0) -> str:
    if v is None:
        return '<span class="text-gray-300">—</span>'
    try:
        f = float(v)
        if decimals == 0:
            return f"{int(f):,}"
        return f"{f:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


# ── Resumen ────────────────────────────────────────────────────────────────────

def _resumen_html(rows: list[dict], dias_inv: int) -> str:
    total_cajas   = sum(int(r.get("CAJAS_A_PEDIR", 0) or 0) for r in rows)
    items_uniq    = len({r.get("ITEM") for r in rows})
    provs_uniq    = len({r.get("PROVEEDOR") for r in rows})
    staple_cajas  = sum(int(r.get("CAJAS_A_PEDIR", 0) or 0) for r in rows if str(r.get("APROV", "")).upper() == "STAPLE")
    carru_cajas   = total_cajas - staple_cajas

    # Calcular cajas por proveedor para el render inicial
    from collections import defaultdict
    prov_cajas = defaultdict(int)
    for r in rows:
        cjs = int(r.get("CAJAS_A_PEDIR", 0) or 0)
        p = r.get("PROVEEDOR", "Sin Proveedor").upper()
        if cjs > 0:
            prov_cajas[p] += cjs
    
    sorted_provs = sorted(prov_cajas.items(), key=lambda x: x[1], reverse=True)
    if sorted_provs:
        prov_items = "".join(
            f'<div class="bg-gray-50 rounded-lg px-3 py-1.5 border border-gray-100 flex items-center gap-2">'
            f'<span class="font-bold text-gray-800">{prov}</span>'
            f'<span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-emerald-100 text-emerald-800">{cjs:,} cajas</span>'
            f'</div>'
            for prov, cjs in sorted_provs
        )
    else:
        prov_items = '<span class="text-gray-400 font-medium">Ningún proveedor con pedido visible.</span>'

    cards = [
        ("Filas",           f"{len(rows):,}",       "text-[#0053e2]", "kpi-filas"),
        ("Ítems únicos",    f"{items_uniq:,}",       "text-[#0053e2]", "kpi-items"),
        ("Proveedores",     f"{provs_uniq:,}",       "text-[#0053e2]", "kpi-provs"),
        ("Cajas TOTAL",     f"{total_cajas:,}",      "text-emerald-600", "kpi-cajas"),
        ("Cajas STAPLE",    f"{staple_cajas:,}",     "text-blue-600", "kpi-staple"),
        ("Cajas CARRUSEL",  f"{carru_cajas:,}",      "text-violet-600", "kpi-carrusel"),
    ]
    items_html = "".join(
        f'<div class="bg-white rounded-xl border border-gray-200 p-3 text-center shadow-sm">'
        f'<div id="{kid}" class="text-xl sm:text-2xl font-black {c}">{v}</div>'
        f'<div class="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mt-0.5">{lbl}</div>'
        f'</div>'
        for lbl, v, c, kid in cards
    )
    
    summary_section = (
        f'<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">{items_html}</div>'
        f'<div class="bg-white rounded-xl border border-gray-200 p-4 shadow-sm mb-4">'
        f'  <div class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">'
        f'    <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">'
        f'      <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />'
        f'    </svg>'
        f'    Resumen de Cajas por Proveedor (Con Pedido)'
        f'  </div>'
        f'  <div id="prov-summary-container" class="flex flex-wrap gap-2 text-xs">{prov_items}</div>'
        f'</div>'
    )
    return summary_section


# ── Tabla ──────────────────────────────────────────────────────────────────────

_THEAD = """
<thead class="sticky top-0 z-10 bg-gray-100 text-[10px] text-gray-500 uppercase tracking-wider border-b border-gray-200">
  <tr>
    <th class="px-3 py-2.5 whitespace-nowrap">Tipo</th>
    <th class="px-3 py-2.5 whitespace-nowrap">Proveedor</th>
    <th class="px-3 py-2.5 whitespace-nowrap">Descripción</th>
    <th class="px-3 py-2.5 whitespace-nowrap">Ítem</th>
    <th class="px-3 py-2.5 whitespace-nowrap">Dept</th>
    <th class="px-3 py-2.5 whitespace-nowrap">Categoría</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-center">Tienda</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-center">CD</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-right">Tubería</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-right font-bold text-gray-700">Cajas a Pedir</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-center">DOH Tienda</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-center">DOH CD Post</th>
    <th class="px-3 py-2.5 whitespace-nowrap text-center text-red-600 font-bold">Quitar</th>
  </tr>
</thead>
"""


def _fila_html(r: dict, dias_inv: int) -> str:
    aprov    = str(r.get("APROV", "")).upper()
    whse     = r.get("WHSE_NBR", "")
    whse_str = str(int(whse)) if whse is not None else ""
    tienda   = r.get("TIENDA", "")
    tienda_str = str(int(tienda)) if tienda is not None else ""
    cd_label = CD_NAMES.get(int(whse), str(whse)) if whse else "—"
    cajas    = int(r.get("CAJAS_A_PEDIR", 0) or 0)
    cajas_cls = "font-bold text-emerald-700" if cajas > 0 else "text-gray-400"

    # DOH relevante según tipo
    doh_tienda  = r.get("DOH_TIENDA") if aprov != "STAPLE" else None
    doh_cd_post = r.get("DOH_CD_POST") if aprov == "STAPLE" else None

    search_key = (
        f"{r.get('PROVEEDOR','')} {r.get('ITEM','')} {r.get('DESCRIPCION','')} "
        f"{r.get('CATEGORIA','')} {aprov} {whse_str}"
    ).lower()

    doh_val = doh_cd_post if aprov == "STAPLE" else doh_tienda
    try:
        float(str(doh_val))
        doh_str = str(doh_val)
    except (ValueError, TypeError):
        doh_str = ""

    # Extraer todos los valores de BQ para DATA set
    item = r.get("ITEM", "")
    cid = r.get("CID", "")
    prov_name = str(r.get("PROVEEDOR", "")).upper()
    desc = str(r.get("DESCRIPCION", "")).upper()
    dept = r.get("DEPT", "")
    cat = str(r.get("CATEGORIA", "")).upper()
    whpk = r.get("WHPK_QTY", "")
    pallet = r.get("PALLET_CAJAS", "")
    oh = r.get("OH", "")
    it = r.get("IT", "")
    iw = r.get("IW", "")
    oo = r.get("OO", "")
    fcst = r.get("FCST_N1W", "")
    stock_cd = r.get("STOCK_CD", "")
    tuberia = r.get("TUBERIA_", "")
    doh_actual = r.get("DOH_ACTUAL", "")
    max_nd = r.get("MAX_ND_UNI", "")
    gap_uni = r.get("GAP_UNI", "")
    gap_cajas = r.get("GAP_CAJAS_BASE", "")
    pallets_pedir = r.get("PALLETS_A_PEDIR", "")
    exceso = r.get("EXCESO_CAJAS", "")
    doh_tienda_val = r.get("DOH_TIENDA", "")
    doh_cd_val = r.get("DOH_CD", "")
    doh_cd_post_val = r.get("DOH_CD_POST", "")
    dias_inv_val = r.get("dias_inv", "")
    tlo_increment = r.get("INCREMENTO_TLO_CAJAS", 0)

    return (
        f'<tr class="hover:bg-blue-50 border-b border-gray-100 text-xs font-normal" '
        f'data-row="{search_key}" '
        f'data-aprov="{aprov}" '
        f'data-whse="{whse_str}" '
        f'data-tienda="{tienda_str}" '
        f'data-item="{item}" '
        f'data-cajas="{cajas}" '
        f'data-doh="{doh_str}" '
        f'data-prov="{prov_name}" '
        f'data-cat="{cat}" '
        f'data-cid="{cid}" '
        f'data-desc="{desc}" '
        f'data-dept="{dept}" '
        f'data-whpk="{whpk}" '
        f'data-pallet="{pallet}" '
        f'data-oh="{oh}" '
        f'data-it="{it}" '
        f'data-iw="{iw}" '
        f'data-oo="{oo}" '
        f'data-fcst="{fcst}" '
        f'data-stock_cd="{stock_cd}" '
        f'data-tuberia="{tuberia}" '
        f'data-doh_actual="{doh_actual}" '
        f'data-max_nd="{max_nd}" '
        f'data-gap_uni="{gap_uni}" '
        f'data-gap_cajas="{gap_cajas}" '
        f'data-pallets_pedir="{pallets_pedir}" '
        f'data-exceso="{exceso}" '
        f'data-doh_tienda="{doh_tienda_val}" '
        f'data-doh_cd="{doh_cd_val}" '
        f'data-doh_cd_post="{doh_cd_post_val}" '
        f'data-dias_inv="{dias_inv_val}" '
        f'data-tlo_increment="{tlo_increment}">'
        f'<td class="px-3 py-2">{_aprov_badge(aprov)}</td>'
        f'<td class="px-3 py-2 font-medium text-gray-800 whitespace-nowrap">{r.get("PROVEEDOR","")}</td>'
        f'<td class="px-3 py-2 text-gray-600 max-w-[200px] truncate" title="{r.get("DESCRIPCION","")}">'
        f'{r.get("DESCRIPCION","")}</td>'
        f'<td class="px-3 py-2 font-mono">{r.get("ITEM","")}</td>'
        f'<td class="px-3 py-2 text-center">{r.get("DEPT","")}</td>'
        f'<td class="px-3 py-2 text-gray-500 whitespace-nowrap">{r.get("CATEGORIA","")}</td>'
        f'<td class="px-3 py-2 text-center font-mono">{r.get("TIENDA","")}</td>'
        f'<td class="px-3 py-2 text-center whitespace-nowrap">{cd_label}</td>'
        f'<td class="px-3 py-2 text-right font-medium">{_num(r.get("TUBERIA_"))}</td>'
        f'<td class="px-3 py-2 text-right {cajas_cls}">{_num(cajas)}</td>'
        f'<td class="px-3 py-2 text-center">{_doh_badge(doh_tienda, dias_inv, aprov)}</td>'
        f'<td class="px-3 py-2 text-center">{_doh_badge(doh_cd_post, dias_inv, aprov)}</td>'
        f'<td class="px-3 py-2 text-center">'
        f'  <button onclick="eliminarFila(this)" class="text-red-500 hover:text-red-700 hover:scale-115 transition-all p-1" title="Eliminar de la consulta">'
        f'    <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">'
        f'      <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />'
        f'    </svg>'
        f'  </button>'
        f'</td>'
        f'</tr>'
    )


def _tabla_html(rows: list[dict], dias_inv: int) -> str:
    if not rows:
        return (
            '<div class="text-center py-12 text-gray-400 bg-white rounded-xl border border-gray-200">'
            'Sin resultados — ajusta los filtros y vuelve a consultar.</div>'
        )
    filas = "\n".join(_fila_html(r, dias_inv) for r in rows)
    return f"""
<div class="overflow-auto max-h-[60vh] rounded-xl border border-gray-200 shadow-sm bg-white">
  <table id="tabla-resultados" class="w-full text-left border-collapse">
    {_THEAD}
    <tbody class="bg-white divide-y divide-gray-100">
      {filas}
    </tbody>
  </table>
</div>
"""


# ── Página principal ───────────────────────────────────────────────────────────

PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ACP Empuje Compras — Walmart</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- SheetJS para exportación instantánea a Excel -->
  <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
  <style>
    body { font-family: 'Bogle', 'Inter', sans-serif; }
    
    /* Efecto clic en botón Ejecutar Consulta */
    #btn-consultar:active {
      transform: scale(0.97);
    }
    
    /* Estados de carga HTMX */
    .htmx-request #btn-text { display: none !important; }
    .htmx-request #btn-loading-text { display: inline-flex !important; }
    
    /* Columnas pegajosas */
    thead th:nth-child(1), tbody td:nth-child(1) { position: sticky; left: 0; z-index: 5; background: inherit; border-right: 1px solid #f3f4f6; }
    thead th:nth-child(2), tbody td:nth-child(2) { position: sticky; left: 85px; z-index: 5; background: inherit; border-right: 1px solid #f3f4f6; }
  </style>
</head>
<body class="bg-gray-50 min-h-screen">

  <!-- Ruedita de carga pantalla completa (Overlay) -->
  <div id="loading-overlay" class="hidden fixed inset-0 z-50 bg-black/40 flex flex-col items-center justify-center backdrop-blur-sm transition-all">
    <div class="bg-white rounded-2xl p-6 shadow-2xl flex flex-col items-center gap-4 border border-gray-100 max-w-sm text-center animate-bounce-subtle">
      <!-- Rueda de carga estilo Walmart (Azul con Spark Amarillo) -->
      <div class="relative w-16 h-16">
        <div class="absolute inset-0 rounded-full border-4 border-gray-100"></div>
        <div class="absolute inset-0 rounded-full border-4 border-t-[#0053e2] border-r-[#ffc220] animate-spin"></div>
      </div>
      <div>
        <p class="font-extrabold text-gray-800 text-base">Consultando BigQuery</p>
        <p class="text-xs text-gray-500 mt-1">Descargando y calculando matriz DMP. Esto toma alrededor de 10-20 segundos...</p>
      </div>
    </div>
  </div>

  <!-- Header -->
  <header class="bg-[#0053e2] text-white px-6 py-4 flex items-center justify-between shadow-md border-b-4 border-[#ffc220]">
    <div class="flex items-center gap-3">
      <div class="bg-[#ffc220] text-[#0053e2] font-black rounded-full w-9 h-9 flex items-center justify-center text-xl shadow">W</div>
      <div>
        <h1 class="text-xl font-bold leading-tight tracking-tight">ACP Empuje <span class="text-[#ffc220]">Compras</span></h1>
        <p class="text-blue-100 text-xs font-medium">DRV_ACP_DMP · STAPLE &amp; CARRUSEL · Walmart Chile</p>
      </div>
    </div>
    <div class="text-right hidden sm:block">
      <span class="text-xs bg-emerald-800 text-emerald-200 font-mono px-3 py-1 rounded-full border border-emerald-700 animate-pulse">v1.4 - Botones Separados Activos</span>
    </div>
  </header>

  <main class="max-w-full px-4 py-4">

    <!-- Grid principal: Slicers del BI + Contenido de Datos -->
    <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
      
      <!-- Panel de Configuración y BI Slicers -->
      <div class="lg:col-span-1 space-y-4">
        
        <!-- Bloque 1: Query BQ -->
        <form
          hx-post="/consultar"
          hx-target="#results-area"
          hx-swap="innerHTML"
          class="bg-white rounded-xl shadow-sm border border-gray-200 p-4"
        >
          <div class="flex items-center justify-between border-b border-gray-100 pb-2 mb-3">
            <h2 class="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
              <svg class="w-4 h-4 text-[#0053e2]" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 15.75l-2.489-2.489m0 0a3.375 3.375 0 10-4.773-4.773 3.375 3.375 0 004.774 4.774zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              1. Cargar de BigQuery
            </h2>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block text-xs font-semibold text-gray-500 mb-1">Días inv. objetivo</label>
              <input type="number" name="dias_inv" value="15" min="1" max="365"
                class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium focus:ring-2 focus:ring-blue-500 focus:outline-none">
            </div>

            <div>
              <label class="block text-xs font-semibold text-gray-500 mb-1">Departamento(s)</label>
              <input type="text" name="dept" value="2,4,13,26,40,46" placeholder="Ej: 13, 26"
                class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none">
              <p class="text-[10px] text-gray-400 mt-0.5">Separar con comas</p>
            </div>

            <!-- FILTROS OPCIONALES SOLICITADOS -->
            <div class="border-t border-gray-100 pt-2.5 space-y-2.5">
              <div>
                <label class="block text-xs font-semibold text-gray-500 mb-1">Categoría <span class="text-gray-400 font-normal">(opcional)</span></label>
                <input type="text" name="categoria" placeholder="Ej: LIMPIADORES - HOGAR"
                  class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium focus:ring-2 focus:ring-blue-500 focus:outline-none">
              </div>

              <div>
                <label class="block text-xs font-semibold text-gray-500 mb-1">Buscar por ITEM <span class="text-gray-400 font-normal">(opcional)</span></label>
                <input type="text" name="items" placeholder="Ej: 5044936, 5045051"
                  class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none">
                <p class="text-[9px] text-gray-400 mt-0.5">Varios separados por comas</p>
              </div>

              <div>
                <label class="block text-xs font-semibold text-gray-500 mb-1">Proveedor <span class="text-gray-400 font-normal">(opcional)</span></label>
                <input type="text" name="proveedor" placeholder="Ej: CLOROX CHILE SA"
                  class="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium focus:ring-2 focus:ring-blue-500 focus:outline-none">
              </div>


            </div>

            <div class="pt-2">
              <button id="btn-consultar" type="submit"
                class="w-full bg-[#0053e2] hover:bg-blue-700 active:scale-95 text-white font-bold px-4 py-2.5 rounded-lg text-xs tracking-wide uppercase shadow-md transition-all duration-150 flex items-center justify-center gap-2">
                <span id="btn-text">Ejecutar Consulta</span>
                <span id="btn-loading-text" class="hidden items-center gap-2">
                  <div class="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full"></div>
                  Consultando...
                </span>
              </button>
            </div>
          </div>
        </form>

        <!-- Bloque 2: Slicers Interactivos (Estilo Power BI) -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
          <div class="flex items-center justify-between border-b border-gray-100 pb-2 mb-3">
            <h2 class="text-xs font-bold text-gray-700 uppercase tracking-wider flex items-center gap-1.5">
              <svg class="w-4 h-4 text-[#2a8703]" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 01-.659 1.591l-5.432 5.432a2.25 2.25 0 00-.659 1.591v2.927a2.25 2.25 0 01-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 00-.659-1.591L3.659 7.409A2.25 2.25 0 013 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0112 3z" />
              </svg>
              2. Slicers Interactivos (BI)
            </h2>
            <button onclick="resetBiFilters()" class="text-[10px] text-blue-600 hover:underline font-bold">Limpiar</button>
          </div>

          <div class="space-y-4">
            
            <!-- Segmented Control: Tipo Aprov -->
            <div>
              <label class="block text-xs font-semibold text-gray-500 mb-1.5">Filtro por Tipo</label>
              <div class="grid grid-cols-3 gap-1 bg-gray-100 p-1 rounded-lg">
                <label class="cursor-pointer">
                  <input type="radio" name="bi-aprov" value="ALL" checked onchange="applyBiFilters()" class="sr-only peer">
                  <span class="block text-center text-xs py-1 rounded peer-checked:bg-white peer-checked:text-[#0053e2] peer-checked:shadow-sm font-semibold text-gray-500 transition-all">Todos</span>
                </label>
                <label class="cursor-pointer">
                  <input type="radio" name="bi-aprov" value="STAPLE" onchange="applyBiFilters()" class="sr-only peer">
                  <span class="block text-center text-xs py-1 rounded peer-checked:bg-blue-100 peer-checked:text-blue-800 peer-checked:shadow-sm font-semibold text-gray-500 transition-all">Staple</span>
                </label>
                <label class="cursor-pointer">
                  <input type="radio" name="bi-aprov" value="CARRUSEL" onchange="applyBiFilters()" class="sr-only peer">
                  <span class="block text-center text-xs py-1 rounded peer-checked:bg-violet-100 peer-checked:text-violet-800 peer-checked:shadow-sm font-semibold text-gray-500 transition-all">Carrusel</span>
                </label>
              </div>
            </div>

            <!-- CD Slicers (Multi Pills) -->
            <div>
              <label class="block text-xs font-semibold text-gray-500 mb-1.5">Filtro por CD</label>
              <div class="flex flex-wrap gap-1.5">
                <button type="button" onclick="toggleCdPill(this)" data-cd="6009" class="cd-pill text-[10px] font-bold px-2 py-1 rounded-full border border-gray-200 bg-white text-gray-600 transition-all hover:bg-gray-50">6009</button>
                <button type="button" onclick="toggleCdPill(this)" data-cd="6020" class="cd-pill text-[10px] font-bold px-2 py-1 rounded-full border border-gray-200 bg-white text-gray-600 transition-all hover:bg-gray-50">6020</button>
                <button type="button" onclick="toggleCdPill(this)" data-cd="6003" class="cd-pill text-[10px] font-bold px-2 py-1 rounded-full border border-gray-200 bg-white text-gray-600 transition-all hover:bg-gray-50">6003</button>
                <button type="button" onclick="toggleCdPill(this)" data-cd="6010" class="cd-pill text-[10px] font-bold px-2 py-1 rounded-full border border-gray-200 bg-white text-gray-600 transition-all hover:bg-gray-50">6010</button>
                <button type="button" onclick="toggleCdPill(this)" data-cd="6024" class="cd-pill text-[10px] font-bold px-2 py-1 rounded-full border border-gray-200 bg-white text-gray-600 transition-all hover:bg-gray-50">6024</button>
              </div>
            </div>

            <!-- Only with order toggle has been removed, backend always filters only rows with orders -->



          </div>
        </div>

      </div>

      <!-- Área de Visualización y Descarga -->
      <div class="lg:col-span-3 space-y-4">
        
        <!-- Área HTMX donde se cargan los KPI y la tabla -->
        <div id="results-area">
          <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-500">
            <p class="text-base font-semibold text-gray-700 mb-1">Base de Compras Vacía</p>
            <p class="text-xs max-w-md mx-auto">Selecciona los departamentos y haz clic en <strong>Ejecutar Consulta</strong> para descargar la información fresca desde BigQuery.</p>
          </div>
        </div>

      </div>

    </div>

  </main>

  <!-- Script interactivo BI -->
  <script>
    function eliminarFila(btn) {
      const tr = btn.closest('tr');
      if (tr) {
        tr.classList.add('manually-excluded');
        applyBiFilters();
      }
    }

    function ordenarExcedidosAlPrincipio() {
      const tbody = document.querySelector('#tabla-resultados tbody');
      if (!tbody) return;
      const rowsArray = Array.from(tbody.querySelectorAll('tr'));
      
      const diasInvInput = document.querySelector('input[name="dias_inv"]');
      const diasInv = diasInvInput ? parseInt(diasInvInput.value) || 15 : 15;
      
      rowsArray.sort((a, b) => {
        if (a.classList.contains('manually-excluded')) return 1;
        if (b.classList.contains('manually-excluded')) return -1;
        
        const aprovA = a.dataset.aprov;
        const aprovB = b.dataset.aprov;
        const ceilingA = aprovA === 'CARRUSEL' ? (diasInv + 2) : (diasInv * 2);
        const ceilingB = aprovB === 'CARRUSEL' ? (diasInv + 2) : (diasInv * 2);
        
        const dohAText = a.dataset.doh;
        const dohBText = b.dataset.doh;
        let dohA = parseFloat(dohAText);
        if (isNaN(dohA)) dohA = 0;
        let dohB = parseFloat(dohBText);
        if (isNaN(dohB)) dohB = 0;
        
        const exceededA = dohA > ceilingA ? 1 : 0;
        const exceededB = dohB > ceilingB ? 1 : 0;
        
        if (exceededA !== exceededB) {
          return exceededB - exceededA;
        }
        return dohB - dohA;
      });
      rowsArray.forEach(row => tbody.appendChild(row));
    }

    // Mostrar/ocultar el overlay de carga usando eventos de HTMX
    document.addEventListener('htmx:configRequest', function() {
      document.getElementById('loading-overlay').classList.remove('hidden');
    });
    
    document.addEventListener('htmx:afterRequest', function() {
      document.getElementById('loading-overlay').classList.add('hidden');
    });

    function toggleCdPill(btn) {
      btn.classList.toggle('active');
      if (btn.classList.contains('active')) {
        btn.classList.remove('bg-white', 'text-gray-600', 'border-gray-200');
        btn.classList.add('bg-blue-600', 'text-white', 'border-blue-600');
      } else {
        btn.classList.remove('bg-blue-600', 'text-white', 'border-blue-600');
        btn.classList.add('bg-white', 'text-gray-600', 'border-gray-200');
      }
      applyBiFilters();
    }

    function resetBiFilters() {
      // 1. Reset radio type
      document.querySelector('input[name="bi-aprov"][value="ALL"]').checked = true;
      // 2. Reset CD pills
      document.querySelectorAll('.cd-pill').forEach(btn => {
        btn.classList.remove('active', 'bg-blue-600', 'text-white', 'border-blue-600');
        btn.classList.add('bg-white', 'text-gray-600', 'border-gray-200');
      });
      // 3. Reset toggle order
      document.getElementById('bi-only-order').checked = true;
      // 4. Reset search box
      const fl = document.getElementById('filtro-local');
      if (fl) fl.value = '';
      
      applyBiFilters();
    }

    function applyBiFilters() {
      // Ordenar filas con exceso al principio antes de filtrar y contar
      ordenarExcedidosAlPrincipio();

      const table = document.getElementById('tabla-resultados');
      if (!table) return;

      const fl = document.getElementById('filtro-local');
      const q = fl ? fl.value.toLowerCase() : '';
      const aprovFilter = document.querySelector('input[name="bi-aprov"]:checked').value;
      
      // Selected CDs
      const selectedCDs = [];
      document.querySelectorAll('.cd-pill.active').forEach(btn => {
        selectedCDs.push(btn.dataset.cd);
      });
      
      const onlyWithOrder = document.getElementById('bi-only-order').checked;

      // Obtener dias de inventario objetivo
      const diasInvInput = document.querySelector('input[name="dias_inv"]');
      const diasInv = diasInvInput ? parseInt(diasInvInput.value) || 15 : 15;

      // Checkbox para ocultar exceeded DOH
      const hideExceededEl = document.getElementById('bi-hide-exceeded-doh');
      const hideExceeded = hideExceededEl ? hideExceededEl.checked : false;

      let visCount = 0;
      let totalCajas = 0;
      let stapleCajas = 0;
      let carruCajas = 0;
      let exceededCount = 0;
      let itemsSet = new Set();
      let provsSet = new Set();
      const provCajas = {};

      document.querySelectorAll('#tabla-resultados tbody tr').forEach(tr => {
        if (tr.classList.contains('manually-excluded')) {
          tr.style.display = 'none';
          return;
        }
        const rowText = tr.dataset.row;
        const aprov = tr.dataset.aprov;
        const whse = tr.dataset.whse;
        const item = tr.dataset.item;
        const prov = tr.dataset.prov;
        const cajas = parseInt(tr.dataset.cajas) || 0;
        
        // Calcular techo según flujo de la fila (CARRUSEL es flujo continuo = objetivo + 2, STAPLE es objetivo * 2)
        const rowCeiling = aprov === 'CARRUSEL' ? (diasInv + 2) : (diasInv * 2);

        // Evaluar si supera el techo
        const dohText = tr.dataset.doh;
        const dohVal = dohText ? parseFloat(dohText) : NaN;
        let isExceeded = false;
        if (!isNaN(dohVal) && dohVal > rowCeiling) {
          isExceeded = true;
        }

        let show = true;

        if (q && !rowText.includes(q)) show = false;
        if (aprovFilter !== 'ALL' && aprov !== aprovFilter) show = false;
        if (selectedCDs.length > 0 && !selectedCDs.includes(whse)) show = false;
        if (onlyWithOrder && cajas <= 0) show = false;

        // Solo contamos como excedido si pasa los filtros previos de visualización de la tabla
        if (show && isExceeded) {
          exceededCount++;
        }

        if (show && hideExceeded && isExceeded) {
          show = false; // Excluir si el switch está ON
        }

        tr.style.display = show ? '' : 'none';

        if (show) {
          visCount++;
          totalCajas += cajas;
          if (aprov === 'STAPLE') {
            stapleCajas += cajas;
          } else {
            carruCajas += cajas;
          }
          itemsSet.add(item);
          provsSet.add(prov);
          if (cajas > 0) {
            provCajas[prov] = (provCajas[prov] || 0) + cajas;
          }
        }
      });

      // Actualizar KPIs de forma reactiva
      const kpiFilas = document.getElementById('kpi-filas');
      const kpiItems = document.getElementById('kpi-items');
      const kpiProvs = document.getElementById('kpi-provs');
      const kpiCajas = document.getElementById('kpi-cajas');
      const kpiStaple = document.getElementById('kpi-staple');
      const kpiCarrusel = document.getElementById('kpi-carrusel');

      if (kpiFilas) kpiFilas.textContent = visCount.toLocaleString();
      if (kpiItems) kpiItems.textContent = itemsSet.size.toLocaleString();
      if (kpiProvs) kpiProvs.textContent = provsSet.size.toLocaleString();
      if (kpiCajas) kpiCajas.textContent = totalCajas.toLocaleString();
      if (kpiStaple) kpiStaple.textContent = stapleCajas.toLocaleString();
      if (kpiCarrusel) kpiCarrusel.textContent = carruCajas.toLocaleString();

      // Actualizar resumen de proveedores
      const sortedProvs = Object.entries(provCajas).sort((a, b) => b[1] - a[1]);
      const container = document.getElementById('prov-summary-container');
      if (container) {
        if (sortedProvs.length === 0) {
          container.innerHTML = '<span class="text-gray-400 font-medium">Ningún proveedor con pedido visible.</span>';
        } else {
          container.innerHTML = sortedProvs.map(([prov, cjs]) => {
            return `<div class="bg-gray-50 rounded-lg px-3 py-1.5 border border-gray-100 flex items-center gap-2">
              <span class="font-bold text-gray-800">${prov}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-emerald-100 text-emerald-800">${cjs.toLocaleString()} cajas</span>
            </div>`;
          }).join('');
        }
      }

      // Actualizar banner de alerta DOH
      const banner = document.getElementById('doh-alert-banner');
      const ceilingDaysLabel = document.getElementById('ceiling-days-label');
      const exceededCountLabel = document.getElementById('exceeded-count-label');
      if (banner) {
        if (exceededCount > 0) {
          banner.classList.remove('hidden');
          if (ceilingDaysLabel) {
            ceilingDaysLabel.textContent = `+2 días para CARRUSEL / *2 para STAPLE`;
          }
          if (exceededCountLabel) exceededCountLabel.textContent = exceededCount;
        } else {
          banner.classList.add('hidden');
        }
      }
    }
        }
      });

      // Actualizar KPIs de forma reactiva
      const kpiFilas = document.getElementById('kpi-filas');
      const kpiItems = document.getElementById('kpi-items');
      const kpiProvs = document.getElementById('kpi-provs');
      const kpiCajas = document.getElementById('kpi-cajas');
      const kpiStaple = document.getElementById('kpi-staple');
      const kpiCarrusel = document.getElementById('kpi-carrusel');

      if (kpiFilas) kpiFilas.textContent = visCount.toLocaleString();
      if (kpiItems) kpiItems.textContent = itemsSet.size.toLocaleString();
      if (kpiProvs) kpiProvs.textContent = provsSet.size.toLocaleString();
      if (kpiCajas) kpiCajas.textContent = totalCajas.toLocaleString();
      if (kpiStaple) kpiStaple.textContent = stapleCajas.toLocaleString();
      if (kpiCarrusel) kpiCarrusel.textContent = carruCajas.toLocaleString();

      // Actualizar resumen de proveedores
      const sortedProvs = Object.entries(provCajas).sort((a, b) => b[1] - a[1]);
      const container = document.getElementById('prov-summary-container');
      if (container) {
        if (sortedProvs.length === 0) {
          container.innerHTML = '<span class="text-gray-400 font-medium">Ningún proveedor con pedido visible.</span>';
        } else {
          container.innerHTML = sortedProvs.map(([prov, cjs]) => {
            return `<div class="bg-gray-50 rounded-lg px-3 py-1.5 border border-gray-100 flex items-center gap-2">
              <span class="font-bold text-gray-800">${prov}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-black bg-emerald-100 text-emerald-800">${cjs.toLocaleString()} cajas</span>
            </div>`;
          }).join('');
        }
      }

      // Actualizar banner de alerta DOH
      const banner = document.getElementById('doh-alert-banner');
      const ceilingDaysLabel = document.getElementById('ceiling-days-label');
      const exceededCountLabel = document.getElementById('exceeded-count-label');
      if (banner) {
        if (exceededCount > 0) {
          banner.classList.remove('hidden');
          if (ceilingDaysLabel) ceilingDaysLabel.textContent = ceiling;
          if (exceededCountLabel) exceededCountLabel.textContent = exceededCount;
        } else {
          banner.classList.add('hidden');
        }
      }
    }

    // Exportar con formato compra solicitado:
    // Columnas: *Motivo creacion, *#Articulo, *Nodo Recibo, *Cant Ord VNPK
    // Para Staple va CD (whse), para Carrusel va TIENDA
    function exportarFormatoCompra(tipo) {
      const table = document.getElementById('tabla-resultados');
      if (!table) {
        alert("Primero ejecuta la consulta para cargar la información.");
        return;
      }

      const rows = [];
      const dataRows = [];
      
      document.querySelectorAll('#tabla-resultados tbody tr').forEach(tr => {
        if (tr.style.display !== 'none') {
          const aprov = tr.dataset.aprov; // 'STAPLE' o 'CARRUSEL'
          
          if (aprov !== tipo) return;

          const articulo = tr.dataset.item;
          const whse = tr.dataset.whse;
          const tienda = tr.dataset.tienda;
          const cajas = parseInt(tr.dataset.cajas) || 0;

          if (cajas > 0) {
            const nodo = (tipo === 'STAPLE') ? whse : tienda;
            rows.push({
              "*Motivo creacion": "Business Decision",
              "*#Articulo": parseInt(articulo) || articulo,
              "*Nodo Recibo": parseInt(nodo) || nodo,
              "*Cant Ord VNPK": cajas
            });
            
            // Extraer las 29 columnas completas de la base de datos para la hoja DATA
            dataRows.push({
              "Ítem": parseInt(tr.dataset.item) || tr.dataset.item,
              "CID": parseInt(tr.dataset.cid) || tr.dataset.cid,
              "Proveedor": tr.dataset.prov,
              "Descripción": tr.dataset.desc,
              "Dept": parseInt(tr.dataset.dept) || tr.dataset.dept,
              "Categoría": tr.dataset.cat,
              "Tipo": tr.dataset.aprov,
              "WHPK Qty": parseInt(tr.dataset.whpk) || 0,
              "Pallet Cajas": parseInt(tr.dataset.pallet) || 0,
              "Tienda": parseInt(tr.dataset.tienda) || tr.dataset.tienda,
              "CD (WHSE)": parseInt(tr.dataset.whse) || tr.dataset.whse,
              "OH (Stock Tienda)": parseInt(tr.dataset.oh) || 0,
              "In Transit (IT)": parseInt(tr.dataset.it) || 0,
              "In Warehouse (IW)": parseInt(tr.dataset.iw) || 0,
              "Open Orders (OO)": parseInt(tr.dataset.oo) || 0,
              "FCST N1W": parseFloat(tr.dataset.fcst) || 0,
              "Stock CD (Cajas)": parseInt(tr.dataset.stock_cd) || 0,
              "Tubería": parseInt(tr.dataset.tuberia) || 0,
              "DOH Actual": parseFloat(tr.dataset.doh_actual) || 0,
              "Max ND Uni": parseInt(tr.dataset.max_nd) || 0,
              "Gap Uni": parseInt(tr.dataset.gap_uni) || 0,
              "Gap Cajas Base": parseInt(tr.dataset.gap_cajas) || 0,
              "Cajas a Pedir": cajas,
              "Pallets a Pedir": parseFloat(tr.dataset.pallets_pedir) || 0,
              "Exceso Cajas": parseInt(tr.dataset.exceso) || 0,
              "DOH Tienda": tr.dataset.doh_tienda,
              "DOH CD": parseFloat(tr.dataset.doh_cd) || 0,
              "DOH CD Post": parseFloat(tr.dataset.doh_cd_post) || 0,
              "Días Inv. Objetivo": parseInt(tr.dataset.dias_inv) || 15,
              "Incremento TLO (Cajas)": parseInt(tr.dataset.tlo_increment) || 0
            });
          }
        }
      });

      if (rows.length === 0) {
        alert(`No hay registros visibles de tipo ${tipo} con CAJAS A PEDIR > 0 para exportar.`);
        return;
      }

      // Crear workbook usando SheetJS
      const worksheet = XLSX.utils.json_to_sheet(rows);
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, tipo);
      
      // Agregar la segunda hoja "DATA"
      const dataWorksheet = XLSX.utils.json_to_sheet(dataRows);
      XLSX.utils.book_append_sheet(workbook, dataWorksheet, "DATA");
      
      // Ajustar anchos primera hoja
      worksheet['!cols'] = [
        { wch: 18 }, // Motivo
        { wch: 14 }, // Articulo
        { wch: 14 }, // Nodo Recibo
        { wch: 15 }  // Cantidad
      ];

      // Ajustar anchos segunda hoja DATA (29 columnas)
      dataWorksheet['!cols'] = [
        { wch: 12 }, // Item
        { wch: 12 }, // CID
        { wch: 25 }, // Proveedor
        { wch: 30 }, // Descripcion
        { wch: 8 },  // Dept
        { wch: 20 }, // Categoria
        { wch: 12 }, // Tipo
        { wch: 10 }, // WHPK Qty
        { wch: 12 }, // Pallet Cajas
        { wch: 10 }, // Tienda
        { wch: 10 }, // CD
        { wch: 18 }, // OH Stock Tienda
        { wch: 15 }, // IT
        { wch: 15 }, // IW
        { wch: 15 }, // OO
        { wch: 12 }, // FCST N1W
        { wch: 16 }, // Stock CD
        { wch: 10 }, // Tuberia
        { wch: 12 }, // DOH Actual
        { wch: 12 }, // Max ND Uni
        { wch: 10 }, // Gap Uni
        { wch: 15 }, // Gap Cajas Base
        { wch: 15 }, // Cajas a Pedir
        { wch: 15 }, // Pallets a Pedir
        { wch: 12 }, // Exceso Cajas
        { wch: 12 }, // DOH Tienda
        { wch: 12 }, // DOH CD
        { wch: 12 }, // DOH CD Post
        { wch: 18 }, // Dias Inv. Objetivo
        { wch: 22 }  // Incremento TLO Cajas
      ];

      const fileName = tipo === 'STAPLE' ? "Carga_Compras_Staple.xlsx" : "Carga_Compras_Carrusel.xlsx";
      XLSX.writeFile(workbook, fileName);
    }
  </script>
</body>
</html>"""


# ── Rutas ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return PAGE


@app.post("/consultar", response_class=HTMLResponse)
async def consultar(
    dias_inv:        str = Form("15"),
    dept:            str = Form("2,4,13,26,40,46"),
    categoria:       str = Form(""),
    items:           str = Form(""),
    proveedor:       str = Form(""),
    whse_nbr:        str = Form(""),
):
    filtros = FiltrosCompras(
        dias_inv        = int(dias_inv) if dias_inv.strip().isdigit() else 15,
        dept            = dept,
        categoria       = categoria,
        proveedor       = proveedor,
        items           = items,
        whse_nbr        = whse_nbr,
        solo_con_pedido = True,  # Traemos SOLO las filas con pedido de BigQuery!
    )

    try:
        rows, sql = ejecutar_query(filtros)
    except Exception as exc:
        return f"""
        <div class="bg-red-50 border border-red-200 rounded-xl p-5 text-red-800">
          <p class="font-semibold mb-1"> Error al ejecutar la query</p>
          <pre class="text-xs overflow-auto whitespace-pre-wrap">{str(exc)}</pre>
          <details class="mt-3">
            <summary class="cursor-pointer text-xs text-red-500">Ver SQL generado</summary>
            <pre class="text-xs mt-2 overflow-auto whitespace-pre-wrap bg-red-100 p-3 rounded">{sql}</pre>
          </details>
        </div>"""

    dias_inv_int = filtros.dias_inv
    resumen      = _resumen_html(rows, dias_inv_int)
    tabla        = _tabla_html(rows, dias_inv_int)

    alert_banner = """
    <div id="doh-alert-banner" class="hidden bg-amber-50 border-2 border-amber-200 rounded-xl p-4 mb-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-center gap-2.5 text-amber-800 font-bold">
          <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span class="text-sm">¡Alerta! Hay ítems que sobrepasan el techo de DOH (<span id="ceiling-days-label">30</span> días)</span>
        </div>
        <label class="relative inline-flex items-center cursor-pointer shrink-0">
          <input type="checkbox" id="bi-hide-exceeded-doh" onchange="applyBiFilters()" class="sr-only peer">
          <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-600"></div>
          <span class="ml-2 text-xs font-bold text-amber-950 select-none">Eliminar del reporte y exportación</span>
        </label>
      </div>
      <p class="text-xs text-amber-700 mt-1.5">Se detectaron <span id="exceeded-count-label" class="font-extrabold text-amber-900">0</span> filas que sobrepasan el límite de DOH. Activa el interruptor para excluirlas de los KPIs, del resumen de proveedores, de la visualización y del archivo Excel.</p>
    </div>
    """

    # Agregar los botones de exportar y la cabecera interactiva del listado
    header_listado = f"""
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h3 class="text-sm font-bold text-gray-800">Listado de Pedidos Calculados</h3>
        <p class="text-xs text-gray-500">Usa los BI Slicers de la izquierda para filtrar la tabla antes de exportar.</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- Botón Exportar STAPLE -->
        <button onclick="exportarFormatoCompra('STAPLE')"
          class="bg-[#0053e2] hover:bg-blue-700 text-white font-bold px-4 py-2.5 rounded-lg text-xs tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          <span>Exportar STAPLE (CD)</span>
        </button>

        <!-- Botón Exportar CARRUSEL -->
        <button onclick="exportarFormatoCompra('CARRUSEL')"
          class="bg-[#7c3aed] hover:bg-violet-700 text-white font-bold px-4 py-2.5 rounded-lg text-xs tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          <span>Exportar CARRUSEL (Tienda)</span>
        </button>
      </div>
    </div>
    """

    # Trigger JS after HTMX update to apply default filtering immediately
    js_trigger = """
    <script>
      setTimeout(() => {
        applyBiFilters();
      }, 50);
    </script>
    """

    return resumen + alert_banner + header_listado + tabla + js_trigger
