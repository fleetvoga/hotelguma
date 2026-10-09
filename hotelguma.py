import os
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- MAKSIMALNO KOMPAKTAN LAYOUT ---
st.set_page_config(
    page_title="UNOS PODATAKA - HOTEL GUMA",
    page_icon="🚗",
    layout="wide"
)

st.markdown("""
<style>
.block-container {
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
    padding-left: 0.8rem;
    padding-right: 0.8rem;
}
div.stButton > button {
    font-weight: bold;
    padding: 0.2rem 0.6rem;
    font-size: 13px;
}
input {
    font-size: 12px !important;
}
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1VGGl13EhuhGu5LdYWxPzyuqAvRvP4PjpUyXrsirO48M"
WORKSHEET_NAME = "Sheet1"
PRICES_WORKSHEET_NAME = "Cenovnik"

FIELD_ORDER = [
    "id", "redniBroj", "placeno", "datum", "datumIzlaska", "brojDana", "trenutniObracun",
    "korisnik", "telefonKorisnika", "adresaKorisnika", "vlasnik", "telefonVlasnika",
    "brojTablica", "markaVozila", "modelVozila",
    "prednjaLevaDimenzija", "prednjaLevaMarka", "prednjaLevaModel", "prednjaLevaSezona", "prednjaLevaDOT", "prednjaLevaFelna", "prednjaLevaNapomena", "prednjaLevaLokacija",
    "prednjaDesnaDimenzija", "prednjaDesnaMarka", "prednjaDesnaModel", "prednjaDesnaSezona", "prednjaDesnaDOT", "prednjaDesnaFelna", "prednjaDesnaNapomena", "prednjaDesnaLokacija",
    "zadnjaLevaDimenzija", "zadnjaLevaMarka", "zadnjaLevaModel", "zadnjaLevaSezona", "zadnjaLevaDOT", "zadnjaLevaFelna", "zadnjaLevaNapomena", "zadnjaLevaLokacija",
    "zadnjaDesnaDimenzija", "zadnjaDesnaMarka", "zadnjaDesnaModel", "zadnjaDesnaSezona", "zadnjaDesnaDOT", "zadnjaDesnaFelna", "zadnjaDesnaNapomena", "zadnjaDesnaLokacija",
    "prednjaLevaDubinaSare", "prednjaDesnaDubinaSare", "zadnjaLevaDubinaSare", "zadnjaDesnaDubinaSare",
    "zimaDo19", "zimaDo19Felna", "zima20do22", "zima20do22Felna", "zimaPreko22", "zimaPreko22Felna",
    "letoDo19", "letoDo19Felna", "leto20do22", "leto20do22Felna", "letoPreko22", "letoPreko22Felna",
    "napomenaIzlaska"
]

def extract_inch(dim_text):
    if not dim_text:
        return None
    match = re.search(r'[rR](\d{2})', str(dim_text))
    if match:
        val = int(match.group(1))
        if 10 <= val <= 30:
            return val
    return None

def calculate_storage_cost(row, current_form_rates=None):
    record = dict(zip(FIELD_ORDER, row))
    current_form_rates = current_form_rates or {}

    def get_price(field_name, default_val):
        val = (record.get(field_name) or "").strip()
        if not val or val == "0":
            val = current_form_rates.get(field_name, str(default_val))
        try:
            return Decimal(str(val).replace(",", "."))
        except InvalidOperation:
            return Decimal(str(default_val))

    wheels = [
        ("prednjaLevaDimenzija", "prednjaLevaSezona", "prednjaLevaFelna"),
        ("prednjaDesnaDimenzija", "prednjaDesnaSezona", "prednjaDesnaFelna"),
        ("zadnjaLevaDimenzija", "zadnjaLevaSezona", "zadnjaLevaFelna"),
        ("zadnjaDesnaDimenzija", "zadnjaDesnaSezona", "zadnjaDesnaFelna"),
    ]

    total_cost = Decimal("0.00")
    for dim_field, sez_field, feln_field in wheels:
        dim_val = (record.get(dim_field) or "").strip()
        if not dim_val:
            continue
        inch = extract_inch(dim_val) or 16
        sezona = (record.get(sez_field) or "").strip().casefold()
        has_felna = (record.get(feln_field) or "").strip().casefold()
        is_felna = has_felna and has_felna not in ("ne", "false", "0")
        is_zima = "zima" in sezona or "zimsk" in sezona

        if is_zima:
            price = get_price("zimaDo19Felna" if is_felna else "zimaDo19", 1250.0 if is_felna else 1000.0)
        else:
            price = get_price("letoDo19Felna" if is_felna else "letoDo19", 1650.0 if is_felna else 1400.0)
        total_cost += price

    return {"total": total_cost.quantize(Decimal("0.01"))}

def normalize_sheet_id(sheet_id: str) -> str:
    value = (sheet_id or "").strip()
    if "/d/" in value:
        value = value.split("/d/")[1].split("/")[0]
    return value

def sheet_column_name(column_number):
    name = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        name = chr(65 + remainder) + name
    return name

@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            return gspread.authorize(creds)
    except Exception:
        pass
    local_json_file = "my-project-app-508706-9e92b577fcb8.json"
    if os.path.exists(local_json_file):
        creds = Credentials.from_service_account_file(local_json_file, scopes=scope)
        return gspread.authorize(creds)
    return None

def get_worksheet(name=WORKSHEET_NAME):
    client = get_gspread_client()
    if not client:
        return None
    try:
        spreadsheet = client.open_by_key(normalize_sheet_id(SHEET_ID))
        try:
            return spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=name, rows=100, cols=20)
    except Exception:
        return None

def ensure_sheet_headers():
    ws = get_worksheet(WORKSHEET_NAME)
    if not ws:
        return None
    rows = ws.get_all_values()
    if not rows:
        ws.update(range_name=f"A1:{sheet_column_name(len(FIELD_ORDER))}1", values=[FIELD_ORDER], value_input_option="RAW")
    return ws

def get_saved_records():
    ws = ensure_sheet_headers()
    if not ws:
        return []
    try:
        rows = ws.get_all_values()[1:]
        records = []
        for row_number, row in enumerate(rows, start=2):
            values = row[:len(FIELD_ORDER)]
            if any(str(value).strip() for value in values):
                padded = values + [""] * (len(FIELD_ORDER) - len(values))
                if padded[FIELD_ORDER.index("id")].strip().isdigit():
                    records.append((row_number, padded))
        return list(reversed(records))
    except Exception:
        return []

def load_prices_from_cloud():
    default = {"zimaDo19": "1000", "zimaDo19Felna": "1250", "letoDo19": "1400", "letoDo19Felna": "1650", "datumIzmene": "Danas"}
    try:
        ws = get_worksheet(PRICES_WORKSHEET_NAME)
        if ws:
            data = ws.get_all_values()
            if len(data) >= 2:
                default.update({k: v for k, v in dict(zip(data[0], data[1])).items() if v})
    except Exception:
        pass
    return default

def append_row_to_sheet(row_values):
    ws = ensure_sheet_headers()
    row_num = len(ws.get_all_values()) + 1
    row_values[FIELD_ORDER.index("id")] = row_num
    ws.update(range_name=f"A{row_num}:{sheet_column_name(len(FIELD_ORDER))}{row_num}", values=[row_values], value_input_option="RAW")
    return row_num

# --- GLAVNI EKRAN ---
st.markdown("### UNOS PODATAKA - HOTEL GUMA")
saved_prices = load_prices_from_cloud()
records = get_saved_records()

with st.form("compact_form"):
    c_osn, c_pl, c_pd, c_zl, c_zd, c_cen = st.columns([2.2, 1.9, 1.9, 1.9, 1.9, 2.0], gap="small")

    with c_osn:
        st.markdown("**Osnovni podaci**")
        redni_broj = st.text_input("R.br", value="1", label_visibility="collapsed", placeholder="R.br")
        datum = st.text_input("Datum", value=datetime.now().strftime("%d.%m.%Y"), label_visibility="collapsed", placeholder="Datum (09.10.2026)")
        datum_izlaska = st.text_input("Datum izlaska", label_visibility="collapsed", placeholder="Datum izlaska")
        korisnik = st.text_input("Korisnik", label_visibility="collapsed", placeholder="Ime korisnika")
        telefon_korisnika = st.text_input("Tel", label_visibility="collapsed", placeholder="Telefon korisnika")
        adresa_korisnika = st.text_input("Adresa", label_visibility="collapsed", placeholder="Adresa")
        vlasnik = st.text_input("Vlasnik", label_visibility="collapsed", placeholder="Vlasnik vozila")
        telefon_vlasnika = st.text_input("Tel vlasnika", label_visibility="collapsed", placeholder="Tel. vlasnika")
        broj_tablica = st.text_input("Tablice", label_visibility="collapsed", placeholder="Broj tablica")
        marka_vozila = st.text_input("Marka", label_visibility="collapsed", placeholder="Marka vozila")
        model_vozila = st.text_input("Model", label_visibility="collapsed", placeholder="Model vozila")

    def compact_tire_inputs(name):
        st.markdown(f"**{name}**")
        dim = st.text_input(f"Dim {name}", label_visibility="collapsed", placeholder="225/45R17")
        marka = st.text_input(f"Marka {name}", label_visibility="collapsed", placeholder="Marka gume")
        model = st.text_input(f"Model {name}", label_visibility="collapsed", placeholder="Model gume")
        sezona = st.selectbox(f"Sezona {name}", ["", "ZIMSKA", "LETNJA", "ALLSEASON"], label_visibility="collapsed")
        dot = st.text_input(f"DOT {name}", label_visibility="collapsed", placeholder="DOT")
        sara = st.text_input(f"Sara {name}", label_visibility="collapsed", placeholder="Šara (mm)")
        felna = st.checkbox(f"Felna {name}")
        napomena = st.text_input(f"Nap {name}", label_visibility="collapsed", placeholder="Napomena")
        return dim, marka, model, sezona, dot, sara, felna, napomena

    with c_pl:
        pl_dim, pl_mar, pl_mod, pl_sez, pl_dot, pl_sar, pl_fel, pl_nap = compact_tire_inputs("Prednja leva")
    with c_pd:
        pd_dim, pd_mar, pd_mod, pd_sez, pd_dot, pd_sar, pd_fel, pd_nap = compact_tire_inputs("Prednja desna")
    with c_zl:
        zl_dim, zl_mar, zl_mod, zl_sez, zl_dot, zl_sar, zl_fel, zl_nap = compact_tire_inputs("Zadnja leva")
    with c_zd:
        zd_dim, zd_mar, zd_mod, zd_sez, zd_dot, zd_sar, zd_fel, zd_nap = compact_tire_inputs("Zadnja desna")

    with c_cen:
        st.markdown("**Cenovnik**")
        zima19 = st.text_input("Z19", value=saved_prices.get("zimaDo19", "1000"), label_visibility="collapsed", placeholder="Zima do 19")
        zima19f = st.text_input("Z19f", value=saved_prices.get("zimaDo19Felna", "1250"), label_visibility="collapsed", placeholder="Zima do 19 (felna)")
        leto19 = st.text_input("L19", value=saved_prices.get("letoDo19", "1400"), label_visibility="collapsed", placeholder="Leto do 19")
        leto19f = st.text_input("L19f", value=saved_prices.get("letoDo19Felna", "1650"), label_visibility="collapsed", placeholder="Leto do 19 (felna)")
        napomena_izlaska = st.text_area("Opšta napomena", label_visibility="collapsed", placeholder="Napomena...", height=68)
        placeno = st.checkbox("Plaćeno")

    st.markdown("---")
    b1, b2, b3, b4 = st.columns([1, 1, 1.5, 3])
    with b1:
        submit_btn = st.form_submit_button("Sačuvaj")
    with b2:
        clear_btn = st.form_submit_button("Obriši")
    with b4:
        search_query = st.text_input("Pretraga", label_visibility="collapsed", placeholder="Pretraži unose...")

    if submit_btn:
        row_vals = [""] * len(FIELD_ORDER)
        data_dict = {
            "redniBroj": redni_broj, "placeno": "Da" if placeno else "Ne", "datum": datum, "datumIzlaska": datum_izlaska,
            "korisnik": korisnik, "telefonKorisnika": telefon_korisnika, "adresaKorisnika": adresa_korisnika,
            "vlasnik": vlasnik, "telefonVlasnika": telefon_vlasnika, "brojTablica": broj_tablica,
            "markaVozila": marka_vozila, "modelVozila": model_vozila, "napomenaIzlaska": napomena_izlaska,
            "prednjaLevaDimenzija": pl_dim, "prednjaLevaMarka": pl_mar, "prednjaLevaModel": pl_mod, "prednjaLevaSezona": pl_sez, "prednjaLevaDOT": pl_dot, "prednjaLevaFelna": "Da" if pl_fel else "Ne", "prednjaLevaNapomena": pl_nap, "prednjaLevaDubinaSare": pl_sar,
            "prednjaDesnaDimenzija": pd_dim, "prednjaDesnaMarka": pd_mar, "prednjaDesnaModel": pd_mod, "prednjaDesnaSezona": pd_sez, "prednjaDesnaDOT": pd_dot, "prednjaDesnaFelna": "Da" if pd_fel else "Ne", "prednjaDesnaNapomena": pd_nap, "prednjaDesnaDubinaSare": pd_sar,
            "zadnjaLevaDimenzija": zl_dim, "zadnjaLevaMarka": zl_mar, "zadnjaLevaModel": zl_mod, "zadnjaLevaSezona": zl_sez, "zadnjaLevaDOT": zl_dot, "zadnjaLevaFelna": "Da" if zl_fel else "Ne", "zadnjaLevaNapomena": zl_nap, "zadnjaLevaDubinaSare": zl_sar,
            "zadnjaDesnaDimenzija": zd_dim, "zadnjaDesnaMarka": zd_mar, "zadnjaDesnaModel": zd_mod, "zadnjaDesnaSezona": zd_sez, "zadnjaDesnaDOT": zd_dot, "zadnjaDesnaFelna": "Da" if zd_felna else "Ne", "zadnjaDesnaNapomena": zd_nap, "zadnjaDesnaDubinaSare": zd_sar,
        }
        data_dict.update(saved_prices)
        for i, fn in enumerate(FIELD_ORDER):
            row_vals[i] = data_dict.get(fn, "")
        try:
            append_row_to_sheet(row_vals)
            st.success("Sačuvano!")
        except Exception as e:
            st.error(f"Greška: {e}")

st.markdown("### Pregled unosa")
if records:
    t_rows = []
    for r_num, row in records:
        r_dict = dict(zip(FIELD_ORDER, row))
        if search_query and not any(search_query.casefold() in str(v).casefold() for v in row):
            continue
        calc = calculate_storage_cost(row, current_form_rates=saved_prices)
        t_rows.append({
            "ID": r_dict.get("id"), "R.br": r_dict.get("redniBroj"), "Plaćeno": r_dict.get("placeno"),
            "Prijem": r_dict.get("datum"), "Obračun RSD": f"{calc['total']:.2f}",
            "Korisnik": r_dict.get("korisnik"), "Tablice": r_dict.get("brojTablica"),
            "Vozilo": f"{r_dict.get('markaVozila')} {r_dict.get('modelVozila')}",
            "PL Dim": r_dict.get("prednjaLevaDimenzija"), "PD Dim": r_dict.get("prednjaDesnaDimenzija")
        })
    st.dataframe(t_rows, use_container_width=True)
else:
    st.info("Nema sačuvanih unosa.")
    