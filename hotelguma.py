import os
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- KONFIGURACIJA STRANICE ---
st.set_page_config(
    page_title="Hotel Guma - Web Aplikacija",
    page_icon="🚗",
    layout="wide"
)

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

# --- INTERFEJS APLIKACIJE ---
st.title("🚗 Hotel Guma - Upravljanje i Čuvanje Pneumatika")

saved_prices = load_prices_from_cloud()
records = get_saved_records()

tab1, tab2, tab3 = st.tabs(["Unos i Izmena", "Cenovnik", "Pregled unosa"])

with tab1:
    st.subheader("Glavna forma za prijem pneumatika")
    
    with st.form("hotel_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            korisnik = st.text_input("Korisnik")
            telefon_korisnika = st.text_input("Telefon korisnika")
            adresa_korisnika = st.text_input("Adresa korisnika")
        with col2:
            vlasnik = st.text_input("Vlasnik vozila")
            telefon_vlasnika = st.text_input("Telefon vlasnika")
            broj_tablica = st.text_input("Broj tablica")
        with col3:
            marka_vozila = st.text_input("Marka vozila")
            model_vozila = st.text_input("Model vozila")
            datum_prijema = st.text_input("Datum prijema", value=datetime.now().strftime("%d.%m.%Y"))
            placeno = st.checkbox("Plaćeno")

        st.divider()
        st.markdown("### Pozicije pneumatika (Dimenzije, Marka, Model, Sezona, DOT, Šara, Felna, Lokacija)")

        positions = [
            ("Prednja leva", "prednjaLeva"),
            ("Prednja desna", "prednjaDesna"),
            ("Zadnja leva", "zadnjaLeva"),
            ("Zadnja desna", "zadnjaDesna"),
        ]

        form_data = {}
        for title, prefix in positions:
            st.markdown(f"**{title}**")
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
            form_data[f"{prefix}Dimenzija"] = c1.text_input(f"Dim. ({prefix})", placeholder="225/55R17")
            form_data[f"{prefix}Marka"] = c2.text_input(f"Marka ({prefix})")
            form_data[f"{prefix}Model"] = c3.text_input(f"Model ({prefix})")
            form_data[f"{prefix}Sezona"] = c4.selectbox(f"Sezona ({prefix})", ["", "ZIMSKA", "LETNJA", "ALLSEASON"])
            form_data[f"{prefix}DOT"] = c5.text_input(f"DOT ({prefix})")
            form_data[f"{prefix}DubinaSare"] = c6.text_input(f"Šara mm ({prefix})")
            form_data[f"{prefix}Felna"] = c7.checkbox(f"Felna ({prefix})")
            form_data[f"{prefix}Lokacija"] = c8.text_input(f"Lokacija ({prefix})")
            form_data[f"{prefix}Napomena"] = st.text_input(f"Napomena ({prefix})")

        st.divider()
        napomena_izlaska = st.text_area("Napomena izlaska / Opšta napomena")

        submitted = st.form_submit_button("Spremi podatke u Google Sheet")
        if submitted:
            new_row = [""] * len(FIELD_ORDER)
            r_dict = {
                "redniBroj": "1",
                "placeno": "Da" if placeno else "Ne",
                "datum": datum_prijema,
                "korisnik": korisnik,
                "telefonKorisnika": telefon_korisnika,
                "adresaKorisnika": adresa_korisnika,
                "vlasnik": vlasnik,
                "telefonVlasnika": telefon_vlasnika,
                "brojTablica": broj_tablica,
                "markaVozila": marka_vozila,
                "modelVozila": model_vozila,
                "napomenaIzlaska": napomena_izlaska,
            }
            r_dict.update(form_data)
            r_dict.update(saved_prices)

            for i, f_name in enumerate(FIELD_ORDER):
                new_row[i] = r_dict.get(f_name, "")

            try:
                append_row_to_sheet(new_row)
                st.success("Podaci su uspješno spremljeni!")
            except Exception as e:
                st.error(f"Greška pri spremanju: {e}")

with tab2:
    st.subheader("Cenovnik skladištenja")
    with st.form("price_form"):
        col1, col2 = st.columns(2)
        new_prices = dict(saved_prices)
        
        season_fields_labels = [
            ("zimaDo19", "zimaDo19Felna", "Zima do 19\""),
            ("zima20do22", "zima20do22Felna", "Zima 20-22\""),
            ("zimaPreko22", "zimaPreko22Felna", "Zima preko 22\""),
            ("letoDo19", "letoDo19Felna", "Leto do 19\""),
            ("leto20do22", "leto20do22Felna", "Leto 20-22\""),
            ("letoPreko22", "letoPreko22Felna", "Leto preko 22\""),
        ]
        
        for b_name, f_name, lbl in season_fields_labels:
            with col1:
                new_prices[b_name] = st.text_input(f"{lbl} (Bez felne)", value=saved_prices.get(b_name, ""))
            with col2:
                new_prices[f_name] = st.text_input(f"{lbl} (Sa felnom)", value=saved_prices.get(f_name, ""))
                
        if st.form_submit_button("Ažuriraj cenovnik"):
            save_prices_to_cloud(new_prices)
            st.success("Cenovnik je uspješno ažuriran na cloudu!")

with tab3:
    st.subheader("Pregled i pretraga unosa")
    search_query = st.text_input("Pretraži po tablicama, korisniku ili vozilu:")
    
    if records:
        table_data = []
        for row_num, row in records:
            r_dict = dict(zip(FIELD_ORDER, row))
            if search_query and not any(search_query.casefold() in str(v).casefold() for v in row):
                continue
            calc = calculate_storage_cost(row, current_form_rates=saved_prices)
            table_data.append({
                "Redni broj": r_dict.get("redniBroj"),
                "Datum": r_dict.get("datum"),
                "Korisnik": r_dict.get("korisnik"),
                "Telefon": r_dict.get("telefonKorisnika"),
                "Tablice": r_dict.get("brojTablica"),
                "Vozilo": f"{r_dict.get('markaVozila')} {r_dict.get('modelVozila')}",
                "Ukupno RSD": f"{calc['total']:.2f}"
            })
        if table_data:
            st.dataframe(table_data, use_container_width=True)
        else:
            st.info("Nema rezultata za zadanu pretragu.")
    else:
        st.warning("Nema unosa u bazi.")