from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import qrcode
import os
import socket
from datetime import datetime

app = Flask(__name__)

INVENTARIO_FILE = 'inventario.csv'
QR_FOLDER = 'static/qr'
os.makedirs(QR_FOLDER, exist_ok=True)

# Campi inclusi "tipo", "storico", "operatori", "quantita_disponibile"
CAMPOS = [
    "produttore", "diametro", "materiale", "descrizione", "codice",
    "quantita", "quantita_disponibile", "tipo", "cassetto", "stato", "operatori", "storico"
]

def leggi_inventario():
    if os.path.exists(INVENTARIO_FILE):
        df = pd.read_csv(INVENTARIO_FILE)
        # Assicuriamo che tutte le colonne esistano (per retrocompatibilità)
        for campo in CAMPOS:
            if campo not in df.columns:
                if campo == "quantita_disponibile":
                    if 'quantita' in df.columns:
                        df[campo] = df['quantita']
                    else:
                        df[campo] = 0
                elif campo == "quantita":
                    df[campo] = 0
                else:
                    df[campo] = ""
        # Pulizia tipi e gestione NaN
        df['operatori'] = df['operatori'].fillna('')
        df['storico'] = df['storico'].fillna('')
        df['tipo'] = df['tipo'].fillna('')
        # quantita e quantita_disponibile come interi
        df['quantita'] = pd.to_numeric(df['quantita'], errors='coerce').fillna(0).astype(int)
        df['quantita_disponibile'] = pd.to_numeric(df['quantita_disponibile'], errors='coerce').fillna(df['quantita']).astype(int)
        return df
    else:
        # Nuovo DataFrame con tutte le colonne
        return pd.DataFrame(columns=CAMPOS)

def salva_inventario(df):
    df.to_csv(INVENTARIO_FILE, index=False)

def get_ip_locale():
    """
    Prova a ottenere l'IP locale della macchina, utile per generare QR raggiungibili 
    da smartphone sulla stessa rete.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def aggiorna_operatori(operatori_str, nome, qta):
    """
    operatori_str: formato "Filippo:2;Cristian:1"
    nome: nome operatore che preleva/restiuisce
    qta: quantità (intero, se prelievo positivo; per restituzione si passa qta negativa o gestito separatamente)
    """
    d = {}
    if isinstance(operatori_str, str) and operatori_str.strip():
        for item in operatori_str.split(';'):
            if ':' in item:
                k, v = item.split(':')
                try:
                    d[k.strip()] = int(v.strip())
                except:
                    d[k.strip()] = 0
            else:
                d[item.strip()] = 0
    if qta != 0:
        if nome in d:
            d[nome] = d[nome] + qta
        else:
            d[nome] = qta
        if d[nome] <= 0:
            del d[nome]
    return ';'.join([f"{k}:{v}" for k, v in d.items()])

@app.route('/')
def index():
    df = leggi_inventario()

    # Lettura parametri GET per ricerca
    # I nomi dei parametri coincidono con i nomi delle colonne minuscole
    # Eseguiamo filtro case-insensitive 'contains' se il parametro è non vuoto
    ricerca_produttore = request.args.get('produttore', '').strip()
    ricerca_diametro = request.args.get('diametro', '').strip()
    ricerca_materiale = request.args.get('materiale', '').strip()
    ricerca_tipo = request.args.get('tipo', '').strip()
    ricerca_descrizione = request.args.get('descrizione', '').strip()
    ricerca_codice = request.args.get('codice', '').strip()

    # Filtri sequenziali: se i parametri sono forniti, applichiamo .str.contains
    if ricerca_produttore:
        df = df[df['produttore'].astype(str).str.contains(ricerca_produttore, case=False, na=False)]
    if ricerca_diametro:
        df = df[df['diametro'].astype(str).str.contains(ricerca_diametro, case=False, na=False)]
    if ricerca_materiale:
        df = df[df['materiale'].astype(str).str.contains(ricerca_materiale, case=False, na=False)]
    if ricerca_tipo:
        df = df[df['tipo'].astype(str).str.contains(ricerca_tipo, case=False, na=False)]
    if ricerca_descrizione:
        df = df[df['descrizione'].astype(str).str.contains(ricerca_descrizione, case=False, na=False)]
    if ricerca_codice:
        df = df[df['codice'].astype(str).str.contains(ricerca_codice, case=False, na=False)]

    # Preparazione dati per template
    def format_operatori(op_str):
        if not isinstance(op_str, str) or not op_str.strip():
            return ""
        parts = []
        for item in op_str.split(';'):
            if ':' in item:
                k, v = item.split(':')
                parts.append(f"{k.strip()} ({v.strip()})")
        return ', '.join(parts)

    utensils = df.to_dict(orient='records')
    for u in utensils:
        qr_filename = f"{u['codice']}.png"
        qr_path = os.path.join(QR_FOLDER, qr_filename)
        if not os.path.exists(qr_path):
            ip = get_ip_locale()
            url_qr = f"http://{ip}:5000/utensile/{u['codice']}"
            try:
                qr = qrcode.make(url_qr)
                qr.save(qr_path)
            except:
                pass
        u['qr_img'] = url_for('static', filename=f"qr/{qr_filename}")
        u['operatori_formattati'] = format_operatori(u.get('operatori', ''))
    # Passiamo anche i parametri di ricerca per mantenerli nel form
    return render_template(
        'index.html',
        utensils=utensils,
        ricerca_produttore=ricerca_produttore,
        ricerca_diametro=ricerca_diametro,
        ricerca_materiale=ricerca_materiale,
        ricerca_tipo=ricerca_tipo,
        ricerca_descrizione=ricerca_descrizione,
        ricerca_codice=ricerca_codice
    )

@app.route('/inserisci', methods=['GET', 'POST'])
def inserisci():
    if request.method == 'POST':
        dati = {campo: request.form.get(campo, '') for campo in CAMPOS if campo not in ['quantita_disponibile', 'storico', 'operatori', 'stato']}
        try:
            qta = int(dati.get('quantita', '0'))
        except:
            qta = 0
        dati['quantita'] = qta
        dati['quantita_disponibile'] = qta
        dati['stato'] = "in magazzino"
        dati['operatori'] = ""
        dati['storico'] = ""
        df = leggi_inventario()
        if dati['codice'] in df['codice'].values:
            idx = df[df['codice'] == dati['codice']].index[0]
            df.at[idx, 'quantita'] = df.at[idx, 'quantita'] + dati['quantita']
            df.at[idx, 'quantita_disponibile'] = df.at[idx, 'quantita_disponibile'] + dati['quantita']
            df.at[idx, 'stato'] = "in magazzino"
            salva_inventario(df)
        else:
            df = pd.concat([df, pd.DataFrame([dati])], ignore_index=True)
            salva_inventario(df)
        # Genera QR con IP locale
        ip = get_ip_locale()
        url_qr = f"http://{ip}:5000/utensile/{dati['codice']}"
        qr = qrcode.make(url_qr)
        qr.save(os.path.join(QR_FOLDER, f"{dati['codice']}.png"))
        return redirect(url_for('index'))
    return render_template('inserisci.html')

@app.route('/utensile/<codice>')
def utensile(codice):
    df = leggi_inventario()
    u = df[df['codice'] == codice]
    if u.empty:
        return "Utensile non trovato", 404
    utensile = u.iloc[0].to_dict()
    # Prepara lista operatori attuali (in uso)
    ops_str = utensile.get('operatori', '')
    operators = []
    if isinstance(ops_str, str) and ops_str.strip():
        for item in ops_str.split(';'):
            if ':' in item:
                k, v = item.split(':')
                operators.append({'nome': k.strip(), 'quantita': v.strip()})
    return render_template('scheda.html', u=utensile, operators=operators)

@app.route('/preleva/<codice>', methods=['GET', 'POST'])
def preleva(codice):
    df = leggi_inventario()
    idxs = df[df['codice'] == codice].index
    if len(idxs) == 0:
        return "Utensile non trovato", 404
    idx = idxs[0]
    utensile = df.loc[idx]
    if request.method == 'POST':
        operatore = request.form.get('operatore', '').strip()
        try:
            qta_prelevata = int(request.form.get('quantita_prelevata', '0'))
        except:
            qta_prelevata = 0
        if not operatore:
            return "Inserire nome operatore", 400
        if qta_prelevata <= 0:
            return "Quantità prelevata deve essere > 0", 400
        try:
            disp = int(utensile['quantita_disponibile'])
        except:
            disp = 0
        if qta_prelevata > disp:
            return f"Quantità disponibile insufficiente ({disp})", 400
        nuovo_disp = disp - qta_prelevata
        df.at[idx, 'quantita_disponibile'] = nuovo_disp
        try:
            tot = int(utensile['quantita'])
        except:
            tot = 0
        nuovo_tot = tot - qta_prelevata
        df.at[idx, 'quantita'] = nuovo_tot
        df.at[idx, 'stato'] = "in uso" if nuovo_disp < nuovo_tot or nuovo_disp < tot else "in magazzino"
        ops_str = utensile.get('operatori', '')
        new_ops = aggiorna_operatori(ops_str, operatore, qta_prelevata)
        df.at[idx, 'operatori'] = new_ops
        storico_raw = utensile.get('storico', '')
        if not isinstance(storico_raw, str):
            storico_raw = ''
        evento = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:: {operatore}:: PRELIEVO {qta_prelevata}"
        nuovo_storico = storico_raw + "||" + evento if storico_raw else evento
        df.at[idx, 'storico'] = nuovo_storico
        salva_inventario(df)
        return redirect(url_for('index'))
    try:
        max_qta = int(utensile['quantita_disponibile'])
    except:
        max_qta = 0
    return render_template('preleva.html', codice=codice, max_qta=max_qta)

@app.route('/restituisci/<codice>', methods=['GET', 'POST'])
def restituisci(codice):
    df = leggi_inventario()
    idxs = df[df['codice'] == codice].index
    if len(idxs) == 0:
        return "Utensile non trovato", 404
    idx = idxs[0]
    utensile = df.loc[idx]
    if request.method == 'POST':
        operatore = request.form.get('operatore', '').strip()
        try:
            qta_restituita = int(request.form.get('quantita_restituita', '0'))
        except:
            qta_restituita = 0
        stato = request.form.get('stato', 'in magazzino').strip().lower()
        if not operatore:
            return "Inserire nome operatore", 400
        if qta_restituita <= 0:
            return "Quantità restituita deve essere > 0", 400
        ops_str = utensile.get('operatori', '')
        ops_dict = {}
        if isinstance(ops_str, str) and ops_str.strip():
            for item in ops_str.split(';'):
                if ':' in item:
                    k, v = item.split(':')
                    try:
                        ops_dict[k.strip()] = int(v.strip())
                    except:
                        ops_dict[k.strip()] = 0
        if operatore not in ops_dict or ops_dict[operatore] < qta_restituita:
            return "Errore: operatore non ha prelevato questa quantità", 400
        ops_dict[operatore] -= qta_restituita
        if ops_dict[operatore] <= 0:
            del ops_dict[operatore]
        new_ops_str = ';'.join([f"{k}:{v}" for k, v in ops_dict.items()])
        df.at[idx, 'operatori'] = new_ops_str
        if stato == 'in magazzino':
            try:
                tot = int(utensile['quantita'])
            except:
                tot = 0
            try:
                disp = int(utensile['quantita_disponibile'])
            except:
                disp = 0
            nuovo_disp = disp + qta_restituita
            nuovo_tot = tot + qta_restituita
            df.at[idx, 'quantita_disponibile'] = nuovo_disp
            df.at[idx, 'quantita'] = nuovo_tot
            df.at[idx, 'stato'] = "in magazzino"
        elif stato == 'rotta':
            df.at[idx, 'stato'] = "rotta"
        else:
            df.at[idx, 'stato'] = "in magazzino"
            try:
                tot = int(utensile['quantita'])
            except:
                tot = 0
            try:
                disp = int(utensile['quantita_disponibile'])
            except:
                disp = 0
            nuovo_disp = disp + qta_restituita
            nuovo_tot = tot + qta_restituita
            df.at[idx, 'quantita_disponibile'] = nuovo_disp
            df.at[idx, 'quantita'] = nuovo_tot
        storico_raw = utensile.get('storico', '')
        if not isinstance(storico_raw, str):
            storico_raw = ''
        evento = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:: {operatore}:: RESTITUZIONE {qta_restituita} ({stato})"
        nuovo_storico = storico_raw + "||" + evento if storico_raw else evento
        df.at[idx, 'storico'] = nuovo_storico
        salva_inventario(df)
        return redirect(url_for('index'))
    # GET: calcola max che può restituire (somma in uso)
    ops_str = utensile.get('operatori', '')
    total_in_uso = 0
    if isinstance(ops_str, str) and ops_str.strip():
        for item in ops_str.split(';'):
            if ':' in item:
                try:
                    total_in_uso += int(item.split(':')[1].strip())
                except:
                    pass
    return render_template('restituisci.html', codice=codice, max_qta=total_in_uso)

@app.route('/cancella/<codice>', methods=['POST'])
def cancella(codice):
    df = leggi_inventario()
    idxs = df[df['codice'] == codice].index
    if len(idxs) == 0:
        return "Utensile non trovato", 404
    idx = idxs[0]
    df = df.drop(idx).reset_index(drop=True)
    salva_inventario(df)
    qr_path = os.path.join(QR_FOLDER, f"{codice}.png")
    if os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except:
            pass
    return redirect(url_for('index'))

@app.route('/etichette')
def etichette():
    df = leggi_inventario()
    utensils = df.to_dict(orient='records')
    return render_template('etichette.html', utensils=utensils)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
