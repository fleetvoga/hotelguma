import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import gradio as gr
import gspread
from google.oauth2.service_account import Credentials

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
        is_felna = has_felna and has_felna not in ("ne", "false", "0", "False")
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

        total_cost += get_price(feln_f, def_fb) if is_felna else get_price(base_f, def_b)

    return total_cost.quantize(Decimal("0.01"))

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

def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
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
    default = {
        "zimaDo19": "1000.00", "zimaDo19Felna": "1250.00",
        "zima20do22": "1200.00", "zima20do22Felna": "1450.00",
        "zimaPreko22": "1300.00", "zimaPreko22Felna": "1550.00",
        "letoDo19": "1400.00", "letoDo19Felna": "1650.00",
        "leto20do22": "1680.00", "leto20do22Felna": "1930.00",
        "letoPreko22": "1820.00", "letoPreko22Felna": "2070.00"
    }
    try:
        ws = get_worksheet(PRICES_WORKSHEET_NAME)
        if ws:
            data = ws.get_all_values()
            if len(data) >= 2:
                default.update({k: v for k, v in dict(zip(data[0], data[1])).items() if v})
    except Exception:
        pass
    return default

saved_prices = load_prices_from_cloud()

def save_entry(*args):
    row_vals = [""] * len(FIELD_ORDER)
    # Mapiramo argumente iz Gradio forme u red za Sheet
    data_dict = dict(zip(FIELD_ORDER[1:], args[:-1])) # Zadnji je edit_id ako postoji
    edit_id = args[-1]
    
    data_dict["placeno"] = "Da" if data_dict.get("placeno") else "Ne"
    data_dict["prednjaLevaFelna"] = "Da" if data_dict.get("prednjaLevaFelna") else "Ne"
    data_dict["prednjaDesnaFelna"] = "Da" if data_dict.get("prednjaDesnaFelna") else "Ne"
    data_dict["zadnjaLevaFelna"] = "Da" if data_dict.get("zadnjaLevaFelna") else "Ne"
    data_dict["zadnjaDesnaFelna"] = "Da" if data_dict.get("zadnjaDesnaFelna") else "Ne"

    for i, fn in enumerate(FIELD_ORDER):
        if fn == "id":
            continue
        row_vals[i] = str(data_dict.get(fn, ""))

    ws = ensure_sheet_headers()
    try:
        if edit_id and str(edit_id).strip().isdigit():
            row_num = int(edit_id)
            row_vals[FIELD_ORDER.index("id")] = row_num
            ws.update(range_name=f"A{row_num}:{sheet_column_name(len(FIELD_ORDER))}{row_num}", values=[row_vals], value_input_option="RAW")
            msg = "Izmene uspešno sačuvane!"
        else:
            row_num = len(ws.get_all_values()) + 1
            row_vals[FIELD_ORDER.index("id")] = row_num
            ws.update(range_name=f"A{row_num}:{sheet_column_name(len(FIELD_ORDER))}{row_num}", values=[row_vals], value_input_option="RAW")
            msg = "Uspešno sačuvano u Google Sheet!"
        
        # Osvježi tabelu
        updated_records = get_tab_data()
        return msg, updated_records, None, *([None]*len(FIELD_ORDER[1:]))
    except Exception as e:
        return f"Greška: {e}", get_tab_data(), edit_id, *args[:-1]

def get_tab_data(search_text=""):
    records = get_saved_records()
    table_rows = []
    prices = load_prices_from_cloud()
    for r_num, row in records:
        r_dict = dict(zip(FIELD_ORDER, row))
        if search_text and not any(search_text.casefold() in str(v).casefold() for v in row):
            continue
        cost = calculate_storage_cost(row, prices)
        table_rows.append([
            r_num,
            r_dict.get("id"),
            r_dict.get("redniBroj"),
            r_dict.get("placeno"),
            r_dict.get("datum"),
            f"{cost:.2f}",
            r_dict.get("korisnik"),
            r_dict.get("brojTablica"),
            f"{r_dict.get('markaVozila')} {r_dict.get('modelVozila')}",
            r_dict.get("prednjaLevaDimenzija"),
            r_dict.get("prednjaDesnaDimenzija")
        ])
    return table_rows

# --- GRADIO INTERFEJS ---
with gr.Blocks(title="Hotel Guma - Gradio") as demo:
    gr.markdown("## UNOS PODATAKA - HOTEL GUMA")
    
    edit_id_state = gr.State(None)

    with gr.Row():
        # Osnovni podaci
        with gr.Column(scale=2):
            gr.Markdown("**Osnovni podaci**")
            redniBroj = gr.Textbox(value="1", label="R.br", placeholder="R.br")
            datum = gr.Textbox(value=datetime.now().strftime("%d.%m.%Y"), label="Datum")
            datumIzlaska = gr.Textbox(label="Datum izlaska")
            korisnik = gr.Textbox(label="Ime korisnika")
            telefonKorisnika = gr.Textbox(label="Telefon")
            adresaKorisnika = gr.Textbox(label="Adresa")
            vlasnik = gr.Textbox(label="Vlasnik")
            telefonVlasnika = gr.Textbox(label="Tel. vlasnika")
            brojTablica = gr.Textbox(label="Tablice")
            markaVozila = gr.Textbox(label="Marka vozila")
            modelVozila = gr.Textbox(label="Model vozila")

        def tire_column(title, prefix):
            gr.Markdown(f"**{title}**")
            dim = gr.Textbox(label="Dimenzija", placeholder="225/45R17")
            marka = gr.Textbox(label="Marka gume")
            model = gr.Textbox(label="Model gume")
            sezona = gr.Dropdown(["", "ZIMSKA", "LETNJA", "ALLSEASON"], label="Sezona")
            dot = gr.Textbox(label="DOT")
            dubina = gr.Textbox(label="Šara (mm)")
            felna = gr.Checkbox(label="Felna")
            nap = gr.Textbox(label="Napomena")
            lok = gr.Textbox(label="Lokacija")
            return [dim, marka, model, sezona, dot, dubina, felna, nap, lok]

        with gr.Column(scale=2):
            pl_inputs = tire_column("Prednja leva", "prednjaLeva")
        with gr.Column(scale=2):
            pd_inputs = tire_column("Prednja desna", "prednjaDesna")
        with gr.Column(scale=2):
            zl_inputs = tire_column("Zadnja leva", "zadnjaLeva")
        with gr.Column(scale=2):
            zd_inputs = tire_column("Zadnja desna", "zadnjaDesna")

        # Cenovnik i napomene
        with gr.Column(scale=2):
            gr.Markdown("**Cenovnik čuvanja**")
            with gr.Row():
                z19b = gr.Textbox(value=saved_prices.get("zimaDo19", "1000"), label="Zima <19 Bez f.")
                z19f = gr.Textbox(value=saved_prices.get("zimaDo19Felna", "1250"), label="Sa f.")
            with gr.Row():
                z22b = gr.Textbox(value=saved_prices.get("zima20do22", "1200"), label="Zima 20-22")
                z22f = gr.Textbox(value=saved_prices.get("zima20do22Felna", "1450"), label="Sa f.")
            with gr.Row():
                z23b = gr.Textbox(value=saved_prices.get("zimaPreko22", "1300"), label="Zima >22")
                z23f = gr.Textbox(value=saved_prices.get("zimaPreko22Felna", "1550"), label="Sa f.")
            with gr.Row():
                l19b = gr.Textbox(value=saved_prices.get("letoDo19", "1400"), label="Leto <19")
                l19f = gr.Textbox(value=saved_prices.get("letoDo19Felna", "1650"), label="Sa f.")
            with gr.Row():
                l22b = gr.Textbox(value=saved_prices.get("leto20do22", "1680"), label="Leto 20-22")
                l22f = gr.Textbox(value=saved_prices.get("leto20do22Felna", "1930"), label="Sa f.")
            with gr.Row():
                l23b = gr.Textbox(value=saved_prices.get("letoPreko22", "1820"), label="Leto >22")
                l23f = gr.Textbox(value=saved_prices.get("letoPreko22Felna", "2070"), label="Sa f.")

            napomenaIzlaska = gr.Textbox(label="Napomena", lines=2)
            placeno = gr.Checkbox(label="Plaćeno")

    with gr.Row():
        submit_btn = gr.Button("Sačuvaj", variant="primary")
        clear_btn = gr.Button("Nova forma")
        status_box = gr.Textbox(label="Status", interactive=False)

    gr.Markdown("### Pregled unosa")
    search_box = gr.Textbox(label="Pretraga unosa", placeholder="Unesite pojam za pretragu...")
    
    table = gr.Dataframe(
        headers=["Red", "ID", "R.br", "Plaćeno", "Prijem", "Obračun RSD", "Korisnik", "Tablice", "Vozilo", "PL Dim", "PD Dim"],
        value=get_tab_data(),
        interactive=False
    )

    # Lista svih ulaznih polja za formu
    form_inputs = [
        redniBroj, datum, datumIzlaska, korisnik, telefonKorisnika, adresaKorisnika,
        vlasnik, telefonVlasnika, brojTablica, markaVozila, modelVozila,
        *pl_inputs, *pd_inputs, *zl_inputs, *zd_inputs,
        z19b, z19f, z22b, z22f, z23b, z23f, l19b, l19f, l22b, l22f, l23b, l23f,
        napomenaIzlaska, placeno, edit_id_state
    ]

    submit_btn.click(
        fn=save_entry,
        inputs=form_inputs,
        outputs=[status_box, table, edit_id_state, *form_inputs[:-1]]
    )

    search_box.change(
        fn=get_tab_data,
        inputs=search_box,
        outputs=table
    )

    clear_btn.click(
        fn=lambda: [None] * len(form_inputs),
        outputs=form_inputs
    )

if __name__ == "__main__":
    demo.launch()