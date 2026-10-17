"""User-facing messages in Italian and English, picked by UI language (Accept-Language header)."""

from contextvars import ContextVar

LANGUAGES = ("it", "en")
DEFAULT_LANGUAGE = "it"

current_language: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)

MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "application_not_found": "Candidatura non trovata",
        "event_not_found": "Evento non trovato",
        "event_field_required": "Tipo, data, titolo e completamento non possono essere vuoti",
        "advice_running": "Analisi già in corso",
        "no_cv": "Nessun CV caricato",
        "upload_first_cv": "Carica prima il CV",
        "file_too_large": "File oltre {mb} MB",
        "file_empty": "File vuoto",
        "ai_disabled": "Le funzioni AI sono disattivate nelle impostazioni",
        "no_saved_posting": "Per questa candidatura non è salvato il testo dell'annuncio",
        "posting_too_short": "Il testo dell'annuncio è troppo corto",
        "task_not_found": "Attività non trovata: forse il backend è stato riavviato",
        "task_failed": "Errore imprevisto durante l'elaborazione",
        "unsupported_format": "Formato {suffix} non supportato. Usa {supported}.",
        "unknown_format": "sconosciuto",
        "no_text": "Il documento non contiene testo estraibile (forse è una scansione).",
        "llm_starting": "Il modello si sta ancora avviando: riprova tra poco",
        "llm_http_error": "Ollama ha risposto {code}: {text}",
        "llm_unreachable": "Impossibile contattare Ollama su {url}: {error}",
        "llm_invalid": "Risposta del modello non valida: {error}",
        "level_basic": "Livello base: da approfondire con un uso pratico",
        "level_too_low_senior": "Livello {level}: per una posizione senior serve più esperienza",
        "level_1": "base",
        "level_2": "intermedio",
        "level_3": "avanzato",
        "level_4": "esperto",
        "paste_hint": "Apri l'annuncio nel browser, copia il testo e incollalo nella scheda Testo.",
        "link_scheme": "Il link deve iniziare con http:// o https://",
        "page_no_text": "Nella pagina non ho trovato il testo dell'annuncio: probabilmente richiede il login o viene "
                        "caricato via JavaScript. {hint}",
        "site_blocked": "Il sito ha bloccato lo scaricamento automatico (errore {code}). {hint}",
        "page_error": "La pagina ha risposto con errore {code}.",
        "page_too_large": "La pagina è troppo grande.",
        "page_unreachable": "Impossibile raggiungere la pagina: {error}",
        "salary_up_to": "fino a {amount}",
        "salary_from": "da {amount}",
        "salary_payments": "{amount} × {count} mensilità",
        "advice_language": "italiano",
        "not_authenticated": "Sessione scaduta: accedi di nuovo",
        "admin_required": "Operazione riservata agli amministratori",
        "invalid_credentials": "Username o password non corretti",
        "account_locked": "Troppi tentativi falliti: account bloccato per {minutes} min",
        "setup_done": "L'amministratore è già stato creato",
        "username_taken": "Username già in uso",
        "email_taken": "Email già in uso",
        "invalid_recovery_key": "Username o chiave di recupero non corretti",
        "wrong_password": "Password attuale non corretta",
        "password_invalid": "La password deve avere {rules}",
        "password_rule_length": "almeno {count} caratteri",
        "password_rule_uppercase": "una lettera maiuscola",
        "password_rule_digit": "un numero",
        "password_rule_symbol": "un simbolo",
        "last_admin": "Deve restare almeno un amministratore",
        "cannot_delete_self": "Non puoi eliminare il tuo account",
        "user_not_found": "Utente non trovato",
        "invalid_image": "Immagine non valida: usa JPG, PNG, WebP o GIF",
        "no_avatar": "Nessuna foto profilo",
        "skill_from_project": "Progetto {name}",
        "skill_from_experience": "Esperienza {name}",
    },
    "en": {
        "application_not_found": "Application not found",
        "event_not_found": "Event not found",
        "event_field_required": "Type, date, title and completion can't be empty",
        "advice_running": "Analysis already in progress",
        "no_cv": "No CV uploaded",
        "upload_first_cv": "Upload your CV first",
        "file_too_large": "File larger than {mb} MB",
        "file_empty": "Empty file",
        "ai_disabled": "AI features are turned off in the settings",
        "no_saved_posting": "No job posting text is saved for this application",
        "posting_too_short": "The job posting text is too short",
        "task_not_found": "Task not found: the backend may have been restarted",
        "task_failed": "Unexpected error while processing",
        "unsupported_format": "Format {suffix} is not supported. Use {supported}.",
        "unknown_format": "unknown",
        "no_text": "The document contains no extractable text (it may be a scan).",
        "llm_starting": "The model is still starting: try again shortly",
        "llm_http_error": "Ollama answered {code}: {text}",
        "llm_unreachable": "Cannot reach Ollama at {url}: {error}",
        "llm_invalid": "Invalid model response: {error}",
        "level_basic": "Basic level: needs hands-on practice",
        "level_too_low_senior": "{level} level: a senior role needs more experience",
        "level_1": "Basic",
        "level_2": "Intermediate",
        "level_3": "Advanced",
        "level_4": "Expert",
        "paste_hint": "Open the posting in your browser, copy the text and paste it in the Text tab.",
        "link_scheme": "The link must start with http:// or https://",
        "page_no_text": "I could not find the job posting text on the page: it probably requires a login or is "
                        "loaded with JavaScript. {hint}",
        "site_blocked": "The site blocked the automatic download (error {code}). {hint}",
        "page_error": "The page answered with error {code}.",
        "page_too_large": "The page is too large.",
        "page_unreachable": "Cannot reach the page: {error}",
        "salary_up_to": "up to {amount}",
        "salary_from": "from {amount}",
        "salary_payments": "{amount} × {count} monthly payments",
        "advice_language": "English",
        "not_authenticated": "Session expired: please sign in again",
        "admin_required": "Only administrators can do this",
        "invalid_credentials": "Wrong username or password",
        "account_locked": "Too many failed attempts: account locked for {minutes} min",
        "setup_done": "The administrator has already been created",
        "username_taken": "Username already in use",
        "email_taken": "Email already in use",
        "invalid_recovery_key": "Wrong username or recovery key",
        "wrong_password": "Current password is wrong",
        "password_invalid": "The password needs {rules}",
        "password_rule_length": "at least {count} characters",
        "password_rule_uppercase": "an uppercase letter",
        "password_rule_digit": "a digit",
        "password_rule_symbol": "a symbol",
        "last_admin": "At least one administrator must remain",
        "cannot_delete_self": "You can't delete your own account",
        "user_not_found": "User not found",
        "invalid_image": "Invalid image: use JPG, PNG, WebP or GIF",
        "no_avatar": "No profile picture",
        "skill_from_project": "Project {name}",
        "skill_from_experience": "Experience {name}",
    },
}


def t(key: str, **values) -> str:
    return MESSAGES[current_language.get()][key].format(**values)


def parse_language(header: str) -> str:
    """First supported language in the Accept-Language header (e.g. "en-GB,en;q=0.9")."""
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2].lower()
        if code in LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


class LanguageMiddleware:
    """Set the request language; also applies to background tasks it starts."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            current_language.set(parse_language(headers.get(b"accept-language", b"").decode("latin-1")))
        await self.app(scope, receive, send)
