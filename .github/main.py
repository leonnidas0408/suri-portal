import json
import os
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.utils import platform

import requests

# ---------------------------------------------------------------------------
# Configuração da API (mesma lógica que já funcionava no desktop)
# ---------------------------------------------------------------------------
API_BASE = "https://smartv5.escolarmanageronline.com.br"
DOMINIO = "grupofractal"

DEFAULT_TOKEN = (
    "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxOTAzNDAiLCJ0eXAiOiJBTCIsIm5iZiI6"
    "MTc1Nzk1ODcwMCwiaWF0IjoxNzU3OTU4NzAwLCJ0ZW5hbnQiOiJncnVwb2ZyYWN0YWwiLCJleHAiOjE4MjEwMzA3MDB9."
    "Wa6wigkqiACXyCNF-gR2JvyNqYGgtNbpGtjNX1LuyIgtthJ98S_6pgclYY8X8FYaF1jaB4S7wyCQoLNzwNotWg"
)

INVALID_FOLDER_MARKER = '"des":"Financeiro"'

DEFAULT_CATEGORIES = [
    {"id": "conteudos", "label": "CONTEÚDOS E TAREFAS", "code": "111"},
    {"id": "faltas",    "label": "FALTAS",              "code": "22"},
    {"id": "saida",     "label": "SAÍDA ANTECIPADA",    "code": "108"},
    {"id": "listas",    "label": "LISTAS OBRIGATÓRIAS", "code": "124"},
]

EXTENSION_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def guess_extension(content_type: str) -> str:
    if not content_type:
        return ".pdf"
    content_type = content_type.split(";")[0].strip().lower()
    return EXTENSION_BY_CONTENT_TYPE.get(content_type, ".pdf")


# ---------------------------------------------------------------------------
# Caminhos (em Android usa a pasta privada do app; no desktop usa a pasta local)
# ---------------------------------------------------------------------------
if platform == "android":
    from android.storage import app_storage_path  # noqa: E402
    BASE_DIR = app_storage_path()
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "portal_aluno_config.json")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("categories"):
                data["categories"] = DEFAULT_CATEGORIES
            return data
        except Exception:
            pass
    return {"matricula": "", "token": DEFAULT_TOKEN, "categories": DEFAULT_CATEGORIES}


def save_config(config: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("Falha ao salvar configuração:", exc)


# ---------------------------------------------------------------------------
# Chamadas de API
# ---------------------------------------------------------------------------
def auth_headers(token: str) -> dict:
    return {
        "dominio": DOMINIO,
        "user-agent": "Versao/2026.01.02",
        "accept-encoding": "gzip",
        "authorization": "Bearer " + token,
        "content-type": "application/json",
    }


def fetch_folder_items(matricula: str, token: str, pasta_codigo: str):
    try:
        resp = requests.post(
            f"{API_BASE}/publicacoes/ConsultePublicacaoAlunoPasta",
            json={"Matricula": int(matricula), "PastaCodigo": int(pasta_codigo)},
            headers=auth_headers(token),
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, f"Não foi possível conectar ao servidor da escola: {exc}"

    if not resp.ok:
        return False, f"A escola respondeu com erro ({resp.status_code}). Verifique matrícula e token."

    if INVALID_FOLDER_MARKER in resp.text:
        return True, []

    try:
        data = resp.json()
    except ValueError:
        return False, "Resposta inesperada do servidor."

    items = data[0].get("pub", []) if data else []
    return True, items


def download_item_bytes(url: str, token: str):
    resp = requests.get(
        f"{API_BASE}/{url}",
        headers={"dominio": DOMINIO, "authorization": "Bearer " + token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "")


def open_or_share_file(path: str):
    """No Android abre o seletor de apps (share); no desktop abre com o app padrão."""
    if platform == "android":
        try:
            from plyer import share
            share.share(filepath=path)
            return
        except Exception as exc:
            print("share falhou:", exc)
    try:
        if platform == "win":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform == "macosx":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception as exc:
        print("abrir falhou:", exc)


def info_popup(title: str, message: str):
    Popup(
        title=title,
        content=Label(text=message, text_size=(320, None)),
        size_hint=(0.85, 0.4),
    ).open()


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = load_config()

        root = BoxLayout(orientation="vertical", padding=24, spacing=12)
        root.add_widget(Label(
            text="Fractal - Portal do Aluno", font_size=22, size_hint_y=None, height=60
        ))

        root.add_widget(Label(text="Matrícula", size_hint_y=None, height=24, halign="left"))
        self.matricula_input = TextInput(
            text=self.config_data.get("matricula", ""),
            multiline=False, size_hint_y=None, height=44
        )
        root.add_widget(self.matricula_input)

        self.token_toggle_btn = Button(
            text="Configurar token (opcional)", size_hint_y=None, height=36
        )
        self.token_toggle_btn.bind(on_release=self.toggle_token_field)
        root.add_widget(self.token_toggle_btn)

        self.token_box = BoxLayout(orientation="vertical", size_hint_y=None, height=0, opacity=0)
        self.token_box.add_widget(Label(text="Token (Bearer)", size_hint_y=None, height=24))
        self.token_input = TextInput(multiline=False, size_hint_y=None, height=44)
        self.token_box.add_widget(self.token_input)
        root.add_widget(self.token_box)

        root.add_widget(BoxLayout())  # spacer

        login_btn = Button(text="ACESSAR", size_hint_y=None, height=48)
        login_btn.bind(on_release=self.do_login)
        root.add_widget(login_btn)

        self.add_widget(root)

    def toggle_token_field(self, *_):
        if self.token_box.height == 0:
            self.token_box.height = 100
            self.token_box.opacity = 1
        else:
            self.token_box.height = 0
            self.token_box.opacity = 0

    def do_login(self, *_):
        matricula = self.matricula_input.text.strip()
        if not matricula:
            info_popup("Matrícula", "Informe a matrícula.")
            return
        token_val = self.token_input.text.strip()
        self.config_data["matricula"] = matricula
        if token_val:
            self.config_data["token"] = token_val
        elif not self.config_data.get("token"):
            self.config_data["token"] = DEFAULT_TOKEN
        save_config(self.config_data)

        menu_screen = self.manager.get_screen("menu")
        menu_screen.reload(self.config_data)
        self.manager.current = "menu"


class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = load_config()
        self.root_box = BoxLayout(orientation="vertical", padding=16, spacing=10)
        self.add_widget(self.root_box)
        self.build()

    def reload(self, config_data):
        self.config_data = config_data
        self.build()

    def build(self):
        self.root_box.clear_widgets()

        top = BoxLayout(size_hint_y=None, height=44)
        top.add_widget(Label(text="Categorias", font_size=18, halign="left"))
        settings_btn = Button(text="Configurações", size_hint_x=None, width=140)
        settings_btn.bind(on_release=self.go_settings)
        top.add_widget(settings_btn)
        self.root_box.add_widget(top)

        grid = GridLayout(cols=2, spacing=8, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for cat in self.config_data.get("categories", DEFAULT_CATEGORIES):
            has_code = bool(cat.get("code"))
            label = cat["label"] + ("" if has_code else "\n(sem código)")
            btn = Button(text=label, size_hint_y=None, height=90)
            btn.bind(on_release=lambda inst, c=cat: self.open_category(c))
            grid.add_widget(btn)

        scroll = ScrollView()
        scroll.add_widget(grid)
        self.root_box.add_widget(scroll)

        logout_btn = Button(text="Sair / trocar de conta", size_hint_y=None, height=40)
        logout_btn.bind(on_release=self.logout)
        self.root_box.add_widget(logout_btn)

    def go_settings(self, *_):
        settings_screen = self.manager.get_screen("settings")
        settings_screen.reload(self.config_data)
        self.manager.current = "settings"

    def open_category(self, cat):
        if not cat.get("code"):
            self.go_settings()
            return
        items_screen = self.manager.get_screen("items")
        items_screen.load_category(self.config_data, cat)
        self.manager.current = "items"

    def logout(self, *_):
        self.config_data["matricula"] = ""
        save_config(self.config_data)
        login_screen = self.manager.get_screen("login")
        login_screen.config_data = self.config_data
        login_screen.matricula_input.text = ""
        self.manager.current = "login"


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = load_config()
        self.category_rows = []  # (cat_dict, name_input, code_input)
        self.root_box = BoxLayout(orientation="vertical", padding=16, spacing=10)
        self.add_widget(self.root_box)

    def reload(self, config_data):
        self.config_data = config_data
        self.categories = [dict(c) for c in config_data.get("categories", DEFAULT_CATEGORIES)]
        self.build()

    def build(self):
        self.root_box.clear_widgets()

        top = BoxLayout(size_hint_y=None, height=44)
        back_btn = Button(text="< Voltar", size_hint_x=None, width=100)
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        top.add_widget(back_btn)
        top.add_widget(Label(text="Configurações", font_size=18))
        self.root_box.add_widget(top)

        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None, padding=(0, 8))
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(Label(text="Matrícula", size_hint_y=None, height=24))
        self.matricula_input = TextInput(
            text=self.config_data.get("matricula", ""), multiline=False,
            size_hint_y=None, height=44
        )
        form.add_widget(self.matricula_input)

        form.add_widget(Label(text="Token (Bearer)", size_hint_y=None, height=24))
        self.token_input = TextInput(
            text=self.config_data.get("token", ""), multiline=False,
            size_hint_y=None, height=44
        )
        form.add_widget(self.token_input)

        form.add_widget(Label(
            text="Categorias (nome e código da pasta / PastaCodigo)",
            size_hint_y=None, height=24
        ))

        self.category_rows = []
        for cat in self.categories:
            form.add_widget(self._build_category_row(cat, form))

        add_btn = Button(text="+ Adicionar categoria", size_hint_y=None, height=40)
        add_btn.bind(on_release=lambda *_: self._add_category(form))
        form.add_widget(add_btn)

        scroll.add_widget(form)
        self.root_box.add_widget(scroll)

        save_btn = Button(text="SALVAR", size_hint_y=None, height=48)
        save_btn.bind(on_release=self.save_settings)
        self.root_box.add_widget(save_btn)

    def _build_category_row(self, cat, form):
        row = BoxLayout(size_hint_y=None, height=44, spacing=6)
        name_input = TextInput(text=cat.get("label", ""), multiline=False)
        code_input = TextInput(text=cat.get("code", ""), multiline=False, size_hint_x=None, width=80)
        remove_btn = Button(text="✕", size_hint_x=None, width=40)

        def remove(*_):
            self.categories.remove(cat)
            self.build()

        remove_btn.bind(on_release=remove)
        row.add_widget(name_input)
        row.add_widget(code_input)
        row.add_widget(remove_btn)
        self.category_rows.append((cat, name_input, code_input))
        return row

    def _add_category(self, form):
        self.categories.append({"id": f"cat{len(self.categories)}", "label": "NOVA CATEGORIA", "code": ""})
        self.build()

    def save_settings(self, *_):
        self.config_data["matricula"] = self.matricula_input.text.strip()
        self.config_data["token"] = self.token_input.text.strip() or DEFAULT_TOKEN
        updated = []
        for cat, name_input, code_input in self.category_rows:
            updated.append({
                "id": cat.get("id"),
                "label": name_input.text.strip() or "CATEGORIA",
                "code": code_input.text.strip(),
            })
        self.config_data["categories"] = updated
        save_config(self.config_data)

        menu_screen = self.manager.get_screen("menu")
        menu_screen.reload(self.config_data)
        login_screen = self.manager.get_screen("login")
        login_screen.config_data = self.config_data
        info_popup("Configurações", "Configurações salvas.")
        self.manager.current = "menu"


class ItemsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical", padding=16, spacing=10)
        self.add_widget(self.root_box)

    def load_category(self, config_data, cat):
        self.config_data = config_data
        self.cat = cat
        self.root_box.clear_widgets()

        top = BoxLayout(size_hint_y=None, height=44)
        back_btn = Button(text="< Voltar", size_hint_x=None, width=100)
        back_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        top.add_widget(back_btn)
        top.add_widget(Label(text=cat["label"], font_size=16))
        self.root_box.add_widget(top)

        self.status_label = Label(text="Carregando...")
        self.root_box.add_widget(self.status_label)

        def worker():
            matricula = config_data.get("matricula", "")
            token = config_data.get("token", DEFAULT_TOKEN)
            ok, result = fetch_folder_items(matricula, token, cat["code"])
            Clock.schedule_once(lambda dt: self.on_loaded(ok, result))

        threading.Thread(target=worker, daemon=True).start()

    def on_loaded(self, ok, result):
        self.root_box.remove_widget(self.status_label)

        if not ok:
            self.root_box.add_widget(Label(text=result, text_size=(320, None)))
            return

        items = result
        if not items:
            self.root_box.add_widget(Label(text="Nada por aqui ainda nesta categoria."))
            return

        list_box = GridLayout(cols=1, spacing=6, size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter("height"))
        for item in items:
            list_box.add_widget(self._build_item_row(item))

        scroll = ScrollView()
        scroll.add_widget(list_box)
        self.root_box.add_widget(scroll)

    def _build_item_row(self, item):
        row = BoxLayout(size_hint_y=None, height=56, spacing=6)
        title = item.get("tit") or "Documento"
        row.add_widget(Label(text=title, text_size=(180, None), halign="left"))

        open_btn = Button(text="Abrir", size_hint_x=None, width=70)
        download_btn = Button(text="Baixar", size_hint_x=None, width=70)

        open_btn.bind(on_release=lambda *_: self._fetch_item(item, open_btn))
        download_btn.bind(on_release=lambda *_: self._fetch_item(item, download_btn))

        row.add_widget(open_btn)
        row.add_widget(download_btn)
        return row

    def _fetch_item(self, item, btn):
        token = self.config_data.get("token", DEFAULT_TOKEN)
        title = item.get("tit") or "documento"
        url = item.get("url")
        original_text = btn.text
        btn.text = "..."
        btn.disabled = True

        def worker():
            try:
                content, content_type = download_item_bytes(url, token)
            except Exception as exc:
                Clock.schedule_once(lambda dt: self._on_fetch_error(btn, original_text, exc))
                return
            Clock.schedule_once(lambda dt: self._on_fetch_done(btn, original_text, title, content, content_type))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_error(self, btn, original_text, exc):
        btn.text = original_text
        btn.disabled = False
        info_popup("Erro", f"Não foi possível abrir este item: {exc}")

    def _on_fetch_done(self, btn, original_text, title, content, content_type):
        btn.text = original_text
        btn.disabled = False
        ext = guess_extension(content_type)
        safe_name = "".join(c for c in title if c not in '\\/:*?"<>|').strip() or "documento"
        path = os.path.join(DOWNLOAD_DIR, safe_name + ext)
        with open(path, "wb") as f:
            f.write(content)
        open_or_share_file(path)


class PortalApp(App):
    def build(self):
        self.title = "Fractal - Portal do Aluno"
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(ItemsScreen(name="items"))

        config_data = load_config()
        if config_data.get("matricula"):
            sm.get_screen("menu").reload(config_data)
            sm.current = "menu"
        else:
            sm.current = "login"
        return sm


if __name__ == "__main__":
    PortalApp().run()
