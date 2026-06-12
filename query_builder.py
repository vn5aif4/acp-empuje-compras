"""Construye y ejecuta el query ACP-empuje contra BigQuery.

Billing project: leído de .env → BQ_BILLING_PROJECT
gcloud path:     auto-detectado (Windows + Linux)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

import google.oauth2.credentials
from google.cloud import bigquery
from dotenv import load_dotenv

TABLE = "wmt-edw-sandbox.DMP.DRV_ACP_DMP"

_ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def _billing_project() -> str:
    """Lee BQ_BILLING_PROJECT del .env en cada llamada (no en import time)."""
    load_dotenv(_ENV_FILE, override=True)
    candidates = [
        os.getenv("BQ_BILLING_PROJECT", ""),
        "wmt-9ca45f77fc0cfa9cafcba7a82a",
    ]
    for p in candidates:
        if p and p.strip():
            return p.strip()
    return "wmt-9ca45f77fc0cfa9cafcba7a82a"


# ── gcloud path ────────────────────────────────────────────────────────────────

def _gcloud_cmd() -> str:
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if found:
        return found
    win_path = (
        r"C:\Users\vn5aif4\AppData\Local\Google\CloudSDK"
        r"\google-cloud-sdk\bin\gcloud.cmd"
    )
    if os.path.exists(win_path):
        return win_path
    raise FileNotFoundError("No se encontro gcloud. Instala Google Cloud SDK.")


# ── Filtros ────────────────────────────────────────────────────────────────────

@dataclass
class FiltrosCompras:
    dias_inv:  int  = 15
    dept:      str  = "2,4,13,26,40,46"
    categoria: str  = ""
    items:     str  = ""
    proveedor: str  = ""
    whse_nbr:  str  = ""
    solo_con_pedido: bool = True   # False = muestra TODAS las filas


def _lista_int(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


def _lista_str(raw: str) -> list[str]:
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


# ── Query builder ──────────────────────────────────────────────────────────────

def construir_query(f: FiltrosCompras) -> str:
    dias = max(1, int(f.dias_inv))

    depts = [d.strip() for d in f.dept.split(",") if d.strip().isdigit()]
    dept_str = ", ".join(depts) if depts else "13"

    filtro_cat   = "AND UPPER(T1.CATEGORIA) LIKE UPPER(CONCAT('%', @categoria, '%'))" if f.categoria.strip() else ""
    filtro_prov  = "AND UPPER(T1.PROVEEDOR) LIKE UPPER(CONCAT('%', @proveedor, '%'))" if f.proveedor.strip() else ""
    filtro_item  = "AND T1.ITEM IN UNNEST(@items)"  if _lista_int(f.items)  else ""
    filtro_whse  = "AND T1.WHSE_NBR IN UNNEST(@whse_list)" if _lista_int(f.whse_nbr) else ""

    filtro_pedido = "WHERE CAJAS_A_PEDIR > 0" if f.solo_con_pedido else ""

    return f"""
WITH
params AS (
    SELECT {dias} AS dias_inv
),

base AS (
    SELECT
        T1.ITEM,
        CAST(T1.CID AS INT64)                                       AS CID,
        T1.PROVEEDOR,
        T1.DESCRIPCION,
        T1.DEPT,
        T1.CATEGORIA,
        T1.APROV,
        T1.WHPK_QTY,
        T1.TI * T1.HI                                               AS PALLET_CAJAS,
        T1.TIENDA,
        T1.WHSE_NBR,
        T1.OH, T1.IT, T1.IW, T1.OO,
        T1.FCST_N1W,
        CASE
            WHEN T1.WHSE_NBR = 6009 THEN T1.STOCK_6009
            WHEN T1.WHSE_NBR = 6020 THEN T1.STOCK_6020
            WHEN T1.WHSE_NBR = 6003 THEN T1.STOCK_6003
            WHEN T1.WHSE_NBR = 6010 THEN T1.STOCK_6010
            WHEN T1.WHSE_NBR = 6024 THEN T1.STOCK_6024
        END                                                          AS STOCK_CD,
        P.dias_inv,
        SUM(T1.FCST_N1W) OVER (PARTITION BY T1.CID, T1.WHSE_NBR)   AS fcst_cd_sum,
        ROW_NUMBER() OVER (
            PARTITION BY T1.ITEM, T1.WHSE_NBR ORDER BY T1.TIENDA
        )                                                            AS rn
    FROM `{TABLE}` T1
    CROSS JOIN params P
    WHERE T1.STATUS IN ('A')
      AND T1.DEPT IN ({dept_str})
      {filtro_cat}
      {filtro_item}
      {filtro_prov}
      {filtro_whse}
),

calculos AS (
    SELECT *,
        OH + IT + IW + OO                                            AS TUBERIA_,
        ROUND(dias_inv * FCST_N1W / 7, 0)                           AS MAX_ND_UNI,
        CASE
            WHEN fcst_cd_sum > 0
            THEN ROUND(STOCK_CD * WHPK_QTY * 7 / fcst_cd_sum, 1)
            ELSE NULL
        END                                                          AS DOH_CD,
        STOCK_CD * WHPK_QTY                                         AS STOCK_CD_UNI
    FROM base
),

gaps AS (
    SELECT *,
        CASE WHEN FCST_N1W > 0
             THEN ROUND(TUBERIA_ * 7 / FCST_N1W, 1) ELSE NULL END  AS DOH_ACTUAL,
        GREATEST(0, MAX_ND_UNI - TUBERIA_)                          AS GAP_UNI,
        CASE WHEN TUBERIA_ > MAX_ND_UNI
             THEN CEIL((TUBERIA_ - MAX_ND_UNI) / WHPK_QTY)
             ELSE 0 END                                              AS EXCESO_CAJAS
    FROM calculos
),

gap_cajas AS (
    SELECT *,
        CASE WHEN GAP_UNI > 0 THEN CEIL(GAP_UNI / WHPK_QTY) ELSE 0 END
                                                                     AS GAP_CAJAS_BASE
    FROM gaps
),

cajas AS (
    SELECT *,
        CASE
          WHEN APROV = 'STAPLE' THEN
            CASE
              WHEN rn = 1 AND fcst_cd_sum > 0 AND DOH_CD <= dias_inv * 2
              THEN CEIL(
                     GREATEST(0, dias_inv * fcst_cd_sum / 7 - STOCK_CD_UNI)
                     / WHPK_QTY / PALLET_CAJAS
                   ) * PALLET_CAJAS
              ELSE 0
            END
          ELSE
            CASE
              WHEN FCST_N1W > 0
               AND DOH_CD <= dias_inv * 2
               AND (TUBERIA_ + GAP_CAJAS_BASE * WHPK_QTY) * 7
                   / FCST_N1W <= dias_inv + 2
              THEN GAP_CAJAS_BASE
              ELSE 0
            END
        END                                                          AS CAJAS_A_PEDIR
    FROM gap_cajas
),

cajas_cd AS (
    SELECT *,
        SUM(CAJAS_A_PEDIR) OVER (PARTITION BY ITEM, WHSE_NBR)       AS cajas_ped_cd
    FROM cajas
),

resultado AS (
    SELECT
        ITEM,
        CID,
        PROVEEDOR,
        DESCRIPCION,
        DEPT,
        CATEGORIA,
        APROV,
        WHPK_QTY,
        PALLET_CAJAS,
        TIENDA,
        WHSE_NBR,
        OH, IT, IW, OO,
        FCST_N1W,
        STOCK_CD,
        TUBERIA_,
        DOH_ACTUAL,
        CAST(MAX_ND_UNI AS INT64)                                    AS MAX_ND_UNI,
        CAST(GAP_UNI    AS INT64)                                    AS GAP_UNI,
        GAP_CAJAS_BASE,
        CAJAS_A_PEDIR,
        CASE
            WHEN PALLET_CAJAS > 0
            THEN ROUND(CAJAS_A_PEDIR / PALLET_CAJAS, 2)
            ELSE 0
        END                                                          AS PALLETS_A_PEDIR,
        EXCESO_CAJAS,
        CASE
            WHEN APROV = 'STAPLE' THEN 'INV'
            ELSE
                CASE WHEN FCST_N1W > 0
                     THEN CAST(ROUND((TUBERIA_ + CAJAS_A_PEDIR * WHPK_QTY) * 7 / FCST_N1W, 1) AS STRING)
                     ELSE 'SIN VENTA' END
        END                                                          AS DOH_TIENDA,
        DOH_CD,
        CASE
            WHEN APROV = 'STAPLE' AND fcst_cd_sum > 0
            THEN ROUND((STOCK_CD + cajas_ped_cd) * WHPK_QTY * 7 / fcst_cd_sum, 1)
            ELSE NULL
        END                                                          AS DOH_CD_POST,
        dias_inv
    FROM cajas_cd
)

SELECT *
FROM resultado
{filtro_pedido}
ORDER BY PROVEEDOR, ITEM, WHSE_NBR, TIENDA
"""


# ── Credenciales ───────────────────────────────────────────────────────────────

_ADC_PATHS = [
    os.path.join(os.environ.get("APPDATA", ""), "gcloud", "application_default_credentials.json"),
    os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
]


def _get_credentials():
    """Devuelve credenciales Google usando ADC o token de gcloud."""
    import json
    from google.auth.transport.requests import Request

    # 1. Intentar ADC desde archivo
    for adc_path in _ADC_PATHS:
        if os.path.exists(adc_path):
            with open(adc_path) as fh:
                data = json.load(fh)
            creds = google.oauth2.credentials.Credentials(
                token=None,
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
            )
            creds.refresh(Request())
            return creds

    # 2. Fallback: token de gcloud via subprocess (stdin=DEVNULL para no colgar)
    cmd = _gcloud_cmd()
    result = subprocess.run(
        [cmd, "auth", "print-access-token"],
        capture_output=True, text=True,
        timeout=30, shell=True, stdin=subprocess.DEVNULL,
    )
    lineas = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    if not lineas:
        raise RuntimeError(
            "No se encontraron credenciales Google. "
            "Ejecuta: gcloud auth application-default login"
        )
    token = lineas[-1]
    return google.oauth2.credentials.Credentials(token=token)


# ── TLO Truckload Optimization ──────────────────────────────────────────────────

def _cargar_tlos() -> dict[str, dict[str, int]]:
    tlos = {}
    tlo_path = r"C:\Users\vn5aif4\Downloads\TLO.xlsx"
    if not os.path.exists(tlo_path):
        return tlos
    try:
        import openpyxl
        wb = openpyxl.load_workbook(tlo_path, read_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if len(row) >= 3:
                prov, tlo, pallets = row[0], row[1], row[2]
                if prov:
                    tlos[str(prov).strip().upper()] = {
                        "tlo": int(tlo or 0),
                        "pallets": int(pallets or 0)
                    }
    except Exception as e:
        print("Error al cargar TLO.xlsx:", e)
    return tlos


def _aplicar_tlo_staple(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Inicializar columnas para todas las filas
    for r in rows:
        r["INCREMENTO_TLO_CAJAS"] = 0

    tlos = _cargar_tlos()
    if not tlos:
        return rows

    import math
    from collections import defaultdict
    import copy

    # Agrupar filas por (PROVEEDOR, WHSE_NBR) para STAPLE
    groups = defaultdict(list)
    for r in rows:
        aprov = str(r.get("APROV", "")).upper()
        if aprov == "STAPLE":
            prov = str(r.get("PROVEEDOR", "")).strip().upper()
            whse = r.get("WHSE_NBR")
            if prov and whse is not None:
                groups[(prov, int(whse))].append(r)

    for (prov, whse), group_rows in groups.items():
        tlo_rule = tlos.get(prov)
        if not tlo_rule or tlo_rule.get("tlo") != 1:
            continue
        
        min_pallets = tlo_rule.get("pallets", 0)
        if min_pallets <= 0:
            continue

        # Capacidad de camion completo estandar es 60 pallets
        full_truck_capacity = 60
        
        # Dias objetivo y techo
        dias_inv = 15
        for r in group_rows:
            if r.get("dias_inv") is not None:
                dias_inv = int(r.get("dias_inv"))
                break
        ceiling = dias_inv * 2

        # Calcular pallets actuales
        total_pallets = 0.0
        eligible_rows = []
        for r in group_rows:
            cajas = int(r.get("CAJAS_A_PEDIR") or 0)
            pallet_cajas = int(r.get("PALLET_CAJAS") or 0)
            rn = r.get("rn", 1)
            fcst_cd_sum = float(r.get("fcst_cd_sum") or 0.0)
            
            if rn == 1 and pallet_cajas > 0 and fcst_cd_sum > 0:
                eligible_rows.append(r)
            if pallet_cajas > 0:
                total_pallets += cajas / pallet_cajas

        if total_pallets <= 0 or not eligible_rows:
            continue

        # Calcular el remanente en el último camión
        remaining_pallets = total_pallets % full_truck_capacity

        # Si el remanente es menor al minimo de pallets por camion (TLO)
        if 0 < remaining_pallets < min_pallets:
            deficit = min_pallets - remaining_pallets
            pallets_to_add = int(math.ceil(deficit))
            
            # --- EVALUACION DE OPCION 1: COMPLETAR (ROUND UP) ---
            # Hacemos una simulacion en una copia de las filas
            sim_rows = copy.deepcopy(eligible_rows)
            safe_to_add = True
            
            # Reparto Greedy simulado
            for _ in range(pallets_to_add):
                best_row = None
                best_doh = float("inf")
                for r in sim_rows:
                    cajas = int(r.get("CAJAS_A_PEDIR") or 0)
                    stock_cd = int(r.get("STOCK_CD") or 0)
                    whpk = int(r.get("WHPK_QTY") or 0)
                    fcst_cd_sum = float(r.get("fcst_cd_sum") or 0.0)
                    
                    doh = (stock_cd + cajas) * whpk * 7.0 / fcst_cd_sum
                    if doh < best_doh:
                        best_doh = doh
                        best_row = r
                
                if best_row:
                    pallet_cajas = int(best_row.get("PALLET_CAJAS") or 0)
                    best_row["CAJAS_A_PEDIR"] = int(best_row.get("CAJAS_A_PEDIR") or 0) + pallet_cajas
                    
                    # Verificar si al agregar este pallet, el nuevo DOH post-compra excede el techo
                    stock_cd = int(best_row.get("STOCK_CD") or 0)
                    whpk = int(best_row.get("WHPK_QTY") or 0)
                    fcst_cd_sum = float(best_row.get("fcst_cd_sum") or 0.0)
                    new_doh = (stock_cd + best_row["CAJAS_A_PEDIR"]) * whpk * 7.0 / fcst_cd_sum
                    if new_doh > ceiling:
                        safe_to_add = False
                        break
            
            # Si completar el camion es SEGURO (ningun item supera el techo de DOH)
            if safe_to_add:
                # Aplicamos la simulación al grupo real
                for i, r in enumerate(eligible_rows):
                    added_cajas = sim_rows[i]["CAJAS_A_PEDIR"] - int(r.get("CAJAS_A_PEDIR") or 0)
                    if added_cajas > 0:
                        r["CAJAS_A_PEDIR"] = sim_rows[i]["CAJAS_A_PEDIR"]
                        r["INCREMENTO_TLO_CAJAS"] = added_cajas
            else:
                # --- OPCION 2: RECORTAR (ROUND DOWN) ---
                # Si no es seguro completar, recortamos el camión incompleto
                pallets_to_remove = int(math.ceil(remaining_pallets))
                
                for _ in range(pallets_to_remove):
                    best_row = None
                    best_doh = -float("inf")
                    
                    for r in eligible_rows:
                        cajas = int(r.get("CAJAS_A_PEDIR") or 0)
                        pallet_cajas = int(r.get("PALLET_CAJAS") or 0)
                        stock_cd = int(r.get("STOCK_CD") or 0)
                        whpk = int(r.get("WHPK_QTY") or 0)
                        fcst_cd_sum = float(r.get("fcst_cd_sum") or 0.0)
                        
                        # Solo podemos quitar si ya tenemos cajas pedidas
                        if cajas >= pallet_cajas:
                            doh = (stock_cd + cajas) * whpk * 7.0 / fcst_cd_sum
                            if doh > best_doh:
                                best_doh = doh
                                best_row = r
                    
                    if best_row:
                        pallet_cajas = int(best_row.get("PALLET_CAJAS") or 0)
                        best_row["CAJAS_A_PEDIR"] = int(best_row.get("CAJAS_A_PEDIR") or 0) - pallet_cajas
                        # Marcamos como incremento negativo (o simplemente restamos)
                        best_row["INCREMENTO_TLO_CAJAS"] = int(best_row.get("INCREMENTO_TLO_CAJAS") or 0) - pallet_cajas

            # Recalcular DOH_CD_POST y PALLETS_A_PEDIR para el grupo finalizado
            item_cajas = {}
            for r in group_rows:
                rn = r.get("rn", 1)
                item = r.get("ITEM")
                if rn == 1:
                    item_cajas[item] = int(r.get("CAJAS_A_PEDIR") or 0)

            for r in group_rows:
                item = r.get("ITEM")
                cajas = item_cajas.get(item, 0)
                pallet_cajas = int(r.get("PALLET_CAJAS") or 0)
                
                if pallet_cajas > 0:
                    r["PALLETS_A_PEDIR"] = round(cajas / pallet_cajas, 2)
                else:
                    r["PALLETS_A_PEDIR"] = 0.0
                
                stock_cd = int(r.get("STOCK_CD") or 0)
                whpk = int(r.get("WHPK_QTY") or 0)
                fcst_cd_sum = float(r.get("fcst_cd_sum") or 0.0)
                if fcst_cd_sum > 0:
                    r["DOH_CD_POST"] = round((stock_cd + cajas) * whpk * 7.0 / fcst_cd_sum, 1)

    return rows


# ── Ejecución ──────────────────────────────────────────────────────────────────

def ejecutar_query(
    f: FiltrosCompras,
    billing_project: str = "",
) -> tuple[list[dict[str, Any]], str]:
    """Retorna (filas, sql_usado). Lanza Exception si BQ falla."""
    creds   = _get_credentials()
    proyecto = billing_project.strip() or _billing_project()
    
    # Clonamos filtros para forzar solo_con_pedido = False en BigQuery
    # Esto permite que el optimizador TLO vea todos los productos del proveedor para repartir pallets de forma equilibrada
    f_internal = FiltrosCompras(
        dias_inv=f.dias_inv,
        dept=f.dept,
        categoria=f.categoria,
        proveedor=f.proveedor,
        items=f.items,
        whse_nbr=f.whse_nbr,
        solo_con_pedido=False
    )
    
    client   = bigquery.Client(project=proyecto, credentials=creds)
    sql      = construir_query(f_internal)

    params: list = []
    if f_internal.categoria.strip():
        params.append(bigquery.ScalarQueryParameter("categoria", "STRING", f_internal.categoria.strip()))
    if f_internal.proveedor.strip():
        params.append(bigquery.ScalarQueryParameter("proveedor", "STRING", f_internal.proveedor.strip().upper()))
    items_list = _lista_int(f_internal.items)
    if items_list:
        params.append(bigquery.ArrayQueryParameter("items", "INT64", items_list))
    whse_list = _lista_int(f_internal.whse_nbr)
    if whse_list:
        params.append(bigquery.ArrayQueryParameter("whse_list", "INT64", whse_list))

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    job        = client.query(sql, job_config=job_config)
    rows       = [dict(r) for r in job.result()]
    
    # Aplicar optimización de camión mínimo (TLO) para Staple
    rows = _aplicar_tlo_staple(rows)
    
    # Si el usuario pidió filtrar (solo_con_pedido es True por defecto en main.py),
    # filtramos las filas de forma limpia en Python después de optimizar el camión
    if f.solo_con_pedido:
        rows = [r for r in rows if int(r.get("CAJAS_A_PEDIR") or 0) > 0]
        
    return rows, sql
