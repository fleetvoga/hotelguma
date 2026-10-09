import os
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- KONFIGURACIJA STRANICE (ŠIROKI PRIKAZ) ---
st.set_page_config(
    page_title="UNOS PODATAKA - HOTEL GUMA",
    page_icon="🚗",
    layout="wide"
)

# --- CSS STILOVI ZA FLEKSIBILAN RASPORED ---
st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
    padding-left: 1rem;
    padding-right: 1rem;
}
div.stButton > button {
    font-weight: bold;
    padding: 0.3rem 0.8rem;
}
</style>
""", unsafe_allow_html=True)

# --- DEFINICIJE I KONSTANTE ---
SHEET_ID = "1VGGl13EhuhGu5LdYWxPzyuqAvRvP4PjpUyXrsirO48M"
WORKSHEET_NAME = "Sheet1"
PRICES_WORKSHEET_NAME = "Cenovnik"

FIELD_ORDER = [
    "id",
    "redniBroj",
    "placeno",
    "datum",
    "datumIzlaska",
    "brojDana",
    "trenutniObracun",
    "korisnik",
    "telefonKorisnika",
    "adresaKorisnika",
    "vlasnik",
    "telefonVlasnika",
    "brojTablica",
    "markaVozila",
    "modelVozila",
    "prednjaLevaDimenzija",
    "prednjaLevaMarka",
    "prednjaLevaModel",
    "prednjaLevaSezona",
    "prednjaLevaDOT",
    "prednjaLevaFelna",
    "prednjaLevaNapomena",
    "prednjaDesnaDimenzija",
    "prednjaDesnaMarka",
    "prednjaDesnaModel",
    "prednjaDesnaSezona",
    "prednjaDesnaDOT",
    "prednjaDesnaFelna",
    "prednjaDesnaNapomena",
    "zadnjaLevaDimenzija",
    "zadnjaLevaMarka",
    "zadnjaLevaModel",
    "zadnjaLevaSezona",
    "zadnjaLevaDOT",
    "zadnjaLevaFelna",
    "zadnjaLevaNapomena",
    "zadnjaDesnaDimenzija",
    "zadnjaDesnaMarka",
    "zadnjaDesnaModel",
    "zadnjaDesnaSezona",
    "zadnjaDesnaDOT",
    "zadnjaDesnaFelna",
    "zadnjaDesnaNapomena",
    "prednjaLevaDubinaSare",
    "prednjaDesnaDubinaSare",
    "zadnjaLevaDubinaSare",
    "zadnjaDesnaDubinaSare",
    "prednjaLevaLokacija",
    "prednjaDesnaLokacija",
    "zadnjaLevaLokacija",
    "zadnjaDesnaLokacija",
    "zimaDo19", "zimaDo19Felna",
    "zima20do22", "zima20do22Felna",
    "zimaPreko22", "zimaPreko22Felna",
    "letoDo19", "letoDo19Felna",
    "leto20do22", "leto20do22Felna",
    "letoPreko22", "letoPreko22Felna",
    "napomenaIzlaska",
]

# --- POMOĆNE FUNKCIJE ---
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
    active_tires = 0

    for dim_field, sez_field, feln_field in wheels:
        dim_val = (record.get(dim_field) or "").strip()
        if not dim_val:
            continue
        active_tires += 1
        inch = extract_inch(dim_val) or 16
        sezona = (record.get(sez_field) or "").strip().casefold()
        has_felna = (record.get(feln_field) or "").strip().casefold()
        is_felna = has_felna and has_felna not in ("ne", "false", "0", "ne")

        is_zima = "zima" in sezona or "zimsk" in sezona

        if is_zima:
            if inch <= 19:
                base_f, feln_f = "zimaDo19", "zimaDo19Felna"
                def_b, def_fb = 1000.0, 1250.0
            elif inch <= 22:
                base_f, feln_f = "zima20do22", "zima20do22Felna"
                def_b, def_fb = 1200.0, 1450.0
            else:
                base_f, feln_f = "zimaPreko22", "zimaPreko22Felna"
                def_b, def_fb = 1300.0, 1550.0
        else:
            if inch <= 19:
                base_f, feln_f = "letoDo19", "letoDo19Felna"
                def_b, def_fb = 1400.0, 1650.0
            elif inch <= 22:
                base_f, feln_f = "leto20do22", "leto20do22Felna"
                def_b, def_fb = 1680.0, 1930.0
            else:
                base_f, feln_f = "letoPreko22", "letoPreko22Felna"
                def_b, def_fb = 1820.0, 2070.0

        if is_felna:
            price = get_price(feln_f, def_fb)
        else:
            price = get_price(base_f, def_b)

        total_cost += price

    return {
        "total": total_cost.quantize(Decimal("0.01")),
        "tire_count": active_tires
    }

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
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
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
    sheet_id = normalize_sheet_id(SHEET_ID)
    try:
        spreadsheet = client.open_by_key(sheet_id)
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
    last_column = sheet_column_name(len(FIELD_ORDER))
    if not rows:
        ws.update(range_name=f"A1:{last_column}1", values=[FIELD_ORDER], value_input_option="RAW")
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
                padded_values = values + [""] * (len(FIELD_ORDER) - len(values))
                id_val = padded_values[FIELD_ORDER.index("id")].strip()
                if not id_val.isdigit():
                    continue
                records.append((row_number, padded_values))
        return list(reversed(records))
    except Exception:
        return []

def load_prices_from_cloud():
    default_prices = {
        "zimaDo19": "1000.00", "zimaDo19Felna": "1250.00",
        "zima20do22": "1200.00", "zima20do22Felna": "1450.00",
        "zimaPreko22": "1300.00", "zimaPreko22Felna": "1550.00",
        "letoDo19": "1400.00", "letoDo19Felna": "1650.00",
        "leto20do22": "1680.00", "leto20do22Felna": "1930.00",
        "letoPreko22": "1820.00", "letoPreko22Felna": "2070.00",
        "datumIzmene": datetime.now().strftime("%d.%m.%Y")
    }
    try:
        ws = get_worksheet(PRICES_WORKSHEET_NAME)
        if ws:
            data = ws.get_all_values()
            if len(data) >= 2:
                cloud_prices = dict(zip(data[0], data[1]))
                if "datumIzmene" in cloud_prices:
                    default_prices.update({k: v for k, v in cloud_prices.items() if v != ""})
    except Exception:
        pass
    return default_prices

def save_prices_to_cloud(prices_dict):
    prices_dict["datumIzmene"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    ws = get_worksheet(PRICES_WORKSHEET_NAME)
    if ws:
        headers = list(prices_dict.keys())
        values = list(prices_dict.values())
        ws.clear()
        ws.update(range_name="A1", values=[headers, values], value_input_option="RAW")

def append_row_to_sheet(row_values):
    ws = ensure_sheet_headers()
    if not ws:
        raise Exception("Nema konekcije sa Google Sheet-om.")
    all_vals = ws.get_all_values()
    row_number = len(all_vals) + 1
    last_column = sheet_column_name(len(FIELD_ORDER))
    row_values = list(row_values)
    row_values[FIELD_ORDER.index("id")] = row_number
    ws.update(
        range_name=f"A{row_number}:{last_column}{row_number}",
        values=[row_values],
        value_input_option="RAW",
    )
    return row_number

# --- GLAVNI PROZOR ---
st.markdown("### UNOS PODATAKA - HOTEL GUMA")

saved_prices = load_prices_from_cloud()
records = get_saved_records()

with st.form("main_entry_form"):
    # 6 kolona u gornjem redu: Osnovni podaci, 4 točka, Cenovnik/Napomena
    col_osnovni, col_pl, col_pd, col_zl, col_zd, col_cen = st.columns([2.2, 1.9, 1.9, 1.9, 1.9, 2.0])

    with col_osnovni:
        st.markdown("**Osnovni podaci**")
        rec_id = st.text_input("ID", value="", disabled=True)
        redni_broj = st.text_input("R.br", value="1")
        datum = st.text_input("Datum", value=datetime.now().strftime("%d.%m.%Y"))
        datum_izlaska = st.text_input("Datum izlaska", value="")
        korisnik = st.text_input("Korisnik")
        telefon_korisnika = st.text_input("Tel.korisnika")
        adresa_korisnika = st.text_input("Adresa")
        vlasnik = st.text_input("Vlasnik")
        telefon_vlasnika = st.text_input("Tel.vlasnika")
        broj_tablica = st.text_input("Tablice")
        marka_vozila = st.text_input("Marka")
        model_vozila = st.text_input("Model")

    def render_tire_column(title, prefix):
        st.markdown(f"**{title}**")
        dim = st.text_input(f"Dimenzija ({prefix})", placeholder="širina/visinaRprečnik")
        marka = st.text_input(f"Marka ({prefix})")
        model = st.text_input(f"Model ({prefix})")
        sezona = st.selectbox(f"Sezona ({prefix})", ["", "ZIMSKA", "LETNJA", "ALLSEASON"])
        dot = st.text_input(f"DOT ({prefix})")
        sara = st.text_input(f"Šara mm ({prefix})")
        felna = st.checkbox(f"Felna ({prefix})")
        napomena = st.text_input(f"Napomena ({prefix})")
        lokacija = st.text_input(f"Lokacija ({prefix})")
        return dim, marka, model, sezona, dot, sara, felna, napomena, lokacija

    with col_pl:
        pl_dim, pl_marka, pl_model, pl_sezona, pl_dot, pl_sara, pl_felna, pl_nap, pl_lok = render_tire_column("Prednja leva", "pl")

    with col_pd:
        pd_dim, pd_marka, pd_model, pd_sezona, pd_dot, pd_sara, pd_felna, pd_nap, pd_lok = render_tire_column("Prednja desna", "pd")

    with col_zl:
        zl_dim, zl_marka, zl_model, zl_sezona, zl_dot, zl_sara, zl_felna, zl_nap, zl_lok = render_tire_column("Zadnja leva", "zl")

    with col_zd:
        zd_dim, zd_marka, zd_model, zd_sezona, zd_dot, zd_sara, zd_felna, zd_nap, zd_lok = render_tire_column("Zadnja desna", "zd")

    with col_cen:
        st.markdown("**Cenovnik čuvanja**")
        st.caption(f"Ažurirano: {saved_prices.get('datumIzmene', '-')}")
        zima19 = st.text_input("Zima do 19\"", value=saved_prices.get("zimaDo19", "1000"))
        zima19f = st.text_input("Zima do 19\" (f)", value=saved_prices.get("zimaDo19Felna", "1250"))
        zima22 = st.text_input("Zima 20-22\"", value=saved_prices.get("zima20do22", "1200"))
        zima22f = st.text_input("Zima 20-22\" (f)", value=saved_prices.get("zima20do22Felna", "1450"))
        leto19 = st.text_input("Leto do 19\"", value=saved_prices.get("letoDo19", "1400"))
        leto19f = st.text_input("Leto do 19\" (f)", value=saved_prices.get("letoDo19Felna", "1650"))
        
        st.markdown("**Napomena**")
        napomena_izlaska = st.text_area("Opšta napomena", height=60)
        placeno = st.checkbox("Plaćeno")

    st.divider()

    # --- KONTROLNI GUMBI ---
    b_col1, b_col2, b_col3, b_col4, b_col5, b_col6, b_col7 = st.columns([1, 1, 1.2, 1.5, 1.5, 2, 2])
    with b_col1:
        submit_btn = st.form_submit_button("Sačuvaj")
    with b_col2:
        clear_btn = st.form_submit_button("Obriši")
    with b_col3:
        cenovnik_btn = st.form_submit_button("Cenovnik")
    with b_col4:
        sheet_btn = st.form_submit_button("Otvori Google Sheet")
    with b_col5:
        search_query = st.text_input("Pretraga", placeholder="Unesi pojam...")

    if submit_btn:
        new_row = [""] * len(FIELD_ORDER)
        r_dict = {
            "redniBroj": redni_broj,
            "placeno": "Da" if placeno else "Ne",
            "datum": datum,
            "datumIzlaska": datum_izlaska,
            "korisnik": korisnik,
            "telefonKorisnika": telefon_korisnika,
            "adresaKorisnika": adresa_korisnika,
            "vlasnik": vlasnik,
            "telefonVlasnika": telefon_vlasnika,
            "brojTablica": broj_tablica,
            "markaVozila": marka_vozila,
            "modelVozila": model_vozila,
            "prednjaLevaDimenzija": pl_dim, "prednjaLevaMarka": pl_marka, "prednjaLevaModel": pl_model, "prednjaLevaSezona": pl_sezona, "prednjaLevaDOT": pl_dot, "prednjaLevaDubinaSare": pl_sara, "prednjaLevaFelna": "Da" if pl_felna else "Ne", "prednjaLevaNapomena": pl_nap, "prednjaLevaLokacija": pl_lok,
            "prednjaDesnaDimenzija": pd_dim, "prednjaDesnaMarka": pd_marka, "prednjaDesnaModel": pd_model, "prednjaDesnaSezona": pd_sezona, "prednjaDesnaDOT": pd_dot, "prednjaDesnaDubinaSare": pd_sara, "prednjaDesnaFelna": "Da" if pd_felna else "Ne", "prednjaDesnaNapomena": pd_nap, "prednjaDesnaLokacija": pd_lok,
            "zadnjaLevaDimenzija": zl_dim, "zadnjaLevaMarka": zl_marka, "zadnjaLevaModel": zl_model, "zadnjaLevaSezona": zl_sezona, "zadnjaLevaDOT": zl_dot, "zadnjaLevaDubinaSare": zl_sara, "zadnjaLevaFelna": "Da" if zl_felna else "Ne", "zadnjaLevaNapomena": zl_nap, "zadnjaLevaLokacija": zl_lok,
            "zadnjaDesnaDimenzija": zd_dim, "zadnjaDesnaMarka": zd_marka, "zadnjaDesnaModel": zd_model, "zadnjaDesnaSezona": zd_sezona, "zadnjaDesnaDOT": zd_dot, "zadnjaDesnaDubinaSare": zd_sara, "zadnjaDesnaFelna": "Da" if zd_felna else "Ne", "zadnjaDesnaNapomena": zd_nap, "zadnjaDesnaLokacija": zd_lok,
            "napomenaIzlaska": napomena_izlaska,
            "zimaDo19": zima19, "zimaDo19Felna": zima19f, "zima20do22": zima22, "zima20do22Felna": zima22f,
        }
        r_dict.update(saved_prices)
        for i, f_name in enumerate(FIELD_ORDER):
            new_row[i] = r_dict.get(f_name, "")
        try:
            append_row_to_sheet(new_row)
            st.success("Uspešno sačuvano u Google Sheet!")
        except Exception as e:
            st.error(f"Greška: {e}")

# --- PREGLED UNOSA (TABLICA NA DNU) ---
st.markdown("### Pregled unosa")
if records:
    table_rows = []
    for row_num, row in records:
        r_dict = dict(zip(FIELD_ORDER, row))
        if search_query and not any(search_query.casefold() in str(v).casefold() for v in row):
            continue
        calc = calculate_storage_cost(row, current_form_rates=saved_prices)
        table_rows.append({
            "ID": r_dict.get("id"),
            "R.br": r_dict.get("redniBroj"),
            "Plaćeno": r_dict.get("placeno"),
            "Prijem": r_dict.get("datum"),
            "Izlaz": r_dict.get("datumIzlaska"),
            "Obračun RSD": f"{calc['total']:.2f}",
            "Korisnik": r_dict.get("korisnik"),
            "Tel.kor": r_dict.get("telefonKorisnika"),
            "Tablice": r_dict.get("brojTablica"),
            "Marka": r_dict.get("markaVozila"),
            "Model": r_dict.get("modelVozila"),
            "PL Dim": r_dict.get("prednjaLevaDimenzija"),
            "PD Dim": r_dict.get("prednjaDesnaDimenzija"),
        })
    st.dataframe(table_rows, use_container_width=True)
else:
    st.info("Nema sačuvanih unosa u tabeli.")