import os
import time
import json
import sqlite3
import logging
import requests
import feedparser
import schedule
from datetime import datetime
from dotenv import load_dotenv
from sentry_handler import init_sentry
# --- CONFIGURAZIONE ---
load_dotenv()

# Log su INFO per la produzione (meno spam)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '../data')
DB_PATH = os.path.join(DATA_DIR, 'bot_memory.db')
SERIES_FILE = os.path.join(BASE_DIR, '../series.json')

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TOPIC_NEWS = os.getenv("TOPIC_ID_NEWS")
TOPIC_RELEASES = os.getenv("TOPIC_ID_RELEASES")
ERROR_TOPIC = int(os.getenv('TVBOT_TOPIC_ID', 0)) 
DSN = os.getenv('SENTRY_DSN')

# --- SENTRY ---
if DSN:
    init_sentry(
        dsn=DSN,
        bot_name="📺 TVBot",
        telegram_token=TOKEN,
        chat_id=CHAT_ID,
        topic_id=ERROR_TOPIC # Manda l'errore nel topic 54
    )
    
# --- DATABASE ---
def init_db():
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tabella per tracciare le news già inviate
    c.execute('''CREATE TABLE IF NOT EXISTS seen_news (link TEXT PRIMARY KEY)''')
    # Tabella per salvare configurazioni (es. ID messaggio dashboard)
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def is_seen_news(link):
    conn = sqlite3.connect(DB_PATH)
    res = conn.cursor().execute("SELECT 1 FROM seen_news WHERE link=?", (link,)).fetchone()
    conn.close()
    return res is not None

def mark_news_as_seen(link):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("INSERT OR IGNORE INTO seen_news (link) VALUES (?)", (link,))
    conn.commit()
    conn.close()

def get_config(key):
    conn = sqlite3.connect(DB_PATH)
    res = conn.cursor().execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return res[0] if res else None

def set_config(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# --- FUNZIONI TELEGRAM ---

# 1. Funzione Semplice per le NEWS (Topic News)
def send_news_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "message_thread_id": TOPIC_NEWS
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        # Gestione base rate limit
        if r.status_code == 429:
            time.sleep(int(r.json().get('parameters', {}).get('retry_after', 60)) + 1)
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Errore invio News: {e}")

# 2. Funzione Avanzata per la DASHBOARD (Topic Releases - Edit/Pin)
def send_or_edit_dashboard(text):
    msg_id = get_config('dashboard_msg_id')
    base_url = f"https://api.telegram.org/bot{TOKEN}"
    
    # Tentativo di Modifica (EDIT)
    if msg_id:
        edit_url = f"{base_url}/editMessageText"
        payload = {
            "chat_id": CHAT_ID,
            "message_id": msg_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(edit_url, json=payload, timeout=10)
            
            if r.status_code == 200:
                logger.info("Dashboard aggiornata.")
                return
            
            # --- AGGIUNTA FONDAMENTALE ---
            # Se il messaggio è identico, Telegram dà errore 400. Noi lo ignoriamo.
            elif r.status_code == 400 and "message is not modified" in r.text:
                logger.info("Dashboard identica (nessuna modifica necessaria).")
                return
            # -----------------------------

            else:
                logger.warning(f"Edit fallito (msg cancellato?): {r.text}")
                msg_id = None # Solo se fallisce davvero resettiamo l'ID
        except Exception as e:
            logger.error(f"Errore edit dashboard: {e}")
            msg_id = None

    # Nuovo Messaggio (CREATE + PIN) - Resto della funzione invariato...
    if not msg_id:
        send_url = f"{base_url}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "message_thread_id": TOPIC_RELEASES
        }
        try:
            r = requests.post(send_url, json=payload, timeout=10)
            if r.status_code == 200:
                new_msg_id = r.json()['result']['message_id']
                set_config('dashboard_msg_id', new_msg_id)
                logger.info(f"Nuova Dashboard creata: ID {new_msg_id}")
                
                # Fissa il messaggio (Pin)
                requests.post(f"{base_url}/pinChatMessage", 
                              json={"chat_id": CHAT_ID, "message_id": new_msg_id}, timeout=5)
        except Exception as e:
            logger.error(f"Errore creazione dashboard: {e}")

# --- JOB: NEWS (Google RSS) ---
def job_check_news():
    logger.info("Check News...")
    try:
        with open(SERIES_FILE, 'r') as f: series = json.load(f)
    except: return

    for s in series:
        rss = f"https://news.google.com/rss/search?q={s.replace(' ', '+')}+serie+tv+when:7d&hl=it&gl=IT&ceid=IT:it"
        try:
            feed = feedparser.parse(rss)
            for e in feed.entries[:2]: # Max 2 news per serie
                
                # MODIFICA IMPORTANTE: Usa l'ID (GUID) invece del LINK
                # Se 'id' esiste nel feed usa quello, altrimenti ripiega sul link
                guid = e.get('id', e.link)
                
                if not is_seen_news(guid):
                    msg = f"📰 <b>News: {s}</b>\n\n<a href='{e.link}'>{e.title}</a>"
                    send_news_telegram(msg)
                    mark_news_as_seen(guid) # Salviamo il GUID nel DB
                    time.sleep(1) # Rispetto API
        except Exception as e: 
            logger.error(f"Err News {s}: {e}")

# --- JOB: DASHBOARD USCITE (TVMaze) ---
def job_check_releases():
    logger.info("Costruzione Dashboard...")
    try:
        with open(SERIES_FILE, 'r') as f: series_list = json.load(f)
    except Exception as e:
        logger.error(f"Errore series.json: {e}")
        return

    today = datetime.now().date()
    upcoming_shows = []
    
    for s in series_list:
        url = f"https://api.tvmaze.com/singlesearch/shows?q={s}&embed=nextepisode"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                name = data['name']
                
                if '_embedded' in data and 'nextepisode' in data['_embedded']:
                    ep = data['_embedded']['nextepisode']
                    airdate = datetime.strptime(ep['airdate'], "%Y-%m-%d").date()
                    delta = (airdate - today).days
                    ep_code = f"S{ep['season']:02d}E{ep['number']:02d}"
                    
                    if delta == 0:
                        status = "🚨 <b>OGGI!</b>"
                        row = f"🟢 <b>{name}</b>: {ep_code} - {status}"
                        order = 0
                    elif delta == 1:
                        status = "⏰ <b>DOMANI!</b>"
                        row = f"🟢 <b>{name}</b>: {ep_code} - {status}"
                        order = 1
                    elif delta > 0:
                        status = f"tra {delta} gg ({ep['airdate']})"
                        row = f"🟡 <b>{name}</b>: {ep_code} - {status}"
                        order = delta + 10
                    else:
                        row = f"⚪️ <b>{name}</b>: {ep_code} - {ep['airdate']}"
                        order = 999
                else:
                    row = f"🔴 <b>{name}</b>: In attesa..."
                    order = 9999
            else:
                row = f"❓ <b>{s}</b>: Non trovata"
                order = 99999
            
            upcoming_shows.append((order, row))
            time.sleep(1) # Rispetto API

        except Exception as e:
            logger.error(f"Err {s}: {e}")
            upcoming_shows.append((99999, f"❌ <b>{s}</b>: Errore API"))

    # Ordina e costruisci messaggio
    upcoming_shows.sort(key=lambda x: x[0])
    
    msg_body = f"📺 <b>CALENDARIO SERIE TV</b>\n<i>Ultimo agg: {today.strftime('%d/%m %H:%M')}</i>\n\n"
    for _, line in upcoming_shows:
        msg_body += line + "\n"
        
    send_or_edit_dashboard(msg_body)

# --- MAIN ---
if __name__ == "__main__":
    init_db()
    logger.info("Bot Dashboard Avviato (Silent Mode)")

    # Esegui subito una volta per creare la dashboard
    job_check_releases()

    # Schedulazione
    schedule.every().hour.at(":15").do(job_check_news)     # News ogni ora
    schedule.every().day.at("09:00").do(job_check_releases) # Aggiorna Dashboard ogni mattina

    while True:
        schedule.run_pending()
        time.sleep(60)