# pipeline_condiciones.py
# ============================================================
# Pipeline unificado para procesamiento de condiciones
# Reemplaza los notebooks individuales por condición
# Uso: python pipeline_condiciones.py <ruta_excel>
# ============================================================

import os
import re
import json
import math
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import pandas as pd


# ============================================================
# CONFIGURACIÓN DE CONDICIONES ACTIVAS
# Agrega o quita condiciones aquí según sea necesario
# ============================================================
CONDICIONES = {
    "0424": {"carpeta": "424"},
    "0622": {"carpeta": "622"},
    "0822": {"carpeta": "822"},
    "0862": {"carpeta": "862"},
    "0876": {"carpeta": "876"},
}


# ============================================================
# HELPERS DE FORMATO
# Replicados exactamente del notebook cond424.ipynb
# ============================================================

def _to_str(x) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, (int, float)):
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return str(x)
    return str(x).strip()


def _zfill_digits(x, width: int) -> str:
    s = _to_str(x)
    s = re.sub(r"\D", "", s)
    return s.zfill(width)[:width]


def _pad_left(x, width: int, fill=" ") -> str:
    s = _to_str(x)
    return s.rjust(width, fill)[:width]


def _pad_right(x, width: int, fill=" ") -> str:
    s = _to_str(x)
    return s.ljust(width, fill)[:width]


def _yyyymmdd_from_acf_fecha_trx(x) -> str:
    s = _zfill_digits(x, 8)
    return s if len(s) == 8 else ""


def _hora_6(x) -> str:
    s = _to_str(x)
    if s == "":
        return "000000"
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6)


def _numero_tarjeta(j_tarjeta_750, banco_destino) -> str:
    """IZQUIERDA(tarjeta,6) + banco_destino + DERECHA(tarjeta,4)"""
    t = _to_str(j_tarjeta_750)
    b = _to_str(banco_destino)
    left6  = t[:6].ljust(6)
    right4 = t[-4:].rjust(4) if len(t) >= 4 else t.rjust(4)
    return f"{left6}{b}{right4}".strip()


def _importe_correcto(x) -> str:
    """Quita separadores y rellena a 16 con ceros."""
    s = _to_str(x)
    if s == "":
        return "0" * 16
    s = s.replace(".", "").replace(",", "")
    s = re.sub(r"\D", "", s)
    return s.zfill(16)[:16]


def _moneda_correcta(x) -> str:
    """PEN→604, USD→840, si no mapea → 000"""
    s = _to_str(x).upper()
    if s == "PEN":
        return "604"
    if s == "USD":
        return "840"
    if s.isdigit() and len(s) == 3:
        return s
    return "000"


def normalize_ddmmyyyy(x) -> str:
    """Normaliza fecha a 8 dígitos DDMMYYYY. Si vacío devuelve HOY."""
    if x is None or str(x).strip() == "":
        return datetime.today().strftime("%d%m%Y")
    digits = re.sub(r"\D", "", str(x).strip())
    if len(digits) != 8:
        raise ValueError(f"Fecha debe ser DDMMYYYY. Ej: 24052026. Recibido: {x}")
    return digits


# ============================================================
# CLASE 1: IngestorExcel
# Lee el Excel del correo y devuelve un DataFrame limpio
# ============================================================

class IngestorExcel:

    def __init__(self, ruta_excel: str, skiprows: int = 4):
        self.ruta_excel = Path(ruta_excel)
        self.skiprows   = skiprows
        self.df         = None

    def ingestar(self) -> pd.DataFrame:
        """Lee el Excel y devuelve DataFrame limpio."""
        self.df = self._leer_robusto()
        return self.df

    # ── privados ────────────────────────────────────────────

    def _leer_robusto(self) -> pd.DataFrame:
        try:
            df = pd.read_excel(
                self.ruta_excel,
                engine='openpyxl',
                skiprows=self.skiprows,
                dtype=str
            )
        except Exception:
            raw = self._parse_xlsx_xml(str(self.ruta_excel))
            if raw.empty:
                return raw
            header_row_idx = None
            candidates = ['ACF-Condiciones que generaron alertas', 'Condiciones', 'condiciones']
            for idx in range(len(raw)):
                row_as_text = ' | '.join([
                    str(x) for x in raw.iloc[idx].tolist() if x is not None
                ])
                if any(c.lower() in row_as_text.lower() for c in candidates):
                    header_row_idx = idx
                    break
            if header_row_idx is None:
                header_row_idx = self.skiprows
            headers = raw.iloc[header_row_idx].tolist()
            df = raw.iloc[header_row_idx + 1:].copy()
            df.columns = headers

        df = df.dropna(axis=1, how='all')
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how='all').copy()
        return df

    def _col_letter_to_index(self, col_letters: str) -> int:
        n = 0
        for ch in col_letters:
            n = n * 26 + (ord(ch.upper()) - 64)
        return n - 1

    def _parse_xlsx_xml(self, file_path: str) -> pd.DataFrame:
        """Parser XML de fallback para Excel corruptos o con formato inusual."""
        NS_MAIN = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        REL_NS  = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

        with zipfile.ZipFile(file_path) as z:
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                sst = ET.fromstring(z.read('xl/sharedStrings.xml'))
                for si in sst:
                    texts = []
                    for node in si.iter():
                        if node.tag.endswith('}t') and node.text is not None:
                            texts.append(node.text)
                    shared_strings.append(''.join(texts))

            workbook   = ET.fromstring(z.read('xl/workbook.xml'))
            sheets     = workbook.find('a:sheets', NS_MAIN)
            first_sheet = list(sheets)[0]
            rid        = first_sheet.attrib[REL_NS]

            rels   = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            target = None
            for rel in rels:
                if rel.attrib.get('Id') == rid:
                    target = rel.attrib.get('Target')
                    break
            if target is None:
                raise ValueError(f'No se encontró sheet target para {file_path}')
            if not target.startswith('xl/'):
                target = 'xl/' + target

            sheet_xml  = ET.fromstring(z.read(target))
            sheet_data = sheet_xml.find('a:sheetData', NS_MAIN)
            rows       = []
            max_col    = 0

            for row in sheet_data:
                row_values = {}
                for c in row:
                    ref = c.attrib.get('r', '')
                    m = re.match(r'([A-Z]+)(\d+)', ref)
                    if not m:
                        continue
                    col_letters, _ = m.groups()
                    col_idx = self._col_letter_to_index(col_letters)
                    max_col = max(max_col, col_idx)
                    t  = c.attrib.get('t')
                    v  = c.find('a:v', NS_MAIN)
                    is_ = c.find('a:is', NS_MAIN)
                    value = None
                    if t == 's' and v is not None:
                        idx_ = int(v.text)
                        value = shared_strings[idx_] if idx_ < len(shared_strings) else None
                    elif t == 'inlineStr' and is_ is not None:
                        texts = [x.text or '' for x in is_.iter() if x.tag.endswith('}t')]
                        value = ''.join(texts)
                    elif v is not None:
                        value = v.text
                    row_values[col_idx] = value
                if row_values:
                    full_row = [row_values.get(i) for i in range(max_col + 1)]
                    rows.append(full_row)

            if not rows:
                return pd.DataFrame()
            width = max(len(r) for r in rows)
            rows  = [r + [None] * (width - len(r)) for r in rows]
            return pd.DataFrame(rows)


# ============================================================
# CLASE 2: SeparadorCondiciones
# Agrupa el DataFrame por código y copia a cada Archivo_Base/
# ============================================================

class SeparadorCondiciones:

    def __init__(self, df: pd.DataFrame, base_dir: Path, condiciones: dict):
        self.df          = df
        self.base_dir    = Path(base_dir)
        self.condiciones = condiciones
        self.grupos      = {}

    def separar(self) -> dict:
        """Agrupa por código de condición. Devuelve dict {cod: DataFrame}."""
        col_cond = self._encontrar_columna_condiciones()
        self.df[col_cond] = (
            self.df[col_cond]
            .fillna('SIN_VALOR')
            .astype(str)
            .str.strip()
        )
        for condicion, grupo in self.df.groupby(col_cond, dropna=False):
            cod = str(condicion).strip()
            if cod in self.condiciones:
                self.grupos[cod] = grupo.copy()
            else:
                print(f"  [AVISO] Condición '{cod}' no configurada, se omite.")
        return self.grupos

    def exportar_a_carpetas(self, fecha_str: str) -> dict:
        """Exporta cada grupo a su Archivo_Base/ correspondiente."""
        rutas = {}
        for cod, grupo in self.grupos.items():
            carpeta        = self.condiciones[cod]["carpeta"]
            archivo_base   = self.base_dir / carpeta / "Archivo_Base"
            archivo_base.mkdir(parents=True, exist_ok=True)
            nombre         = f"condiciones_{fecha_str}.xlsx"
            ruta_salida    = archivo_base / nombre
            grupo.to_excel(ruta_salida, index=False, engine='openpyxl')
            rutas[cod]     = ruta_salida
            print(f"  [{cod}] → {ruta_salida}")
        return rutas

    def _encontrar_columna_condiciones(self) -> str:
        columnas = [str(c).strip() for c in self.df.columns]
        for col in columnas:
            low = col.lower()
            if 'condiciones' in low or 'generaron alertas' in low:
                return col
        raise ValueError('No se encontró la columna de condiciones en el DataFrame.')


# ============================================================
# CLASE 3: ConvertidorMonitor
# Genera el TXT de 875 chars para Monitor
# Replica exactamente la lógica de cond424.ipynb
# ============================================================

class ConvertidorMonitor:

    COLUMNAS_REQUERIDAS = {
        "ACF-Tarjeta registro 750",
        "ACF-Código Banco Destino Transf. Inmediata",
        "ACF-Fecha TRX",
        "ACF-Hora TRX",
        "ACF-ID Cliente",
    }

    def __init__(self, condicion: str, carpeta_base: Path):
        self.condicion    = condicion
        self.carpeta_base = Path(carpeta_base)
        self.export_dir   = self.carpeta_base / "Exportado"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def procesar(
        self,
        fechacarga: str    = "",
        fecha_proceso: str = "",
        export_excel: bool = True
    ):
        fechacarga    = normalize_ddmmyyyy(fechacarga)
        fecha_proceso = normalize_ddmmyyyy(fecha_proceso)

        # 1. Correlativo
        icorr = self._obtener_icorr_siguiente()

        # 2. Leer Excel más reciente de Archivo_Base
        input_dir    = self.carpeta_base / "Archivo_Base"
        journal_path = self._get_latest_excel(input_dir)
        df           = self._read_input(str(journal_path))

        # 3. Validar columnas
        missing = self.COLUMNAS_REQUERIDAS - set(df.columns)
        if missing:
            raise ValueError(f"[{self.condicion}] Faltan columnas: {missing}")

        # 4. Columnas calculadas
        df["NUMERO DE TARJETA"] = df.apply(
            lambda r: _numero_tarjeta(
                r["ACF-Tarjeta registro 750"],
                r["ACF-Código Banco Destino Transf. Inmediata"]
            ), axis=1
        )
        df["FECHA"] = df["ACF-Fecha TRX"].apply(_yyyymmdd_from_acf_fecha_trx)
        df["HORA"]  = df["ACF-Hora TRX"].apply(_hora_6)

        # 5. Construir hoja1
        hoja1 = pd.DataFrame({
            "FECHA RECLAMO":       df["FECHA"].values,
            "FECHA PROCESO":       df["FECHA"].values,
            "FECHA TRANSACCION":   df["FECHA"].values,
            "NUMERO DE TARJETA":   df["NUMERO DE TARJETA"].values,
            "BT":                  df["ACF-ID Cliente"].apply(_to_str).values,
            "CODIGO AUTORIZACION": "",
            "IMPORTE":             "",
            "MONEDA":              "",
        })

        hoja1["Fecha Reclamo2"]    = hoja1["FECHA RECLAMO"].apply(
            lambda x: _pad_right(_to_str(x), 8, " ")
        )
        hoja1["Fecha Transacción"] = hoja1["FECHA TRANSACCION"].apply(
            lambda x: _pad_right(_to_str(x), 8, " ")
        )
        hoja1["Tarjeta"]           = hoja1["NUMERO DE TARJETA"].apply(_to_str)
        hoja1["Autorización"]      = hoja1["CODIGO AUTORIZACION"].apply(_to_str)
        hoja1["Llave"]             = (
            hoja1["Fecha Reclamo2"]
            + hoja1["Fecha Transacción"]
            + hoja1["Autorización"]
        )
        hoja1["BT Correcta"]       = hoja1["BT"].apply(lambda x: _pad_left(x, 15, " "))
        hoja1["Importe Correcto"]  = hoja1["IMPORTE"].apply(_importe_correcto)
        hoja1["Moneda Correcta"]   = hoja1["MONEDA"].apply(_moneda_correcta)
        hoja1["HORA"]              = df["HORA"].values
        hoja1 = hoja1.reset_index(drop=True)
        hoja1["REGISTRO_TXT"]      = self._build_registro_txt(
            hoja1, icorr=icorr, fechacarga=fechacarga
        )

        # 6. Exportar TXT en lotes de 800
        run_dir = self.export_dir / fecha_proceso
        run_dir.mkdir(parents=True, exist_ok=True)
        self._safe_empty_dir(run_dir, "*.txt")

        rows_cnt  = len(hoja1)
        files_cnt = math.ceil(rows_cnt / 800) if rows_cnt > 0 else 1

        for j in range(1, files_cnt + 1):
            file_number = str(j).zfill(2)
            file_path   = run_dir / f"RECLAMOS_{fecha_proceso}_{self.condicion}_{file_number}.txt"
            start       = (j - 1) * 800
            end         = min(j * 800, rows_cnt)
            lines       = hoja1.loc[start:end - 1, "REGISTRO_TXT"].tolist()

            with open(file_path, "w", encoding="utf-8", newline="") as f:
                for k, line in enumerate(lines):
                    if k < len(lines) - 1:
                        f.write(line + "\n")
                    else:
                        f.write(line)
            print(f"  [{self.condicion}] TXT → {file_path.name} ({end - start} registros)")

        # 7. Exportar Excel opcional
        if export_excel:
            xlsx_path = run_dir / f"salida_reclamos_{fecha_proceso}.xlsx"
            with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
                hoja1.to_excel(writer, index=False, sheet_name="Hoja1")
                hoja1[["REGISTRO_TXT"]].to_excel(writer, index=False, sheet_name="Hoja2")

        # 8. Guardar correlativo
        ultimo_del_dia = (icorr + rows_cnt - 1) if rows_cnt > 0 else icorr - 1
        self._guardar_correlativo(ultimo_del_dia, fecha_proceso, journal_path.name)
        print(f"  [{self.condicion}] Correlativo final: {ultimo_del_dia}")

        return hoja1, run_dir, ultimo_del_dia

    # ── registro fixed-width 875 chars ──────────────────────

    def _build_registro_txt(
        self,
        df: pd.DataFrame,
        icorr: int,
        fechacarga: str,
        total_len: int = 875
    ) -> pd.Series:
        fc = _pad_right(fechacarga, 8, " ")
        registros = []

        for enum_idx, (_, row) in enumerate(df.iterrows()):
            correlativo = str(icorr + enum_idx).zfill(6)
            fecha8      = _pad_right(_to_str(row.get("Fecha Reclamo2", "")),    8, " ")
            fecha_txn8  = _pad_right(_to_str(row.get("Fecha Transacción", "")), 8, " ")
            hora6       = _zfill_digits(_to_str(row.get("HORA", "000000")), 6)
            bt15        = _pad_left(row.get("BT Correcta", row.get("BT", "")), 15, " ")
            tar         = _pad_left(row.get("Tarjeta", ""),                   128, " ")
            importe16   = "0" * 16
            moneda3     = "000"
            autoriz6    = " " * 6

            parts = [
                correlativo,        # 1)  6
                " " * 10,           # 2)  10
                " " * 12,           # 3)  12
                " " * 5,            # 4)  5
                fecha8,             # 5)  8
                "0" * 6,            # 6)  6
                " " * 200,          # 7)  200
                " " * 3,            # 8)  3
                " " * 2,            # 9)  2
                " " * 4 + "1",      # 10) 5   → " 821" ajustado a 5
                " 8750",            # 11) 5
                bt15,               # 12) 15
                tar,                # 13) 128
                fecha_txn8,         # 14) 8
                hora6,              # 15) 6   HORA
                importe16,          # 16) 16
                moneda3,            # 17) 3
                autoriz6,           # 18) 6
                "000",              # 19) 3
                "5",                # 20) 1
                "000",              # 21) 3
                " " * 200,          # 22) 200
                " " * 12,           # 23) 12
                "SBP",              # 24) 3
                fc,                 # 25) 8
                " " * 6,            # 26) 6
                " " * 1,            # 27) 1
                " " * 15,           # 28) 15
                " " * 19 + "N",     # 29) 20
                " " * 20,           # 30) 20
                " " * 20,           # 31) 20
                " " * 20,           # 32) 20
                " " * 20,           # 33) 20
                " " * 20,           # 34) 20
                " " * 20,           # 35) 20
                " " * 20,           # 36) 20
                " " * 19,           # 37) 19  ajuste → total 875
            ]

            registro = "".join(parts)
            if len(registro) < total_len:
                registro = registro.ljust(total_len, " ")
            elif len(registro) > total_len:
                registro = registro[:total_len]

            registros.append(registro)

        return pd.Series(registros, name="REGISTRO_TXT")

    # ── utilidades de carpeta y correlativo ─────────────────

    def _get_latest_excel(self, input_dir: Path) -> Path:
        files = sorted(
            [p for p in Path(input_dir).glob("*.xlsx") if not p.name.startswith("~$")],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not files:
            raise FileNotFoundError(f"No hay archivos .xlsx en: {input_dir}")
        return files[0]

    def _read_input(self, path: str) -> pd.DataFrame:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No existe: {path}")
        if p.suffix.lower() in [".xlsx", ".xls"]:
            return pd.read_excel(
                p,
                engine="openpyxl",
                dtype={
                    "ACF-ID Cliente": "string",
                    "ACF-Código Banco Destino Transf. Inmediata": "string",
                }
            )
        elif p.suffix.lower() in [".csv", ".txt"]:
            return pd.read_csv(p, sep=None, engine="python")
        raise ValueError(f"Formato no soportado: {p.suffix}")

    def _safe_empty_dir(self, folder: Path, pattern: str = "*.txt"):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for f in folder.glob(pattern):
            try:
                f.unlink()
            except PermissionError:
                try:
                    os.chmod(f, 0o200)
                    f.unlink()
                except Exception:
                    pass

    def _estado_path(self) -> Path:
        return self.export_dir / "_estado_correlativo.json"

    def _cargar_correlativo(self):
        p = self._estado_path()
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("ultimo_correlativo")
            return int(v) if v is not None else None
        except Exception:
            return None

    def _guardar_correlativo(self, ultimo: int, fecha_proceso: str, archivo_base: str):
        payload = {
            "ultimo_correlativo": int(ultimo),
            "fecha_proceso":      str(fecha_proceso),
            "archivo_base":       str(archivo_base),
            "actualizado_en":     datetime.now().isoformat(timespec="seconds"),
        }
        self._estado_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _obtener_icorr_siguiente(self) -> int:
        ultimo = self._cargar_correlativo()
        if ultimo is None:
            raise ValueError(
                f"[{self.condicion}] No existe _estado_correlativo.json. "
                f"Asegúrate de que el archivo JSON esté en: {self.export_dir}"
            )
        return ultimo + 1


# ============================================================
# CLASE 4: BitacoraComercio
# Acumula comercios por condición: histórico + ranking
# ============================================================

class BitacoraComercio:

    def __init__(self, ruta_bitacora: Path):
        self.ruta = Path(ruta_bitacora)

    def actualizar(self, grupos: dict, fecha_str: str):
        """
        grupos    : {"0424": df, "0622": df, ...}
        fecha_str : "24052026"
        """
        # Cargar histórico existente o empezar vacío
        if self.ruta.exists():
            historico = pd.read_excel(self.ruta, sheet_name="Historico", dtype=str)
        else:
            historico = pd.DataFrame(
                columns=["fecha", "condicion", "comercio", "cantidad"]
            )

        # Nuevas filas del día
        nuevas_filas = []
        for cod, df in grupos.items():
            col_comercio = self._encontrar_columna_comercio(df)
            if col_comercio is None:
                print(f"  [AVISO] No se encontró columna 'comercio' en condición {cod}")
                continue
            conteo = (
                df[col_comercio]
                .fillna("SIN_VALOR")
                .astype(str)
                .str.strip()
                .value_counts()
            )
            for comercio, cantidad in conteo.items():
                nuevas_filas.append({
                    "fecha":     fecha_str,
                    "condicion": cod,
                    "comercio":  comercio,
                    "cantidad":  cantidad,
                })

        if nuevas_filas:
            historico = pd.concat(
                [historico, pd.DataFrame(nuevas_filas)],
                ignore_index=True
            )

        # Resumen ranking
        historico["cantidad"] = pd.to_numeric(historico["cantidad"], errors="coerce").fillna(0)
        resumen = (
            historico
            .groupby(["condicion", "comercio"])["cantidad"]
            .sum()
            .reset_index(name="total_apariciones")
            .sort_values(["condicion", "total_apariciones"], ascending=[True, False])
        )
        resumen["rank"] = (
            resumen
            .groupby("condicion")["total_apariciones"]
            .rank(method="dense", ascending=False)
            .astype(int)
        )

        # Guardar
        with pd.ExcelWriter(self.ruta, engine='openpyxl') as writer:
            historico.to_excel(writer, index=False, sheet_name="Historico")
            resumen.to_excel(writer, index=False, sheet_name="Resumen")

        print(f"  Bitácora actualizada → {self.ruta.name}")
        print(f"  Top comercios hoy:")
        top = resumen.head(10)
        for _, row in top.iterrows():
            print(f"    [{row['condicion']}] #{int(row['rank'])} {row['comercio']} — {int(row['total_apariciones'])} veces")

    def _encontrar_columna_comercio(self, df: pd.DataFrame):
        for col in df.columns:
            low = col.lower()
            if 'comercio' in low or 'merchant' in low or 'establecimiento' in low:
                return col
        return None


# ============================================================
# CLASE 5: PipelineCondiciones — ORQUESTADOR
# La única clase que el usuario ejecuta
# ============================================================

class PipelineCondiciones:

    def __init__(self, ruta_excel: str, base_dir: str = None, fecha_str: str = None):
        self.ruta_excel = Path(ruta_excel)
        self.base_dir   = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        # Si se pasa --fecha se usa esa, si no se usa la fecha de hoy
        self.fecha_str  = fecha_str if fecha_str else datetime.today().strftime("%d%m%Y")

    def ejecutar(self):
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  PIPELINE CONDICIONES — {self.fecha_str}")
        print(f"{sep}")

        # ── PASO 1: Ingestar Excel ───────────────────────────
        print("\n[1/4] Ingestando Excel...")
        ingestor = IngestorExcel(self.ruta_excel)
        df = ingestor.ingestar()
        print(f"  Filas leídas: {len(df)}")

        # ── PASO 2: Separar por condición ────────────────────
        print("\n[2/4] Separando por condición...")
        separador = SeparadorCondiciones(df, self.base_dir, CONDICIONES)
        grupos    = separador.separar()
        print(f"  Condiciones encontradas: {list(grupos.keys())}")
        separador.exportar_a_carpetas(self.fecha_str)

        if not grupos:
            print("\n[AVISO] No se encontraron condiciones configuradas. Pipeline detenido.")
            return

        # ── PASO 3: Convertir a TXT por condición ────────────
        print("\n[3/4] Generando TXT para Monitor...")
        resultados = {}
        for cod in grupos.keys():
            carpeta    = self.base_dir / CONDICIONES[cod]["carpeta"]
            conversor  = ConvertidorMonitor(cod, carpeta)
            try:
                hoja1, run_dir, ultimo = conversor.procesar(
                    fechacarga    = self.fecha_str,
                    fecha_proceso = self.fecha_str,
                )
                resultados[cod] = {"ok": True, "ultimo": ultimo, "run_dir": run_dir}
            except Exception as e:
                print(f"  [{cod}] ERROR: {e}")
                resultados[cod] = {"ok": False, "error": str(e)}

        # ── PASO 4: Bitácora de comercios ────────────────────
        print("\n[4/4] Actualizando bitácora de comercios...")
        bitacora = BitacoraComercio(self.base_dir / "bitacora_comercios.xlsx")
        bitacora.actualizar(grupos, self.fecha_str)

        # ── Resumen final ────────────────────────────────────
        print(f"\n{sep}")
        print("  RESUMEN FINAL")
        print(f"{sep}")
        for cod, res in resultados.items():
            if res["ok"]:
                print(f"  ✓ [{cod}] OK — correlativo final: {res['ultimo']}")
            else:
                print(f"  ✗ [{cod}] FALLÓ — {res['error']}")
        print(f"{sep}\n")

        # Retorna datos para que automatizar.py pueda usarlos
        return {"grupos": grupos, "resultados": resultados}


# ============================================================
# EJECUCIÓN DIRECTA
# python pipeline_condiciones.py <ruta_excel> [--fecha DDMMYYYY]
# Ejemplos:
#   python pipeline_condiciones.py "Entrada\Archivo Base 24_05_26.xlsx"
#   python pipeline_condiciones.py "Entrada\Archivo Base 24_05_26.xlsx" --fecha 24052026
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pipeline de condiciones automatizadas — Scotiabank Perú"
    )
    parser.add_argument(
        "ruta_excel",
        help="Ruta al Excel de entrada (Archivo Base DD_MM_YY.xlsx)"
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha de proceso en formato DDMMYYYY (ej: 24052026). "
             "Si no se indica se usa la fecha de hoy."
    )
    args = parser.parse_args()

    pipeline = PipelineCondiciones(
        ruta_excel=args.ruta_excel,
        fecha_str=args.fecha
    )
    pipeline.ejecutar()
