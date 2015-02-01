#!/usr/bin/python
from __future__ import division

import cgi
import os
import signal
import sys

from time import sleep

from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, GLib, Keybinder, Gio

max_visible_rows = 5


class Index(object):

    def __init__(self, indexers):
        self.indexers = indexers

        # TODO: Use more suitable data structure :)
        self.items = []

        self.index()

    def search(self, input):
        def match(item):
            iws = input.split()
            ws = item["words"]

            return all((any(w.lower().startswith(iw.lower()) for w in ws)) for iw in iws)

        return filter(match, self.items)

    def index(self):
        for indexer in self.indexers:
            self.items.extend(indexer.provide())


class DirectoryIndexer(object):

    def provide(self):

        user_dir_names = [
            GLib.USER_DIRECTORY_DESKTOP,
            GLib.USER_DIRECTORY_DOCUMENTS,
            GLib.USER_DIRECTORY_DOWNLOAD,
            GLib.USER_DIRECTORY_MUSIC,
            GLib.USER_DIRECTORY_PICTURES,
            GLib.USER_DIRECTORY_PUBLIC_SHARE,
            GLib.USER_DIRECTORY_TEMPLATES,
            GLib.USER_DIRECTORY_VIDEOS,
        ]

        user_dirs = map(GLib.get_user_special_dir, user_dir_names)

        icon_theme = Gtk.IconTheme.get_default()
        icon = Gtk.IconTheme.load_icon(icon_theme, "folder", 44, 0)

        def build_item(user_dir):
            return {
                "indexer": self,

                "name": GLib.path_get_basename(user_dir),
                "description": user_dir,
                "icon": icon,

                "words": [GLib.path_get_basename(user_dir)],
            }

        return map(build_item, user_dirs)

    def launch(self, item):
        item_uri = Gio.File.new_for_path(item["description"]).get_uri()

        def func():
            import subprocess
            subprocess.Popen(["xdg-open", item_uri])

        launch(func)

    def launchable(self, item):
        return os.path.isdir(item["description"])


class ApplicationIndexer(object):
    def provide(self):
        from fnmatch import fnmatch
        from xdg.DesktopEntry import DesktopEntry

        items = []

        for root, dirs, files in os.walk("/usr/share/applications/"):
            for filename in files:
                if fnmatch(filename, "*.desktop"):
                    app_entry = DesktopEntry(os.path.join(root, filename))

                    icon_theme = Gtk.IconTheme.get_default()

                    try:
                        unscaled_icon = Gtk.IconTheme.load_icon(icon_theme, app_entry.getIcon(), 44, 0)
                        icon = unscaled_icon.scale_simple(44, 44, GdkPixbuf.InterpType.BILINEAR)
                    except:
                        icon = Gtk.IconTheme.load_icon(icon_theme, "folder", 44, 0)

                    words = app_entry.getName().split()
                    # words.append(app_entry.getExec())

                    item = {
                        "indexer": self,

                        "name": app_entry.getName(),
                        "description": app_entry.getComment(),
                        "icon": icon,

                        "command": app_entry.getExec(),

                        "words": words,
                    }

                    items.append(item)

        return items

    def launch(self, item):
        codes = ["%f", "%F", "%u", "%U", "%i", "%c", "%k"]

        command = item["command"]

        for code in codes:
            command = command.replace(code, "")

        command = command.strip()

        def func():
            import subprocess
            subprocess.Popen(command.split())

        launch(func)

    def launchable(self, item):
        return item["command"].strip() != ""


class Catapult(object):
    def __init__(self):

        next_accels = map(Gtk.accelerator_parse, [
            "Down", "Tab", "<Ctrl>n"
        ])

        prev_accels = map(Gtk.accelerator_parse, [
            "Up", "<Shift>Tab", "<Shift>ISO_Left_Tab", "<Ctrl>p"
        ])

        self.accels_actions = [
            (next_accels, self.next_choice, "next"),
            (prev_accels, self.prev_choice, "prev")
        ]

        indexers = [
            DirectoryIndexer(),
            ApplicationIndexer(),
        ]

        self.index = Index(indexers)

        self.win = None
        self.tree = None
        self.store = None
        self.entry = None

    def run(self):
        # self.win = Gtk.Window()
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_border_width(1)

        width = 400
        relative_top = 0.25

        self.win.set_size_request(width, -1)

        self.win.move(
            (Gdk.Screen.get_default().width() / 2) - width / 2,
            Gdk.Screen.get_default().height() * relative_top,
        )

        self.win.connect("delete-event", Gtk.main_quit)
        self.win.connect("show", self.handle_show)

        self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        self.win.set_resizable(False)

        self.win.set_decorated(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_homogeneous(False)
        self.win.add(vbox)

        self.entry = Gtk.Entry()
        self.entry.override_font(
            Pango.FontDescription.from_string("Ubuntu 30"))
        # self.entry.set_text("Test")

        self.entry.connect("key-press-event", self.handle_key_press)
        self.entry.connect("changed", self.handle_input)

        vbox.pack_start(self.entry, False, True, 0)

        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, object)

        self.tree = Gtk.TreeView(self.store)

        self.tree.override_font(Pango.FontDescription.from_string("Ubuntu 18"))
        self.tree.set_headers_visible(False)

        self.tree.get_selection().set_mode(Gtk.SelectionMode.BROWSE)

        self.content_renderer = Gtk.CellRendererText()
        content_column = Gtk.TreeViewColumn("Name", self.content_renderer, markup=1)

        self.icon_renderer = Gtk.CellRendererPixbuf()
        icon_column = Gtk.TreeViewColumn("Icon", self.icon_renderer, pixbuf=0)

        self.tree.append_column(icon_column)
        self.tree.append_column(content_column)

        self.tree.set_search_column(-1)

        def handle_selection_changed(selection):
            tree_iter = selection.get_selected()[1]

            if not tree_iter:
                return

            self.tree.scroll_to_cell(self.store.get_path(tree_iter))

        self.tree.get_selection().connect("changed", handle_selection_changed)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.AUTOMATIC)


        self.scrolled.add(self.tree)

        vbox.pack_start(self.scrolled, False, False, 0)

        signal.signal(signal.SIGINT, signal.SIG_DFL)

        accel_group = Gtk.AccelGroup()

        def connect_accel(accel, func):
            accel_group.connect(accel[0], accel[1], 0, func)

        def connection_multiple_accels(accels, func):
            for accel in accels:
                connect_accel(accel, func)

        hide_accel = Gtk.accelerator_parse("Escape")
        connect_accel(hide_accel, self.hide)

        quit_accel = Gtk.accelerator_parse("<Ctrl>q")
        connect_accel(quit_accel, Gtk.main_quit)

        launch_accel = Gtk.accelerator_parse("Return")
        connect_accel(launch_accel, self.launch_choice)

        Keybinder.init()
        Keybinder.bind("<Ctrl>Return", self.show, None)

        self.win.add_accel_group(accel_group)
        self.win.show_all()
        self.scrolled.hide()

        # Gdk.keyboard_grab(self.win.get_window(), False, Gdk.CURRENT_TIME)

        Gtk.main()

    def reset(self, *vargs):
        self.entry.set_text("")
        self.store.clear()

    def hide(self, *vargs):
        self.reset()
        self.win.hide()
        Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)

    def show(self, *vargs):
        self.win.show_all()
        self.scrolled.hide()
        self.win.get_window().focus(Gdk.CURRENT_TIME)

    def handle_show(self, window):
        gdk_win = self.win.get_window()
        grabbed = Gdk.GrabStatus.SUCCESS
        current_time = Gdk.CURRENT_TIME

        while not Gdk.keyboard_grab(gdk_win, False, current_time) == grabbed:
            sleep(0.001)

    def handle_input(self, entry):
        input = self.entry.get_text()

        if input:
            self.store.append()  # WHY?
            self.store.clear()

            items = self.index.search(input)

            for item in items:
                content = cgi.escape(item["name"])

                if item["description"]:
                    content += "\n" + "<span font='12.5'>%s</span>" % (cgi.escape(item["description"],))

                if item["indexer"].launchable(item):
                        self.store.append([item["icon"], content, item])

            if items:
                self.next_choice()
        else:
            self.store.clear()

        # Force redraw so we can get the cell
        while Gtk.events_pending():
            Gtk.main_iteration_do(True)

        n = min(self.store.iter_n_children(None), max_visible_rows)

        if n == 0:
            self.scrolled.hide()
        else:
            self.scrolled.show()

        row_height = max(self.tree.get_column(0).cell_get_size()[3],
                         self.tree.get_column(1).cell_get_size()[3])

        self.scrolled.set_min_content_height(n * row_height)
        self.scrolled.set_min_content_width(0)

    def handle_key_press(self, widget, event, *args):
        for accels_action in self.accels_actions:
            for accel in accels_action[0]:
                modified_state = event.state
                modified_state &= Gdk.ModifierType.MODIFIER_MASK
                modified_state &= ~Gdk.ModifierType.MOD5_MASK

                if accel[0] == event.keyval and accel[1] == modified_state:
                    accels_action[1]()
                    return True

    def launch_choice(self, *vargs):
        selection = self.tree.get_selection()
        model, tree_iter = selection.get_selected()

        if tree_iter:
            item = model[tree_iter][2]
            item["indexer"].launch(item)

        self.hide()

    def next_choice(self):
        selection = self.tree.get_selection()
        model, tree_iter = selection.get_selected()

        if not tree_iter:
            next_iter = model.get_iter_first()
        else:
            next_iter = model.iter_next(tree_iter)

        if next_iter:
            selection.select_iter(next_iter)

    def prev_choice(self):
        selection = self.tree.get_selection()
        model, tree_iter = selection.get_selected()

        if not tree_iter:
            prev_iter = model.get_iter_first()
        else:
            prev_iter = model.iter_previous(tree_iter)

        if prev_iter:
            selection.select_iter(prev_iter)


def launch(func):
    child = os.fork()

    if child > 0:
        return

    grandchild = os.fork()

    if grandchild > 0:
        sys.exit(0)

    os.chdir(os.path.expanduser("~"))
    os.setsid()
    os.umask(0)

    sys.stdout.flush()
    sys.stderr.flush()

    stdin = file(os.devnull, "r")
    stdout = file(os.devnull, "a+")
    stderr = file(os.devnull, "a+", 0)

    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())

    func()

    sys.exit(0)

if __name__ == '__main__':
    catapult = Catapult()
    catapult.run()
