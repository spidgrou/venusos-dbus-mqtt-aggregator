#!/bin/bash

# Abilita l'uscita immediata in caso di errore
set -e

# --- Variabili ---
SERVICE_NAME="dbus-mqtt-bridge"
SCRIPT_DIR="/data/$SERVICE_NAME"
SERVICE_DIR="/data/service/$SERVICE_NAME"
SERVICE_LINK="/service/$SERVICE_NAME"
RC_LOCAL="/data/rc.local"
SETUP_SERVICES="/data/setup-services.sh"

# --- Inizio script ---
echo "--- Inizio Disinstallazione Servizio D-Bus to MQTT ---"

# 1. Controlla di essere eseguito come root
if [ "$(id -u)" -ne 0 ]; then
    echo "Errore: Questo script deve essere eseguito come utente root."
    exit 1
fi

# 2. Ferma e disabilita il servizio
echo "[1/4] Arresto e disabilitazione del servizio..."
# Rimuove il link per disattivare il servizio
if [ -L "$SERVICE_LINK" ]; then
    rm "$SERVICE_LINK"
    echo "Link del servizio rimosso."
fi
# Attende un paio di secondi per assicurarsi che il gestore se ne accorga
sleep 2

# 3. Rimuove i file del servizio e dello script principale
echo "[2/4] Rimozione dei file del programma..."
if [ -d "$SCRIPT_DIR" ]; then
    rm -rf "$SCRIPT_DIR"
    echo "Directory del programma ($SCRIPT_DIR) rimossa."
fi
if [ -d "$SERVICE_DIR" ]; then
    rm -rf "$SERVICE_DIR"
    echo "Directory del servizio ($SERVICE_DIR) rimossa."
fi

# 4. Pulisce la configurazione di avvio automatico (rc.local)
# Questo passaggio è delicato: rimuoviamo solo le nostre righe, se possibile.
# Per semplicità e sicurezza, diamo solo un avviso, ma un utente avanzato potrebbe modificarlo.
# In questo caso, rimuoviamo i file che abbiamo creato noi.
echo "[3/4] Pulizia della configurazione di avvio..."
if [ -f "$SETUP_SERVICES" ]; then
    rm "$SETUP_SERVICES"
    echo "Script di setup ($SETUP_SERVICES) rimosso."
fi
if [ -f "$RC_LOCAL" ]; then
    # Controlla se rc.local contiene solo la nostra riga, in caso affermativo, lo rimuove.
    if grep -q "$SETUP_SERVICES" "$RC_LOCAL" && [ "$(wc -l < "$RC_LOCAL")" -le 3 ]; then
        rm "$RC_LOCAL"
        echo "File di avvio ($RC_LOCAL) rimosso."
    else
        echo "ATTENZIONE: Il file $RC_LOCAL sembra contenere altre modifiche."
        echo "Per favore, modificalo manualmente e rimuovi la riga che esegue: $SETUP_SERVICES"
    fi
fi

# 5. Rimuove i log (opzionale, ma pulito)
echo "[4/4] Rimozione dei log..."
# Il logger di VenusOS per i servizi daemontools non crea una cartella separata,
# quindi non c'è nulla da rimuovere qui in modo sicuro. I log rimarranno
# nel file di sistema principale /var/log/messages.
echo "Nessun file di log separato da rimuovere."

echo "--- Disinstallazione Completata! ---"
echo "Il servizio e tutti i suoi file sono stati rimossi."
echo "Potrebbe essere necessario un riavvio per finalizzare la pulizia."
