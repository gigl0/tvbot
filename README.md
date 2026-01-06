# Low-Spec TV Bot 📺

Un bot Telegram ultra-leggero ottimizzato per hardware datato (es. AMD E1, Raspberry Pi Zero).
Gestisce un calendario serie TV con aggiornamenti automatici e notifiche news.

## Caratteristiche
- **Dashboard Pinnata**: Un unico messaggio aggiornato ogni giorno con il countdown agli episodi.
- **News Feed**: Notifiche immediate dalle news di Google (RSS).
- **Risorse Minime**: Usa SQLite e Python Alpine, consumo RAM < 50MB.

## Installazione con Docker

1. Clona il repo:
   ```bash
   git clone https://github.com/gigl0/tvbot
   cd tvbot
   nano .env
   nano series.json