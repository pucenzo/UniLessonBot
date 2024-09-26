from telegram.constants import ParseMode
import telebot
from telebot import types 
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import smtplib 
import random 
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


"""--------------------------------------------------------------------------SCRAPING CLASSROOM OCCUPATION WEB PAGE----------------------------------------------------------------------------------------"""


current_date = datetime.today() #memorizzo la data corrente
formatted_date = current_date.strftime("%Y/%m/%d") #la formatto nel formato aaaa/mm/gg


url = f"https://mrbs.dmi.unipg.it/day.php?year={current_date.year}&month={current_date.month}&day={current_date.day}&area=1&room=3"
response = requests.get(url) #invia una richiesta http all'indirizzo link
cont = response.text #otteniamo il contenuto della richiesta, (codice html della pagina)


if(response.status_code == 200): # il server ha risposto con successo alla richiesta http
    soup = BeautifulSoup(cont, 'html.parser') #BeautifulSoup, funzione che estrae il testo html dalla risposta

    date = soup.find("div", id="dwm").get_text(strip=True) #restituisce il testo del tag div con id=dwm (giorno, mese, anno)
    table = soup.find("table", class_ = "dwm_main") #restituisce il testo html del tag table e dei sotto tag (tabella lezioni)
    rows = table.find_all("tr") #lista di tutte le righe della tabella

    header = rows[0]  #testo html della prima riga della tabella (intestazione)
    times = [header.get_text(strip=True) for header in header.find_all("th")][1:] #lista con gli orari dell'intestazione

    lessons_list = []

    message_lesson = f"📆 Data: {date}\n\n" #variabile che memorizza il messaggio finale, inizializzata con la data del giorno    
    
    for row in rows[1:]: #iteriamo sulle righe della tabella a partire dalla seconda
        cells = row.find_all("td") #trova tutte le celle (tag <td>) della riga corrente

        room_name = cells[0].get_text(strip=True) #la prima cella contiene l'aula, estrae il nome
        room = f"   🚪 Aula: {room_name}\n" #stringa con il nome dell'aula 
        room_name = re.sub(r'\(.*?\)', '', room_name).strip() #rimuove qualsiasi cosa tra parentesi tonde

        has_lessons = False  #flag per controllare se ci sono lezioni in quell'aula
        time_index = 0  #indice per tracciare le fasce orarie delle lezioni

        for cell in cells[1:]: #iteriamo su tutte le celle della riga tranne la prima che contiene l'aula
            colspan = int(cell.get('colspan', 1))  #conterrà il numero di colonne (ossia di ore) che la lezione copre. se colspan non è specificato, copre solo 1 fascia oraria.
            if cell.get_text(strip=True): #se c'è almeno una lezione nella cella:
                lesson_string = cell.find("a").get_text(strip=True) + " - " + cell.find("sub").get_text(strip=True) #lesson contiene il nome della lezione e del prof. (nome lezione tag <a>, nome prof. tag <sub>)
                lessons_list.append((room_name, cell.find("a").get_text(strip=True), cell.find("sub").get_text(strip=True))) #lista delle aule, lezioni e prof.
                end_time_index = time_index + colspan  #indice ora di fine = indice ora di inizio + nr. colonne/ore coperte

                if end_time_index < len(times): #se fine della lezione è nei limiti degli orari:
                    start_time = times[time_index] #recupera  l'ora di inizio
                    end_time = times[end_time_index] #recupera l'ora di fine

                    room += f"        ⌚ {start_time} - {end_time}: 📚 {lesson_string}\n" #aggiunge al nome dell'aule, l'ora di inizio e fine e la lezione
                    has_lessons = True  #imposta il flag a true visto che abbiamo trovato almeno una lezione
                else: #se fine della lezione è oltre i limiti degli orari (18:00):
                    start_time = times[time_index] #recupera l'ora di inizio
                    room += f"        ⌚ {start_time} - 19:00: 📚 {lesson_string}\n" #per evitare errori di indici inseriamo manualmente l'ora di fine (19:00)
                    has_lessons = True  
        
            time_index += colspan  #incrementa l'indice dell'ora per saltare alla prossima lezione (se c'è)

        if has_lessons:  #se sono quindi state trovate lezioni per quell'aula:
            message_lesson += room + "\n" #aggiungiamo il messaggio con aula, ore e lezioni al messaggio finale 
    if not lessons_list:  #se non ci sono lezioni:
        message_lesson += "Non ci sono lezioni oggi!"
else:
    print("Errore nella richiesta HTTP:", response.status_code)


"""-----------------------------------------------------------------------------TELEGRAM BOT CREATION AND HANDLE PART-------------------------------------------------------------------------------------"""


TOKEN = "MY BOT TOKEN" #token ottenuto dal bot father 
bot = telebot.TeleBot(TOKEN)


connection = sqlite3.connect("dbot.db", check_same_thread = False) #stabiliamo la connessione con il database 
cursor = connection.cursor() #definiamo un oggetto cursore che servirà per impartire comandi al db


cursor.execute("CREATE TABLE IF NOT EXISTS studenti(id INTEGER PRIMARY KEY, email TEXT UNIQUE, matricola TEXT UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS lezioni (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, docente TEXT NOT NULL, aula TEXT NOT NULL, data TEXT, posti_disponibili INTEGER NOT NULL, posti_prenotati INTEGER DEFAULT 0,UNIQUE(nome, aula))")    
cursor.execute("CREATE TABLE IF NOT EXISTS prenotazioni(id INTEGER PRIMARY KEY AUTOINCREMENT, matricola TEXT, id_lezione INTEGER, FOREIGN KEY (id_lezione) REFERENCES lezioni (id))")
connection.commit()


#memorizzazione delle capacità delle diverse aule    
room_capacity = {
    "A0": 180,
    "A2": 180,
    "A3": 70,
    "B1": 30,
    "B3": 35,
    "C2": 20,
    "I1": 215,
    "I2": 90,
    "Sala Riunioni": 40,
    "Aula C3": 25,
    "Aula Gialla": 17,
    "Aula Verde": 18,
}


email_sender = 'telebot.ingsw@gmail.com' #indirizzo email del bot
email_sender_pw = 'MY PASSWORD FOR APP' #password per app, dell'email del bot
smtp_server = 'smtp.gmail.com' #indirizzo del server smtp
smtp_port = 587 #numero porta del server smtp di gmail


#funzione per generare un codice casuale
def generate_code(length = 8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k = length))


#funzione per l'invio dell'email
def send_email(subject, body, email_recipient):
    msg = MIMEMultipart() #crea un oggetto che rappresenta l'email
    msg['From'] = email_sender #imposta il campo from dell'email, che rappresenta l'email del mittente
    msg['To'] = email_recipient #imposta il campo to dell'email, che rappresenta l'email del destinatario
    msg['Subject'] = subject #imposta il campo subject dell'email, che rappresenta l'oggetto dell'email
    msg.attach(MIMEText(body, 'plain')) #aggiunge il corpo del messaggoo all'email in formato semplice
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server: #connessione con il server smtp
            server.starttls() #abilita il tls, che stabilisce una connessione sicura con il server
            server.login(email_sender, email_sender_pw) #accede all'indirizzo email del bot
            server.send_message(msg)  #invia l'email al destinatario
        print("Email inviata con successo")
    except Exception as e:
        print(f"Invio email fallito: {e}")


#funzione per inserire le lezioni nella tabella
def insert_lesson():
    for room_name, lesson_name, prof_name in lessons_list: #iteriamo sulle aule e sulle lezioni
        posti_disponibili = room_capacity.get(room_name) #recupera la capacità dell'aula della lezione
        cursor.execute("INSERT OR IGNORE INTO lezioni (nome, docente, aula, data, posti_disponibili) VALUES (?, ?, ?, ?, ?)",(lesson_name, prof_name, room_name, formatted_date, posti_disponibili))
    connection.commit()
insert_lesson()


user_codes = {} #dizionario per memorizzare i codici associati agli id degli utenti telegram
user_emails = {} #dizionario per memorizzare l'email dell'utente


#definizione comando /start:
@bot.message_handler(commands = ["start"])
def start(message) -> None:
    
    messaggio = (f"*Benvenuto/a {message.from_user.first_name}*\\! 👋\n"
                "Sono il bot per la ricerca e prenotazione di un posto a lezione📚\\.\n"
                "Prima di iniziare ti chiedo di fornirmi la tua email istituzionale 📧\n"
                "così da poterti inviare un codice di verifica\\.")
    
    bot.send_message(message.chat.id, messaggio, parse_mode=ParseMode.MARKDOWN_V2) #invio il messaggio
    bot.register_next_step_handler(message, email_verification) #registro il prossimo passo


#funzione di verifica dell'email e invio del codice di verifica:
def email_verification(message) -> None:
    user_id = message.from_user.id    
    student_email = message.text #estrae il testo dal messaggio telegram dell'utente, quindi l'email

    if not student_email.endswith('@studenti.unipg.it'): #controlliamo se l'email termina con il dominio giusto
        bot.send_message(message.chat.id,'⚠️L\'email fornita non è corretta ❌.\n Ti ricordo che devi obbligatoriamente inserire la tua email istituzionale') #se il dominio non è giusto invia questo messaggio di errore
        bot.register_next_step_handler(message, email_verification)

    else: #caso email corretta
        code = generate_code() #generiamo un codice random
        user_codes[user_id] = code #memorizza il codice inviato
        user_emails[user_id] = student_email #memorizza l'email dell'utente

        subject = "Codice di verifica" #oggetto dell'email
        body = f"Il tuo codice di verifica è: {code}" #corpo dell'email
        send_email(subject, body, student_email) #richiama la funzione che invia l'email

        bot.send_message(message.chat.id,'📩Un codice di verifica è stato inviato alla tua email istituzionale. Per favore rispondi con il codice.')    
        bot.register_next_step_handler(message, code_verification) 


#verifica del codice:
def code_verification(message) -> None:
    user_id = message.from_user.id 
    sent_code = user_codes[user_id] #recupera dal dizionario il codice inviato a quell'utente

    if message.text == sent_code: #se il codice inviato dall'utente è uguale a quello inviato dal bot:
        student_email = user_emails.get(user_id) 
        try:
            cursor.execute("INSERT OR IGNORE INTO studenti (id,email) VALUES (?,?)", (user_id, student_email)) #inserisce lo studente nella tabella, lo ignora se già esiste l'id
            connection.commit()

            bot.send_message(message.chat.id,"✅La tua email è stata verificata con successo.\nOra, per favore inviami la tua matricola. Fai attenzione a scriverla in maniera corretta❗")
            bot.register_next_step_handler(message, ask_matricola)
        except sqlite3.Error as e:
            print(f"Errore nel salvataggio dell'email: {e}")
        finally:
            del user_codes[user_id] #elimina il codice di verifica associato all'utente dal dizionario dopo che la verifica è stata completata con successo
            del user_emails[user_id] #elimina l'email dello studente
    else:
        bot.send_message(message.chat.id,'⚠️Codice non valido ❌, prova di nuovo') 
        bot.register_next_step_handler(message, code_verification)


#richiesta della matricola:
def ask_matricola(message) -> None:
    user_id = message.from_user.id 
    matricola = message.text #estrae la matricola dal messaggio dell'utente

    if matricola.isdigit() and len(matricola) == 6:
        try:
            cursor.execute("UPDATE studenti SET matricola = ? WHERE id = ?", (matricola, user_id)) #inserisce la matricola nello studente nella tabella, lo ignora se già esiste l'id
            connection.commit()
            bot.send_message(message.chat.id,"✅La tua matricola è stata registrata con successo.\nD\'ora in poi scrivi (o clicca):\n     ➡ /start se vuoi ricominciare da capo;\n     ➡ /menu per visualizzare le opzioni.")
        except sqlite3.Error as e:
            print(f"Errore nel salvataggio dell'email: {e}")
    else:
        bot.send_message(message.chat.id, "❌ Matricola non valida.\n❗Assicurati che contenga solo numeri e sia di 6 cifre.")
        bot.register_next_step_handler(message, ask_matricola)


#definizione gestore comando "/menu"
@bot.message_handler(commands = ["menu"])
def menu(message) -> None:
    
    menu_keyboard = types.InlineKeyboardMarkup() #definizione tastiera di bottoni

    #creazione e aggiunta bottoni
    menu_keyboard.add(types.InlineKeyboardButton(text = "Visualizza lezioni 📚", callback_data = "menu_view_lessons"))
    menu_keyboard.add(types.InlineKeyboardButton(text = "Prenota posto 🪑", callback_data = "menu_reserve_seat"))
    menu_keyboard.add(types.InlineKeyboardButton(text = "Visualizza prenotazioni 🗂", callback_data = "menu_view_bookings"))
    menu_keyboard.add(types.InlineKeyboardButton(text = "Cancella prenotazione 🗑", callback_data = "menu_delete_booking"))
    
    bot.send_message(message.chat.id, "Scegli un'opzione:", reply_markup = menu_keyboard)


#definizione gestore comando scelto dall'utente nel menu
@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def choise(call):

    chat_id = call.message.chat.id
    message_id = call.message.message_id

    bot.edit_message_reply_markup(chat_id = chat_id, message_id = message_id, reply_markup = None) #elima i bottoni dopo la scelta
    bot.delete_message(chat_id, message_id)  #elima il messagio "scegli un'opzione" dalla chat

    #definizione funzioni da richiamare
    if call.data == "menu_view_lessons":
        view_lessons(call.message.chat.id)
    elif call.data == "menu_reserve_seat":
        reserve_seat(chat_id)
    elif call.data == "menu_view_bookings":
        view_bookings(chat_id)
    elif call.data == "menu_delete_booking":
        delete_booking(chat_id)


#funzione per visualizzazione delle lezioni
def view_lessons(chat_id):
    bot.send_message(chat_id, messaggio_lezioni)


#funzione per prenotazione del posto
def reserve_seat(chat_id):
    try:
        cursor.execute("SELECT id, nome, docente, posti_disponibili, posti_prenotati FROM lezioni WHERE data = ?", (formatted_date,)) #recupera le lezioni dal database
        lezioni = cursor.fetchall()

        if lezioni:
            reservation_keyboard = types.InlineKeyboardMarkup()            
            for lezione in lezioni:
                reservation_keyboard.add(types.InlineKeyboardButton(text=f"{lezione[1].capitalize()} - {lezione[2]} ({lezione[3] - lezione[4]} posti disponibili)", callback_data=f"{lezione[0]}")) #stampa tanti bottoni quante sono le lezioni disponibili
            bot.send_message(chat_id, "Seleziona la lezione per la quale vorresti prenotare un posto tra quelle qui sotto:", reply_markup=reservation_keyboard)
        else:
            bot.send_message(chat_id, "Non ci sono lezioni disponibili per oggi.")
    except sqlite3.Error as e:
        print(f"Errore: {e}")


#definizione gestore della lezione da prenotares
@bot.callback_query_handler(func=lambda call: call.data.isdigit())
def handle_reservation(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    user_id = call.from_user.id
    lesson_id = int(call.data)

    cursor.execute("SELECT matricola FROM studenti WHERE id = ?", (user_id,)) #recupera la matricola dell'utente che poi sarà inserita nelle prenotazioni
    result = cursor.fetchone()
    
    if result: #se trova la matricola:
        user_matricola = result[0] #la memorizza
        
        cursor.execute("SELECT id FROM prenotazioni WHERE matricola = ? AND id_lezione = ?", (user_matricola, lesson_id)) #recupera (se c'è) la prenotazione dell'utente per quella materia
        prenotazione_esistente = cursor.fetchone()

        if prenotazione_esistente: #se restituisce un valore (id), vuol dire che l'utente ha già prenotato quella lezione 
           bot.edit_message_text(chat_id = chat_id, message_id = message_id, text = "⚠️ Hai già prenotato un posto per questa materia!\nPuoi controllare le tue prenotazioni dal /menu!", reply_markup = None)
        
        else: #altrimenti, non la ha ancora prenotata
            cursor.execute("SELECT posti_disponibili, posti_prenotati FROM lezioni WHERE id = ?", (lesson_id,)) #recupera i posti disponibili e quelli prenotati
            result = cursor.fetchone()

            if result: 
                posti_disponibili, posti_prenotati = result #estrae da result il numero di posti disponibili e quelli prenotati
                if posti_prenotati < posti_disponibili: #se ci sono posti disponibili
                    cursor.execute("UPDATE lezioni SET posti_prenotati = posti_prenotati + 1 WHERE id = ?", (lesson_id,)) #aumenta di 1 il numeri di posti prenotati per la lezione
                    cursor.execute("INSERT INTO prenotazioni (matricola, id_lezione) VALUES (?, ?)", (user_matricola, lesson_id)) #aggiunge una nuova prenotazione nel database
                    connection.commit()
                    bot.edit_message_text(chat_id = chat_id, message_id = message_id, text = "✅ Prenotazione avvenuta con successo! Ora puoi visualizzare o cancellare la tua prenotazione dal /menu.")
                else:
                    bot.edit_message_text(chat_id = chat_id, message_id = message_id, text = "😢 Mi dispiace, ma i posti sono esauriti per la lezione da te scelta.")


#funzione per visualizzare le prenotazioni
def view_bookings(chat_id):
    user_id = chat_id 

    cursor.execute("SELECT matricola FROM studenti WHERE id = ?", (user_id,)) #recupera la matricola dell'utente che poi sarà inserita nelle prenotazioni
    result = cursor.fetchone()

    if result: #se trova la matricola:
        user_matricola = result[0] #la memorizza
        
        cursor.execute("SELECT lezioni.nome, lezioni.docente, lezioni.aula, lezioni.data FROM prenotazioni JOIN lezioni ON prenotazioni.id_lezione = lezioni.id WHERE prenotazioni.matricola = ?", (user_matricola,)) #recupera le prenotazioni dell'utente           
        prenotazioni = cursor.fetchall()

        if prenotazioni: #se ci sono prenotazioni:
            messaggio_prenotazioni = "🗂 *Le tue prenotazioni:* \n\n"
            for prenotazione in prenotazioni:
                nome_lezione, docente, aula, data = prenotazione
                messaggio_prenotazioni += f"     📚 *Lezione*: {nome_lezione.capitalize()} - {docente}\n     🚪 *Aula*: {aula}\n     📅 *Data*: {data}\n\n"
            bot.send_message(chat_id, messaggio_prenotazioni, parse_mode=ParseMode.MARKDOWN)
        else:
            bot.send_message(chat_id, "⚠️ Non hai prenotazioni da visualizzare! Puoi prenotare un posto a lezione dal /menu.")


#funzione per la cancellazione della prenotazione
def delete_booking(chat_id):
    user_id = chat_id 

    cursor.execute("SELECT matricola FROM studenti WHERE id = ?", (user_id,)) #recupera la matricola dell'utente
    result = cursor.fetchone()
    
    if result: #se trova la matricola:
        user_matricola = result[0] #la memorizza
    
        try:
            cursor.execute("SELECT prenotazioni.id, lezioni.nome, lezioni.docente, lezioni.aula, lezioni.data FROM prenotazioni JOIN lezioni ON prenotazioni.id_lezione = lezioni.id WHERE prenotazioni.matricola = ?", (user_matricola,)) #recupera le prenotazioni           
            prenotazioni = cursor.fetchall()

            if prenotazioni: #se ci sono prenotazioni
                reservations_keyboard = types.InlineKeyboardMarkup() #crea una tastiera di bottoni           
                for prenotazione in prenotazioni: #itera sulle prenotazioni
                    prenotazione_id, nome_lezione, docente, aula, data = prenotazione
                    button_text = f"📚 Lezione: {nome_lezione.capitalize()} - {docente},🚪 Aula: {aula}, 📅 Data: {data}\n\n"
                    reservations_keyboard.add(types.InlineKeyboardButton(text= button_text, callback_data = f"delete_{prenotazione_id}")) #crea tanti bottoni quante sono le prenotazioni
                bot.send_message(chat_id, "Seleziona la lezione per la quale vorresti cancellare la prenotazione, tra quelle di seguito:", parse_mode=ParseMode.MARKDOWN,  reply_markup=reservations_keyboard) 
            else:
                bot.send_message(chat_id, "⚠️ Non hai prenotazioni da cancellare! Puoi prenotare un posto a lezione dal /menu.")
        except sqlite3.Error as e:
            print(f"Errore nel recupero delle prenotazioni: {e}")



#definizione gestore della cancellazione:
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def handle_delete_booking(call):
    chat_id = call.message.chat.id
    prenotazione_id = int(call.data.split("_")[1]) #divide la stringa "delete_{prenotazione_id}" in una lista di sottostringhe ["delete", "prenotazione_id"] e estrae il secondo elemento, ossia l'id

    try:
        
        cursor.execute("SELECT id_lezione FROM prenotazioni WHERE id = ?", (prenotazione_id,)) #recupera l'id della lezione
        result = cursor.fetchone()
        
        if result:
            id_lezione = result[0]

            cursor.execute("UPDATE lezioni SET posti_prenotati = posti_prenotati - 1 WHERE id = ?", (id_lezione,)) #aggiorna il numero di posti prenotati per la lezione
            connection.commit()

            cursor.execute("DELETE FROM prenotazioni WHERE id = ?", (prenotazione_id,)) #cancella la prenotazione dal database attraverso l'id estratto sopra
            connection.commit()

            bot.send_message(chat_id, "✅ La prenotazione è stata cancellata con successo.")
            bot.delete_message(chat_id, call.message.message_id)
        else:
            bot.send_message(chat_id, "⚠️ Errore: Prenotazione non trovata.")
    except sqlite3.Error as e:
        print(f"Errore nel cancellare la prenotazione: {e}")


#definizione gestore comandi e messaggi sconosciuti:
@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    chat_id = message.chat.id

    if message.text != "menu" and message.text != "/start":
        bot.send_message(chat_id, "😔 Mi dispiace, non riesco a trovare nulla che corrisponda alla tua richiesta. Prova di nuovo o inviami /menu")
    else:
        bot.send_message(chat_id, "😔 Mi dispiace, non riesco a trovare nulla che corrisponda alla tua richiesta. Prova di nuovo o inviami /menu")
        
bot.polling()
