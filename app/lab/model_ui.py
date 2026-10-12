"""Panel Model AI i przewodnik pierwszego uruchomienia."""
import os
import streamlit as st
from .config import ModelConfig, model_configs
from . import endpoints
from .llm import call_model, ModelError
from .local_models import RECOMMENDED_MODELS, total_ram_gb, recommended_model
from .settings import public_mode, load_settings, save_settings, settings_path

OLLAMA = 'Ollama na tym komputerze'
GOOGLE = 'Google Gemini (bezpłatny klucz)'
CUSTOM = 'Inny serwer zgodny z OpenAI (zaawansowane)'
GOOGLE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai'
GOOGLE_MODELS = ('gemma-4-31b-it', 'gemma-4-26b-a4b-it')


def _discover_ollama(root):
    return endpoints.ollama_models(root)


_FIELDS = ('ai_provider', 'google_key', 'google_verified', 'endpoint_url', 'endpoint_key',
           'endpoint_model', 'endpoint_verified', 'chosen_model')


def init_settings():
    if st.session_state.get('_settings_loaded'):
        # Streamlit usuwa wartości kontrolek, których nie renderuje dany dostawca.
        # Jawne przypisanie zachowuje ustawienia także po przełączeniu panelu.
        for name in _FIELDS:
            if name in st.session_state:
                st.session_state[name] = st.session_state[name]
        return
    try:
        saved = load_settings()
    except ValueError as exc:
        st.warning(str(exc))
        saved = {}
    for name in _FIELDS:
        if name in saved:
            st.session_state[name] = saved[name]
    st.session_state['_settings_loaded'] = True


def remember():
    try:
        value = {name: st.session_state[name] for name in _FIELDS if name in st.session_state}
        if value != st.session_state.get('_last_saved_settings'):
            save_settings(value)
            # JSON kopiuje także listy, które później zmieniają przyciski.
            import json
            st.session_state['_last_saved_settings'] = json.loads(json.dumps(value))
    except ValueError as exc:
        st.error(str(exc))


def credentials_changed(provider):
    st.session_state[provider + '_verified'] = []
    if provider == 'endpoint':
        st.session_state.pop('endpoint_models', None)
    remember()


def google_config(name):
    return ModelConfig('Google: ' + name, name, GOOGLE_URL, st.session_state.get('google_key', ''),
                       reasoning_effort='minimal', session_only=True)


def custom_config(name):
    return ModelConfig('Własny serwer: ' + name, name,
                       endpoints.endpoint_url(st.session_state.get('endpoint_url', '')),
                       st.session_state.get('endpoint_key', ''), session_only=True)


def test_connection(config):
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean', 'enum': [True]}},
              'required': ['ok'], 'additionalProperties': False}
    try:
        with st.spinner('Sprawdzam połączenie. Pierwsze uruchomienie modelu lokalnego może potrwać minutę.'):
            call_model(config, [{'role': 'user', 'content': 'Zwróć {"ok": true}.'}], schema,
                       max_tokens=32, temperature=0, bypass_cache=True, tab='Sprawdzenie połączenia')
        st.success('Połączenie działa. Model zwrócił poprawną odpowiedź JSON.')
        return True
    except ModelError:
        st.error('Połączenie nie działa lub model nie zwrócił poprawnego JSON. Sprawdź, czy serwer jest uruchomiony, a klucz poprawny. Spróbuj ponownie.')
        return False


def _download(model, root, key, disabled=False):
    if st.button('Pobierz', key=key, disabled=disabled):
        bar = st.progress(0.0, text='Rozpoczynam pobieranie modelu.')
        def progress(fraction, completed, total):
            bar.progress(fraction, text=f'Pobrano {completed / 1e9:.2f} z {total / 1e9:.2f} GB.')
        try:
            endpoints.pull_model(root, model.name, progress)
            st.session_state['_download_notice'] = 'Model został pobrany. Możesz rozpocząć ćwiczenia.'
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def recommendations(root, running, prefix):
    ram = total_ram_gb()
    recommended = recommended_model(ram)
    st.write(f'Ten komputer ma około {ram:.0f} GB pamięci RAM.' if ram is not None else
             'Nie można ustalić ilości pamięci RAM. Zalecamy Gemma 4 12B, jeśli komputer spełnia wymagania.')
    if ram is not None and ram < 12:
        st.info('Ten komputer ma mniej niż 12 GB RAM. Modele z tej listy mogą się nie uruchomić. Możesz wybrać Google Gemini w panelu Model AI.')
    st.subheader('Polecane modele')
    for model in RECOMMENDED_MODELS:
        st.write('**' + model.label + '**' + (' — rekomendacja dla tego komputera.' if model == recommended else '.'))
        memory = f'Co najmniej {model.min_ram_gb} GB RAM' + (' lub karta graficzna z 12 GB pamięci' if model.default else '')
        st.caption(f'Pobranie około {model.download_gb:.1f} GB. {memory}.')
        st.write(model.description)
        _download(model, root, prefix + model.name, disabled=not running)
    st.caption('Gemma 4 12B na karcie klasy RTX 2080 Ti: około 4 s na dokument i 10 s na paczkę 10 wierszy. Bez karty graficznej praca może być kilka razy wolniejsza.')
    st.caption('Wyniki dotyczą jednej próby 72 zapytań pakietu PROSTATA-RT z 12 października 2026 r. Nie potwierdzają przydatności klinicznej.')


def configured_models(operators, local):
    configs = dict(operators)
    if not public_mode():
        configs.update(local)
    if st.session_state.get('google_key'):
        for name in st.session_state.get('google_verified', []):
            if name in GOOGLE_MODELS:
                config = google_config(name)
                configs[config.label] = config
    if not public_mode() and st.session_state.get('endpoint_url'):
        for name in st.session_state.get('endpoint_verified', []):
            try:
                config = custom_config(name)
                configs[config.label] = config
            except ValueError:
                pass
    return configs


def default_selection(configs):
    wanted = recommended_model(total_ram_gb()).name
    return next((label for label, config in configs.items() if config.transport == 'ollama' and config.model == wanted),
                next((label for label, config in configs.items() if config.transport == 'ollama'), next(iter(configs), None)))


def model_panel():
    init_settings()
    try:
        operators = model_configs()
    except (OSError, ValueError):
        st.error('Nie można odczytać ustawień modeli administratora. Skontaktuj się z prowadzącym zajęcia.')
        operators = {}
    root = os.getenv('OLLAMA_BASE_URL') or 'http://127.0.0.1:11434'
    local, note = {}, None
    if not public_mode():
        try:
            local, note = _discover_ollama(root)
        except ValueError:
            note = 'Ollama jest niedostępna.'
    with st.expander('Model AI', expanded=not bool(configured_models(operators, local))):
        providers = [GOOGLE] if public_mode() else [OLLAMA, GOOGLE, CUSTOM]
        if st.session_state.get('ai_provider') not in providers:
            st.session_state['ai_provider'] = providers[0]
        provider = st.radio('Wybierz sposób uruchomienia modelu.', providers, key='ai_provider', on_change=remember)
        if provider == OLLAMA:
            if note:
                st.info('Ollama nie jest zainstalowana albo nie jest uruchomiona. Zainstaluj ją i otwórz program Ollama.')
                st.markdown('[Zainstaluj Ollama](https://ollama.com/download).')
            else:
                st.success('Ollama jest uruchomiona.')
                if not local:
                    st.info('Nie ma jeszcze pobranego modelu. Wybierz Pobierz poniżej.')
                for config in local.values():
                    size = f'{config.download_size / 1e9:.1f} GB' if config.download_size else 'rozmiar nieznany'
                    st.write(f'{config.model}: {size}.')
            if st.button('Sprawdź ponownie', key='ollama_refresh'):
                endpoints.refresh_ollama(root)
                st.rerun()
            recommendations(root, note is None, 'sidebar_pull:')
        elif provider == GOOGLE:
            st.write('Dane opuszczają komputer. Używaj wyłącznie danych syntetycznych.')
            st.write('1. Otwórz Google AI Studio i zaloguj się na swoje konto Google.')
            st.markdown('[Otwórz stronę kluczy Google AI Studio](https://aistudio.google.com/apikey).')
            st.write('2. Wybierz Utwórz klucz API. Skopiuj klucz i wklej go poniżej.')
            st.text_input('Twój klucz Google', type='password', key='google_key', on_change=credentials_changed, args=('google',))
            name = st.selectbox('Model Google', GOOGLE_MODELS, key='google_model')
            st.write('3. Sprawdź połączenie. Po udanej próbie model pojawi się na liście w panelu.')
            if st.button('Sprawdź połączenie', key='google_check', disabled=not st.session_state.get('google_key')):
                if test_connection(google_config(name)):
                    verified = st.session_state.setdefault('google_verified', [])
                    if name not in verified:
                        verified.append(name)
                    st.session_state['chosen_model'] = 'Google: ' + name
                    remember()
        elif provider == CUSTOM and not public_mode():
            st.text_input('Adres serwera OpenAI API', key='endpoint_url', placeholder='http://localhost:1234/v1',
                          on_change=credentials_changed, args=('endpoint',))
            st.text_input('Klucz API (opcjonalny)', type='password', key='endpoint_key', on_change=credentials_changed, args=('endpoint',))
            if st.button('Pobierz listę modeli', key='endpoint_fetch'):
                try:
                    st.session_state['endpoint_models'] = endpoints.endpoint_models(st.session_state.endpoint_url, st.session_state.get('endpoint_key', ''))
                except ValueError as exc:
                    st.session_state['endpoint_models'] = []
                    st.error(str(exc))
            if st.session_state.get('endpoint_models'):
                name = st.selectbox('Modele na serwerze', st.session_state.endpoint_models, key='endpoint_pick')
                if st.button('Sprawdź połączenie', key='endpoint_use'):
                    if test_connection(custom_config(name)):
                        verified = st.session_state.setdefault('endpoint_verified', [])
                        if name not in verified:
                            verified.append(name)
                        st.session_state['endpoint_model'] = name
                        st.session_state['chosen_model'] = 'Własny serwer: ' + name
                        remember()
        if public_mode():
            st.caption('Klucz i wybór modelu pozostają tylko w tej sesji. Po zamknięciu sesji wpisz je ponownie.')
        else:
            st.caption('Ustawienia modelu i klucze są zapamiętywane na tym komputerze w pliku ustawienia.json w katalogu danych użytkownika.')
            with st.expander('Informacje techniczne'):
                st.code(str(settings_path()), language=None)
    if st.session_state.get('_download_notice'):
        st.success(st.session_state.pop('_download_notice'))
    configs = configured_models(operators, local)
    if st.session_state.get('chosen_model') not in configs:
        st.session_state['chosen_model'] = default_selection(configs)
    chosen = st.selectbox('Model', list(configs), key='chosen_model', disabled=not configs, on_change=remember,
                          placeholder='Najpierw skonfiguruj model w panelu Model AI.')
    if chosen:
        remember()
        if st.button('Sprawdź połączenie', key='selected_check'):
            test_connection(configs[chosen])
    return configs, chosen, root, note


def first_run_guide(root, note):
    st.subheader('Uruchom swój pierwszy model AI')
    if public_mode():
        st.info('Model nie jest jeszcze skonfigurowany. Otwórz Model AI w panelu po lewej i dodaj własny klucz Google lub poproś prowadzącego o uruchomienie modelu zajęć.')
        return
    st.write('1. Zainstaluj Ollama i otwórz ten program.')
    st.markdown('[Pobierz Ollama](https://ollama.com/download).')
    if st.button('Sprawdź ponownie', key='start_ollama_refresh'):
        endpoints.refresh_ollama(root)
        st.rerun()
    st.write('2. Pobierz polecany model jednym przyciskiem.')
    recommendations(root, note is None, 'start_pull:')
    st.write('3. Gotowe. Po pobraniu model zostanie wybrany automatycznie. Możesz rozpocząć ćwiczenia.')
