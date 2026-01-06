import sentry_sdk
import requests
import logging

def init_sentry(dsn, bot_name, telegram_token, chat_id, topic_id=None):
    """
    Configura Sentry per inviare notifiche al Topic Telegram specificato.
    """
    if not dsn:
        logging.warning(f"⚠️ Sentry DSN mancante per {bot_name}")
        return

    def send_telegram_alert(event, hint):
        # Filtra errori ignorati (se necessario)
        if 'exc_info' in hint:
            exc_type, _, _ = hint['exc_info']
            if exc_type == KeyboardInterrupt:
                return None

        # Estrai info errore
        exception_type = "Errore Generico"
        error_msg = "Nessun dettaglio"
        if 'exception' in event and event['exception']['values']:
            err = event['exception']['values'][0]
            exception_type = err.get('type', 'Error')
            error_msg = err.get('value', '')

        # Messaggio per Telegram
        text = (
            f"🚨 **{bot_name} CRASH** 🚨\n"
            f"💀 `{exception_type}`: {error_msg}\n"
            f"🔗 [Apri Sentry](https://sentry.io)"
        )

        try:
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "message_thread_id": topic_id # La magia è qui
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Err notifica Telegram: {e}")

        return event

    sentry_sdk.init(
        dsn=dsn,
        sample_rate=1.0,
        before_send=send_telegram_alert,
        integrations=[] 
    )
    logging.info(f"✅ Sentry attivo per {bot_name} -> Topic {topic_id}")