"""Suri Portal do Aluno: interface Android e fluxo de sincronização com a API escolar."""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from functools import partial

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from api_client import (
    DEFAULT_CATEGORIES,
    AuthenticationError,
    PortalApi,
    PortalApiError,
)

# Paleta: clara e calma, com contraste alto e acento índigo.
BG = (0.953, 0.965, 0.984, 1)
SURFACE = (1, 1, 1, 1)
INK = (0.090, 0.129, 0.220, 1)
MUTED = (0.388, 0.439, 0.529, 1)
BRAND = (0.255, 0.337, 0.816, 1)
BRAND_DARK = (0.188, 0.259, 0.694, 1)
TEAL = (0.055, 0.584, 0.490, 1)
PALE_BLUE = (0.914, 0.929, 0.992, 1)
PALE_GREEN = (0.894, 0.957, 0.925, 1)
PALE_RED = (0.992, 0.918, 0.922, 1)
BORDER = (0.886, 0.902, 0.929, 1)

if platform == "android":
    from android.storage import app_storage_path  # noqa: E402
    BASE_DIR = app_storage_path()
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "portal_aluno_config.json")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def load_config() -> dict:
    defaults = {
        "matricula": "",
        "token": "",
        "categories": [dict(category) for category in DEFAULT_CATEGORIES],
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            saved = json.load(file)
        if not isinstance(saved, dict):
            return defaults
        defaults.update(saved)
        if not isinstance(defaults.get("categories"), list) or not defaults["categories"]:
            defaults["categories"] = [dict(category) for category in DEFAULT_CATEGORIES]
        defaults["categories"] = [
            dict(category) for category in defaults["categories"]
            if isinstance(category, dict) and category.get("label")
        ] or [dict(category) for category in DEFAULT_CATEGORIES]
        defaults["matricula"] = str(defaults.get("matricula", ""))
        defaults["token"] = str(defaults.get("token", ""))
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def save_config(config: dict) -> None:
    os.makedirs(BASE_DIR, exist_ok=True)
    temp_path = CONFIG_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, CONFIG_PATH)


def safe_filename(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(value or "")).strip().strip(".")
    return (name[:100] or "documento")


def file_extension(content_type: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    extensions = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }
    return extensions.get(content_type, ".pdf")


def open_android_file(path: str, content_type: str) -> None:
    """Abre ou compartilha arquivo privado usando URI de conteúdo concedida pelo FileProvider."""
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    file_provider = autoclass("androidx.core.content.FileProvider")
    java_file = autoclass("java.io.File")(path)
    intent_class = autoclass("android.content.Intent")
    authority = str(activity.getPackageName()) + ".fileprovider"
    uri = file_provider.getUriForFile(activity, authority, java_file)
    mime = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()

    view_intent = intent_class(intent_class.ACTION_VIEW)
    view_intent.setDataAndType(uri, mime)
    view_intent.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
    try:
        activity.startActivity(view_intent)
    except Exception:
        send_intent = intent_class(intent_class.ACTION_SEND)
        send_intent.setType(mime)
        send_intent.putExtra(intent_class.EXTRA_STREAM, uri)
        send_intent.addFlags(intent_class.FLAG_GRANT_READ_URI_PERMISSION)
        chooser = intent_class.createChooser(send_intent, "Abrir ou compartilhar documento")
        activity.startActivity(chooser)


def add_background(widget, color=BG):
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda instance, value: setattr(rect, "pos", value))
    widget.bind(size=lambda instance, value: setattr(rect, "size", value))


def make_label(text, size=14, color=INK, bold=False, height=28, halign="left"):
    widget = Label(
        text=str(text),
        size_hint_y=None,
        height=dp(height),
        font_size=sp(size),
        color=color,
        bold=bold,
        halign=halign,
        valign="middle",
    )
    widget.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
    return widget


def make_input(text="", hint="", password=False, height=54, input_filter=None):
    widget = TextInput(
        text=str(text or ""),
        hint_text=hint,
        multiline=False,
        password=password,
        input_filter=input_filter,
        size_hint_y=None,
        height=dp(height),
        padding=(dp(14), dp(15)),
        font_size=sp(15),
        foreground_color=INK,
        hint_text_color=(0.56, 0.60, 0.67, 1),
        cursor_color=BRAND,
        background_normal="",
        background_active="",
        background_color=(0.957, 0.965, 0.980, 1),
    )
    return widget


class Panel(BoxLayout):
    def __init__(self, fill=SURFACE, radius=18, **kwargs):
        super().__init__(**kwargs)
        self._fill = fill
        with self.canvas.before:
            self._color = Color(*fill)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class ActionButton(Button):
    fill = ListProperty(list(BRAND))
    text_color = ListProperty([1, 1, 1, 1])

    def __init__(self, fill=None, text_color=None, **kwargs):
        kwargs.setdefault("font_size", sp(14))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        super().__init__(**kwargs)
        if fill is not None:
            self.fill = list(fill)
        if text_color is not None:
            self.text_color = list(text_color)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = self.text_color
        self.halign = "center"
        self.valign = "middle"
        with self.canvas.before:
            self._color = Color(*self.fill)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(15)])
        self.bind(pos=self._sync, size=self._sync, fill=self._fill_changed, text_color=self._text_changed)

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _fill_changed(self, *_):
        if hasattr(self, "_color"):
            self._color.rgba = self.fill

    def _text_changed(self, *_):
        self.color = self.text_color


class BrandMark(Panel):
    def __init__(self, **kwargs):
        super().__init__(fill=BRAND, radius=23, size_hint=(None, None), size=(dp(70), dp(70)), **kwargs)
        self.add_widget(Label(text="S", font_size=sp(38), bold=True, color=(1, 1, 1, 1)))


class AppScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        add_background(self, BG)


class LoginScreen(AppScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config = load_config()
        self.config_data = config
        root = BoxLayout(orientation="vertical", padding=(dp(20), dp(10)), spacing=dp(8))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = BoxLayout(
            orientation="vertical", size_hint_y=None,
            padding=(dp(4), dp(20), dp(4), dp(24)), spacing=dp(14),
        )
        content.bind(minimum_height=content.setter("height"))

        brand_row = BoxLayout(size_hint_y=None, height=dp(78), spacing=dp(15))
        brand_row.add_widget(BrandMark())
        wordmark = BoxLayout(orientation="vertical", spacing=dp(2))
        wordmark.add_widget(make_label("Suri", size=27, color=INK, bold=True, height=38))
        wordmark.add_widget(make_label("PORTAL DO ALUNO", size=11, color=MUTED, bold=True, height=23))
        brand_row.add_widget(wordmark)
        brand_row.add_widget(WidgetSpacer())
        content.add_widget(brand_row)
        content.add_widget(make_label("A escola, mais perto.", size=24, bold=True, height=36))
        content.add_widget(make_label("Entre para consultar publicações e documentos da sua escola.", size=14, color=MUTED, height=46))

        form = Panel(orientation="vertical", padding=dp(18), spacing=dp(10), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(make_label("Matrícula", size=13, bold=True, height=24))
        self.matricula_input = make_input(config.get("matricula", ""), "Digite sua matrícula", input_filter="int")
        form.add_widget(self.matricula_input)
        form.add_widget(make_label("Token de acesso", size=13, bold=True, height=24))
        self.token_input = make_input(config.get("token", ""), "Cole o token fornecido pela escola", password=True)
        form.add_widget(self.token_input)
        form.add_widget(make_label("O token fica salvo apenas neste aparelho e é enviado somente à API da escola.", size=11, color=MUTED, height=38))
        content.add_widget(form)

        self.status_label = make_label("", size=13, color=MUTED, height=42)
        content.add_widget(self.status_label)
        self.login_button = ActionButton(text="Conectar à escola", fill=BRAND)
        self.login_button.bind(on_release=self.connect)
        content.add_widget(self.login_button)
        content.add_widget(make_label("Ainda não tem um token? Solicite o acesso à secretaria da escola.", size=12, color=MUTED, height=44, halign="center"))
        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def connect(self, *_):
        matricula = self.matricula_input.text.strip()
        token = self.token_input.text.strip()
        if not matricula or not matricula.isdigit():
            self.status_label.text = "Digite uma matrícula numérica válida."
            self.status_label.color = (0.73, 0.20, 0.25, 1)
            return
        if not token:
            self.status_label.text = "Informe o token de acesso da escola."
            self.status_label.color = (0.73, 0.20, 0.25, 1)
            return

        self.login_button.disabled = True
        self.login_button.text = "Conectando…"
        self.status_label.color = MUTED
        self.status_label.text = "Validando seus dados com a API da escola…"
        config = dict(self.config_data)
        config.update({"matricula": matricula, "token": token})
        categories = config.get("categories") or [dict(item) for item in DEFAULT_CATEGORIES]
        first_code = str(categories[0].get("code", "111"))
        threading.Thread(target=self._connect_worker, args=(config, first_code), daemon=True).start()

    def _connect_worker(self, config, first_code):
        try:
            items = self.app.api_client.fetch_folder_items(config["matricula"], config["token"], first_code)
            save_config(config)
            Clock.schedule_once(partial(self._connected, config, first_code, items), 0)
        except PortalApiError as exc:
            Clock.schedule_once(partial(self._connect_failed, str(exc)), 0)
        except Exception:
            Clock.schedule_once(partial(self._connect_failed, "O app não conseguiu concluir a conexão. Tente novamente."), 0)

    def _connected(self, config, first_code, items, _dt):
        self.login_button.disabled = False
        self.login_button.text = "Conectar à escola"
        menu = self.manager.get_screen("home")
        menu.reload(config)
        menu.cache[first_code] = items
        menu.set_status("Conectado e sincronizado agora", success=True)
        self.manager.current = "home"

    def _connect_failed(self, message, _dt):
        self.login_button.disabled = False
        self.login_button.text = "Tentar novamente"
        self.status_label.text = message
        self.status_label.color = (0.73, 0.20, 0.25, 1)


class WidgetSpacer(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class HomeScreen(AppScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = load_config()
        self.cache = {}
        self.root_box = BoxLayout(orientation="vertical", padding=(dp(18), dp(14)), spacing=dp(12))
        self.add_widget(self.root_box)
        self.build()

    def reload(self, config_data):
        self.config_data = dict(config_data)
        self.cache = {}
        self.build()

    def build(self):
        self.root_box.clear_widgets()
        header = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(10))
        header.add_widget(make_label("Suri", size=23, bold=True, height=48))
        header.add_widget(WidgetSpacer())
        settings = ActionButton(text="Ajustes", fill=PALE_BLUE, text_color=BRAND, size_hint_x=None, width=dp(92), height=dp(42), font_size=sp(12))
        settings.bind(on_release=self.open_settings)
        header.add_widget(settings)
        self.root_box.add_widget(header)

        self.root_box.add_widget(make_label("Seu portal escolar", size=23, bold=True, height=34))
        self.root_box.add_widget(make_label("Publicações, avisos e documentos em um só lugar.", size=13, color=MUTED, height=27))

        status_panel = Panel(orientation="horizontal", padding=(dp(13), dp(9)), spacing=dp(10), size_hint_y=None, height=dp(58), fill=PALE_GREEN)
        status_dot = Label(text="●", size_hint_x=None, width=dp(18), font_size=sp(16), color=TEAL)
        status_panel.add_widget(status_dot)
        self.status_label = make_label("Aguardando sincronização", size=12, color=TEAL, bold=True, height=36)
        status_panel.add_widget(self.status_label)
        self.root_box.add_widget(status_panel)

        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        actions.add_widget(make_label("Categorias", size=16, bold=True, height=40))
        actions.add_widget(WidgetSpacer())
        self.refresh_button = ActionButton(text="Sincronizar", fill=SURFACE, text_color=BRAND, size_hint_x=None, width=dp(112), height=dp(40), font_size=sp(12))
        self.refresh_button.bind(on_release=self.refresh)
        actions.add_widget(self.refresh_button)
        self.root_box.add_widget(actions)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        grid = GridLayout(cols=1, spacing=dp(10), size_hint_y=None, padding=(0, dp(2), 0, dp(8)))
        grid.bind(minimum_height=grid.setter("height"))
        categories = self.config_data.get("categories") or DEFAULT_CATEGORIES
        for category in categories:
            label = str(category.get("label", "Categoria"))
            description = str(category.get("description", "Toque para carregar publicações"))
            button = ActionButton(
                text=f"{label}\n{description}     ›",
                fill=SURFACE,
                text_color=INK,
                font_size=sp(15),
                halign="left",
                padding=(dp(16), dp(10)),
                height=dp(78),
            )
            button.bind(width=lambda instance, width: setattr(instance, "text_size", (width - dp(24), None)))
            button.bind(on_release=partial(self.open_category, category))
            grid.add_widget(button)
        scroll.add_widget(grid)
        self.root_box.add_widget(scroll)

        logout = ActionButton(text="Sair da conta", fill=(0, 0, 0, 0), text_color=MUTED, height=dp(42), font_size=sp(12))
        logout.bind(on_release=self.logout)
        self.root_box.add_widget(logout)

    def set_status(self, message, success=False):
        self.status_label.text = message
        self.status_label.color = TEAL if success else MUTED

    def open_settings(self, *_):
        screen = self.manager.get_screen("settings")
        screen.reload(self.config_data)
        self.manager.current = "settings"

    def open_category(self, category, *_):
        screen = self.manager.get_screen("items")
        code = str(category.get("code", ""))
        screen.load_category(self.config_data, category, cached=self.cache.get(code))
        self.manager.current = "items"

    def refresh(self, *_):
        categories = self.config_data.get("categories") or DEFAULT_CATEGORIES
        if not categories:
            return
        categories = [dict(category) for category in categories]
        self.refresh_button.disabled = True
        self.refresh_button.text = "Sincronizando…"
        self.set_status(f"Sincronizando {len(categories)} categoria(s) com a API…")

        def worker():
            try:
                refreshed = {}
                for category in categories:
                    code = str(category.get("code", ""))
                    refreshed[code] = self.app.api_client.fetch_folder_items(
                        self.config_data.get("matricula", ""), self.config_data.get("token", ""), code
                    )
                Clock.schedule_once(partial(self._refresh_done, refreshed), 0)
            except PortalApiError as exc:
                Clock.schedule_once(partial(self._refresh_error, str(exc)), 0)
            except Exception:
                Clock.schedule_once(partial(self._refresh_error, "A sincronização falhou. Tente novamente."), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_done(self, refreshed, _dt):
        self.cache.update(refreshed)
        self.refresh_button.disabled = False
        self.refresh_button.text = "Sincronizar"
        total = sum(len(items) for items in refreshed.values())
        self.set_status(f"{len(refreshed)} categorias • {total} item(ns) • {datetime.now().strftime('%H:%M')}", success=True)

    def _refresh_error(self, message, _dt):
        self.refresh_button.disabled = False
        self.refresh_button.text = "Tentar novamente"
        self.set_status(message)

    def logout(self, *_):
        self.config_data["matricula"] = ""
        self.config_data["token"] = ""
        save_config(self.config_data)
        login = self.manager.get_screen("login")
        login.config_data = self.config_data
        login.matricula_input.text = ""
        login.token_input.text = ""
        login.status_label.text = ""
        self.manager.current = "login"


class SettingsScreen(AppScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical", padding=(dp(18), dp(14)), spacing=dp(12))
        self.add_widget(self.root_box)
        self.category_rows = []

    def reload(self, config_data):
        self.config_data = dict(config_data)
        self.categories = [dict(category) for category in (config_data.get("categories") or DEFAULT_CATEGORIES)]
        self.build()

    def build(self):
        self.root_box.clear_widgets()
        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        back = ActionButton(text="‹", fill=PALE_BLUE, text_color=BRAND, size_hint_x=None, width=dp(48), height=dp(42), font_size=sp(23))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        header.add_widget(back)
        header.add_widget(make_label("Configurações", size=20, bold=True, height=44))
        self.root_box.add_widget(header)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=(0, dp(4), 0, dp(12)))
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(make_label("Acesso à escola", size=15, bold=True, height=28))
        self.matricula_input = make_input(self.config_data.get("matricula", ""), "Matrícula", input_filter="int")
        form.add_widget(self.matricula_input)
        self.token_input = make_input(self.config_data.get("token", ""), "Token da API", password=True)
        form.add_widget(self.token_input)
        form.add_widget(make_label("O token é usado apenas neste aparelho. Se expirou, solicite um novo à escola.", size=11, color=MUTED, height=40))
        form.add_widget(make_label("Categorias", size=15, bold=True, height=30))
        form.add_widget(make_label("Nome e código PastaCodigo configurado pela escola.", size=11, color=MUTED, height=28))
        self.category_rows = []
        for category in self.categories:
            form.add_widget(self._category_row(category))
        add_button = ActionButton(text="+ Adicionar categoria", fill=PALE_BLUE, text_color=BRAND, height=46, font_size=sp(12))
        add_button.bind(on_release=self.add_category)
        form.add_widget(add_button)
        scroll.add_widget(form)
        self.root_box.add_widget(scroll)

        self.status_label = make_label("", size=12, color=MUTED, height=34)
        self.root_box.add_widget(self.status_label)
        actions = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        cancel = ActionButton(text="Cancelar", fill=SURFACE, text_color=MUTED, height=dp(48))
        cancel.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        self.save_button = ActionButton(text="Testar e salvar", fill=BRAND, height=dp(48))
        self.save_button.bind(on_release=self.test_and_save)
        actions.add_widget(cancel)
        actions.add_widget(self.save_button)
        self.root_box.add_widget(actions)

    def _category_row(self, category):
        row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        name = make_input(category.get("label", ""), "Nome", height=50)
        code = make_input(category.get("code", ""), "Código", height=50, input_filter="int")
        code.size_hint_x = None
        code.width = dp(82)
        remove = ActionButton(text="×", fill=PALE_RED, text_color=(0.72, 0.22, 0.27, 1), size_hint_x=None, width=dp(44), height=dp(48), font_size=sp(20))
        remove.bind(on_release=partial(self.remove_category, category))
        row.add_widget(name)
        row.add_widget(code)
        row.add_widget(remove)
        self.category_rows.append((category, name, code))
        return row

    def add_category(self, *_):
        self.categories.append({"id": f"custom-{len(self.categories) + 1}", "label": "Nova categoria", "code": ""})
        self.build()

    def remove_category(self, category, *_):
        self.categories = [item for item in self.categories if item is not category]
        if not self.categories:
            self.categories = [dict(item) for item in DEFAULT_CATEGORIES]
        self.build()

    def _collect_config(self):
        matricula = self.matricula_input.text.strip()
        token = self.token_input.text.strip()
        if not matricula.isdigit():
            raise PortalApiError("A matrícula deve conter apenas números.")
        if not token:
            raise AuthenticationError("Informe o token de acesso da escola.")
        categories = []
        for original, name_input, code_input in self.category_rows:
            label = name_input.text.strip()
            code = code_input.text.strip()
            if not label or not code.isdigit():
                raise PortalApiError("Cada categoria precisa de um nome e um código numérico.")
            categories.append({
                "id": original.get("id", "custom"),
                "label": label,
                "code": code,
                "description": original.get("description", "Publicações e documentos"),
            })
        if not categories:
            raise PortalApiError("Adicione pelo menos uma categoria.")
        config = dict(self.config_data)
        config.update({"matricula": matricula, "token": token, "categories": categories})
        return config

    def test_and_save(self, *_):
        try:
            config = self._collect_config()
        except PortalApiError as exc:
            self.status_label.text = str(exc)
            self.status_label.color = (0.73, 0.20, 0.25, 1)
            return
        self.save_button.disabled = True
        self.save_button.text = "Testando conexão…"
        self.status_label.text = "Validando matrícula, token e categoria…"
        self.status_label.color = MUTED

        def worker():
            try:
                code = config["categories"][0]["code"]
                items = self.app.api_client.fetch_folder_items(config["matricula"], config["token"], code)
                save_config(config)
                Clock.schedule_once(partial(self._saved, config, code, items), 0)
            except PortalApiError as exc:
                Clock.schedule_once(partial(self._save_failed, str(exc)), 0)
            except Exception:
                Clock.schedule_once(partial(self._save_failed, "Não foi possível salvar. Tente novamente."), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _saved(self, config, code, items, _dt):
        self.save_button.disabled = False
        self.save_button.text = "Testar e salvar"
        home = self.manager.get_screen("home")
        home.reload(config)
        home.cache[code] = items
        home.set_status("Configuração salva e sincronizada", success=True)
        self.manager.current = "home"

    def _save_failed(self, message, _dt):
        self.save_button.disabled = False
        self.save_button.text = "Tentar novamente"
        self.status_label.text = message
        self.status_label.color = (0.73, 0.20, 0.25, 1)


class ItemsScreen(AppScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical", padding=(dp(18), dp(14)), spacing=dp(10))
        self.add_widget(self.root_box)

    def load_category(self, config_data, category, cached=None):
        self.config_data = dict(config_data)
        self.category = dict(category)
        self.root_box.clear_widgets()

        header = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        back = ActionButton(text="‹", fill=PALE_BLUE, text_color=BRAND, size_hint_x=None, width=dp(48), height=dp(42), font_size=sp(23))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        header.add_widget(back)
        header.add_widget(make_label(self.category.get("label", "Publicações"), size=18, bold=True, height=46))
        self.root_box.add_widget(header)

        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.status_label = make_label("", size=12, color=MUTED, height=38)
        row.add_widget(self.status_label)
        self.refresh_button = ActionButton(text="Atualizar", fill=SURFACE, text_color=BRAND, size_hint_x=None, width=dp(104), height=dp(40), font_size=sp(12))
        self.refresh_button.bind(on_release=self.sync)
        row.add_widget(self.refresh_button)
        self.root_box.add_widget(row)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(3))
        self.root_box.add_widget(self.progress)
        self.body = BoxLayout(orientation="vertical")
        self.root_box.add_widget(self.body)
        if cached is not None:
            self.render_items(cached)
            self.set_status(f"{len(cached)} item(ns) • atualizado agora", success=True)
        else:
            self.sync()

    def sync(self, *_):
        self.refresh_button.disabled = True
        self.refresh_button.text = "Atualizando…"
        self.status_label.text = "Buscando publicações na API da escola…"
        self.status_label.color = MUTED
        self.progress.value = 45
        self.body.clear_widgets()
        self.body.add_widget(make_label("Carregando seus documentos…", size=14, color=MUTED, height=54, halign="center"))
        config = self.config_data
        category = self.category

        def worker():
            try:
                items = self.app.api_client.fetch_folder_items(
                    config.get("matricula", ""), config.get("token", ""), category.get("code", "")
                )
                Clock.schedule_once(partial(self._loaded, items), 0)
            except PortalApiError as exc:
                Clock.schedule_once(partial(self._load_failed, str(exc)), 0)
            except Exception:
                Clock.schedule_once(partial(self._load_failed, "A consulta falhou. Verifique a conexão e tente de novo."), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _loaded(self, items, _dt):
        self.refresh_button.disabled = False
        self.refresh_button.text = "Atualizar"
        self.progress.value = 100
        self.render_items(items)
        self.set_status(f"{len(items)} item(ns) • atualizado às {datetime.now().strftime('%H:%M')}", success=True)

    def _load_failed(self, message, _dt):
        self.refresh_button.disabled = False
        self.refresh_button.text = "Tentar novamente"
        self.progress.value = 0
        self.status_label.text = message
        self.status_label.color = (0.73, 0.20, 0.25, 1)
        self.body.clear_widgets()
        self.body.add_widget(make_label("Não foi possível carregar esta categoria.", size=14, color=MUTED, height=76, halign="center"))

    def set_status(self, message, success=False):
        self.status_label.text = message
        self.status_label.color = TEAL if success else MUTED

    def render_items(self, items):
        self.body.clear_widgets()
        if not items:
            empty = Panel(orientation="vertical", padding=dp(22), spacing=dp(8))
            empty.add_widget(make_label("Tudo em dia", size=19, bold=True, halign="center", height=34))
            empty.add_widget(make_label("Ainda não há publicações nesta categoria.\nPuxe para atualizar ou tente novamente mais tarde.", size=13, color=MUTED, halign="center", height=68))
            self.body.add_widget(empty)
            return

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        listing = GridLayout(cols=1, spacing=dp(9), size_hint_y=None, padding=(0, dp(4), 0, dp(10)))
        listing.bind(minimum_height=listing.setter("height"))
        for item in items:
            listing.add_widget(self._item_card(item))
        scroll.add_widget(listing)
        self.body.add_widget(scroll)

    def _item_card(self, item):
        card = Panel(orientation="horizontal", padding=(dp(12), dp(10)), spacing=dp(8), size_hint_y=None, height=dp(86), fill=SURFACE)
        icon = Panel(fill=PALE_BLUE, radius=14, size_hint=(None, None), size=(dp(46), dp(46)))
        icon.add_widget(Label(text="PDF", font_size=sp(10), bold=True, color=BRAND))
        card.add_widget(icon)
        info = BoxLayout(orientation="vertical", spacing=dp(3))
        title = str(item.get("tit") or item.get("titulo") or "Documento")
        info.add_widget(make_label(title, size=13, bold=True, height=38))
        info.add_widget(make_label("Publicação da escola", size=11, color=MUTED, height=23))
        card.add_widget(info)
        action = ActionButton(text="Abrir", fill=BRAND, size_hint_x=None, width=dp(72), height=dp(42), font_size=sp(12))
        action.bind(on_release=partial(self.download_item, item, action))
        card.add_widget(action)
        return card

    def download_item(self, item, button, *_):
        url = item.get("url") or item.get("link")
        if not url:
            show_message("Documento indisponível", "A API não retornou um endereço para este documento.")
            return
        title = str(item.get("tit") or item.get("titulo") or "documento")
        button.disabled = True
        button.text = "…"
        token = self.config_data.get("token", "")

        def worker():
            try:
                content, content_type = self.app.api_client.download_item_bytes(url, token)
                filename = safe_filename(title) + file_extension(content_type)
                path = os.path.join(DOWNLOAD_DIR, filename)
                with open(path, "wb") as file:
                    file.write(content)
                Clock.schedule_once(partial(self._download_done, button, path, content_type), 0)
            except PortalApiError as exc:
                Clock.schedule_once(partial(self._download_failed, button, str(exc)), 0)
            except OSError:
                Clock.schedule_once(partial(self._download_failed, button, "Não foi possível salvar o arquivo neste aparelho."), 0)
            except Exception:
                Clock.schedule_once(partial(self._download_failed, button, "Falha ao baixar o documento. Tente novamente."), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _download_done(self, button, path, content_type, _dt):
        button.disabled = False
        button.text = "Abrir"
        if platform == "android":
            try:
                open_android_file(path, content_type)
                return
            except Exception:
                show_message("Arquivo baixado", "O download foi concluído, mas o Android não encontrou um app para abrir este documento.")
                return
        show_message("Download concluído", f"Arquivo salvo em:\n{path}")

    def _download_failed(self, button, message, _dt):
        button.disabled = False
        button.text = "Abrir"
        show_message("Não foi possível abrir", message)


def show_message(title, message):
    box = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
    text = make_label(message, size=14, color=INK, height=100, halign="center")
    box.add_widget(text)
    close = ActionButton(text="Entendi", fill=BRAND, height=dp(46))
    box.add_widget(close)
    popup = Popup(title=title, content=box, size_hint=(0.88, None), height=dp(230), auto_dismiss=False)
    close.bind(on_release=popup.dismiss)
    popup.open()


class SuriPortalApp(App):
    def build(self):
        self.title = "Suri Portal do Aluno"
        self.api_client = PortalApi()
        Window.clearcolor = BG
        manager = ScreenManager(transition=FadeTransition(duration=0.12))
        manager.add_widget(LoginScreen(name="login"))
        manager.add_widget(HomeScreen(name="home"))
        manager.add_widget(SettingsScreen(name="settings"))
        manager.add_widget(ItemsScreen(name="items"))

        config = load_config()
        if config.get("matricula") and config.get("token"):
            manager.get_screen("home").reload(config)
            manager.current = "home"
        else:
            manager.current = "login"
        return manager


if __name__ == "__main__":
    SuriPortalApp().run()
