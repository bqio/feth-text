import csv
import ctypes
import re
import os
import pathlib

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QFileDialog,
    QLineEdit,
    QLabel,
    QDialog,
    QTextEdit,
    QFormLayout,
    QDialogButtonBox,
    QShortcut,
    QAction,
    QComboBox,
    QListWidget,
    QMessageBox,
)

from PyQt5.QtGui import (
    QKeySequence,
    QIcon,
    QSyntaxHighlighter,
    QTextCharFormat,
    QColor,
    QFont,
)

from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant, QThread, pyqtSignal, QRegExp

MY_APP_ID = "emblem_team.gui.fe3h.1"

HEADERS = ["Index", "Type", "Source", "Translate"]
RAW_HEADERS = ["file_index", "file_type", "source_language", "destination_language"]


def get_glossary() -> list[tuple[str, str]]:
    glossary: list[tuple[str, str]] = []
    glossary_pattern = re.compile(r"- (.*?) - \*{0,2}(.*?)\*{0,2}$")
    with open("glossary.md", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = glossary_pattern.match(line)
            if match:
                en_term, ru_term = match.groups()
                glossary.append((en_term, ru_term))
    return glossary


class GlossaryHighlighter(QSyntaxHighlighter):
    def __init__(
        self, document, glossary: list[tuple[str, str]], on_found_terms_changed
    ):
        super().__init__(document)
        self.glossary = glossary
        self.on_found_terms_changed = on_found_terms_changed
        self.found_terms = set()

        self.fmt = QTextCharFormat()
        self.fmt.setForeground(QColor("darkred"))
        self.fmt.setFontWeight(QFont.Bold)

        self.rules = []
        for name, _ in glossary:
            escaped = re.escape(name)
            pattern = QRegExp(escaped, re.IGNORECASE)
            self.rules.append((name, pattern))

    def highlightBlock(self, text):
        for term, pattern in self.rules:
            index = pattern.indexIn(text)
            while index >= 0:
                length = pattern.matchedLength()
                self.setFormat(index, length, self.fmt)
                self.found_terms.add(term)
                index = pattern.indexIn(text, index + length)

    def rehighlight(self):
        self.found_terms.clear()
        super().rehighlight()
        self.on_found_terms_changed(sorted(self.found_terms))


class CSVLoaderThread(QThread):
    loaded = pyqtSignal(list, list)  # headers, rows

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        with open(self.file_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            data = list(reader)
        rows = data[1:]
        self.loaded.emit(HEADERS, rows)


class CSVTableModel(QAbstractTableModel):
    def __init__(self, headers, data):
        super().__init__()
        self.headers = headers
        self.original_data = data
        self.filtered_data = data

    def rowCount(self, parent=None):
        return len(self.filtered_data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole:
            return self.filtered_data[index.row()][index.column()]
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.headers[section]
            else:
                return str(section + 1)
        return QVariant()

    def get_row(self, row):
        return self.filtered_data[row]

    def set_translation(self, row, new_value):
        index_in_original = self.original_data.index(self.filtered_data[row])
        self.original_data[index_in_original][3] = new_value
        self.filtered_data[row][3] = new_value
        self.dataChanged.emit(self.index(row, 3), self.index(row, 3))

    def apply_filter(
        self, text_filter="", file_type_filter="", show_untranslated=False
    ):
        text_filter = text_filter.lower()
        file_type_filter = file_type_filter.lower()

        def match(row):
            file_type = row[1].lower()
            source = row[2].lower()
            dest = row[3].lower()
            untranslated = dest == ""

            return (
                (not show_untranslated or untranslated)
                and (text_filter in source or text_filter in dest)
                and (file_type_filter in file_type)
            )

        self.beginResetModel()
        self.filtered_data = [row for row in self.original_data if match(row)]
        self.endResetModel()

    def stats(self):
        total = len(self.original_data)
        untranslated = sum(1 for r in self.original_data if r[3] == "")
        percent = int((total - untranslated) / total * 100) if total > 0 else 0
        return total, untranslated, percent


class EditDialog(QDialog):
    def __init__(self, original_text, translated_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit cell")
        self.resize(1200, 400)

        self.glossary = get_glossary()

        self.original_text = QTextEdit(self)
        self.original_light = GlossaryHighlighter(
            self.original_text.document(), self.glossary, self.update_list
        )
        self.original_text.setPlainText(original_text)
        self.original_text.setReadOnly(True)

        self.translated_text = QTextEdit(self)
        self.translated_light = GlossaryHighlighter(
            self.translated_text.document(), self.glossary, self.update_list
        )
        self.translated_text.setPlainText(translated_text)

        self.clone_button = QPushButton("Clone")
        self.clone_button.clicked.connect(self.clone_text)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_text)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.addWidget(self.clone_button)
        self.btn_layout.addWidget(self.clear_button)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        # flayout = QFormLayout()
        # flayout.addRow("Source:", self.original_text)
        # flayout.addRow("Translate:", self.translated_text)

        layout = QVBoxLayout()
        layout.addWidget(self.original_text)
        layout.addWidget(self.translated_text)
        # layout.addLayout(flayout)
        layout.addLayout(self.btn_layout)
        layout.addWidget(self.buttons)

        self.glossary_layout = QVBoxLayout()
        self.glossary_table = QListWidget()
        self.glossary_table.setFixedWidth(400)
        self.glossary_table.itemDoubleClicked.connect(self.on_glossary_clicked)
        self.glossary_layout.addWidget(self.glossary_table)

        def_lay = QHBoxLayout()
        def_lay.addLayout(layout)
        def_lay.addLayout(self.glossary_layout)
        self.setLayout(def_lay)

        self.original_light.rehighlight()

    def on_glossary_clicked(self, item):
        text = item.text()
        _, ru = text.split(" = ")
        self.translated_text.setPlainText(
            self.translated_text.toPlainText() + f"{ru.strip()}"
        )

    def clone_text(self):
        self.translated_text.setPlainText(self.original_text.toPlainText())

    def clear_text(self):
        self.translated_text.setPlainText("")

    def get_translated_text(self):
        return self.translated_text.toPlainText()

    def update_list(self, terms: list[str]):
        self.glossary_table.clear()
        for name in terms:
            for nname in self.glossary:
                if nname[0] == name:
                    value = nname[1]
                    item = f"{name} = {value}"
                    self.glossary_table.addItem(item)
                    break


class CSVEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.window_icon = QIcon("icon.png")
        self.model = None
        self.filter_data = []
        self.can_save = False
        self.current_file = None
        self.config_dir = pathlib.Path(os.getenv("APPDATA")) / "Bundle Editor"
        self.config_dir.mkdir(exist_ok=True)
        self.recent_file_path = self.config_dir / "recent"

        self.setWindowTitle("Bundle Editor")
        self.setWindowIcon(self.window_icon)
        self.resize(1280, 600)

        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText("Search...")
        self.search_line_edit.textChanged.connect(self.apply_filter)
        self.search_line_edit.setEnabled(False)

        self.file_type_filter = QComboBox()
        self.file_type_filter.setFixedWidth(100)
        self.file_type_filter.currentTextChanged.connect(self.apply_filter)
        self.file_type_filter.setEnabled(False)

        self.show_untranslated_checkbox = QCheckBox("Show untranslated")
        self.show_untranslated_checkbox.stateChanged.connect(self.apply_filter)
        self.show_untranslated_checkbox.setEnabled(False)

        self.stats_label = QLabel("No data")

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.load_csv)

        file_menu.addAction(open_action)

        self.save_action = QAction("Save", self)
        self.save_action.setEnabled(False)
        self.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_action.triggered.connect(self.save_csv)

        file_menu.addAction(self.save_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)

        file_menu.addAction(exit_action)

        filters = QHBoxLayout()
        filters.addWidget(self.search_line_edit)
        filters.addWidget(self.file_type_filter)

        stats = QHBoxLayout()
        stats.addWidget(self.show_untranslated_checkbox)
        stats.addStretch()
        stats.addWidget(self.stats_label)

        top_layout = QVBoxLayout()
        top_layout.addLayout(filters)

        self.table = QTableView()
        self.table.doubleClicked.connect(self.edit_translation)

        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.focus_input)

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self.table)
        layout.addLayout(stats)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        if self.recent_file_path.exists():
            recent = self.recent_file_path.read_bytes().decode("utf-8")
            if pathlib.Path(recent).exists():
                self.setWindowTitle("Bundle Editor - opening recent bundle...")
                self.current_file = recent
                self.thread = CSVLoaderThread(recent)
                self.thread.loaded.connect(self.on_csv_loaded)
                self.thread.start()

    def focus_input(self):
        self.search_line_edit.setFocus()

    def load_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV", "", "CSV files (*.csv)"
        )
        if not file_path:
            return
        if self.can_save:
            reply = QMessageBox.question(
                self,
                "Save file",
                "Save current opened file?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )

            if reply == QMessageBox.Yes:
                self.save_csv()
        self.current_file = file_path
        self.thread = CSVLoaderThread(file_path)
        self.thread.loaded.connect(self.on_csv_loaded)
        self.thread.start()

    def on_csv_loaded(self, headers, rows):
        self.save_action.setEnabled(True)
        self.setWindowTitle(f"Bundle Editor - {self.current_file}")
        self.show_untranslated_checkbox.setEnabled(True)
        self.search_line_edit.setEnabled(True)
        self.file_type_filter.clear()
        self.filter_data = self.calc_filter_data(rows)
        self.file_type_filter.addItems(self.filter_data)
        self.file_type_filter.setEnabled(True)
        self.file_type_filter.setCurrentIndex(0)
        self.model = CSVTableModel(headers, rows)
        self.table.setModel(self.model)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 600)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.apply_filter()
        self.can_save = False
        self.recent_file_path.write_bytes(self.current_file.encode("utf-8"))

    def calc_filter_data(self, rows):
        unique = ["ALL"]
        for row in rows:
            if row[1] not in unique:
                unique.append(row[1])
        return unique

    def apply_filter(self):
        if not self.model:
            return
        filter_type = self.file_type_filter.currentText()
        if filter_type == "ALL":
            filter_type = ""
        self.model.apply_filter(
            self.search_line_edit.text(),
            filter_type,
            self.show_untranslated_checkbox.isChecked(),
        )
        self.update_stats()

    def update_stats(self):
        if not self.model:
            return
        total, untranslated, percent = self.model.stats()
        self.stats_label.setText(
            f"Stats: {total} cells, {untranslated} untranslated ({percent}% translated)"
        )

    def edit_translation(self, index):
        if not self.model:
            return
        row = index.row()
        data = self.model.get_row(row)
        source_text = data[2]
        dest_text = data[3]
        dialog = EditDialog(source_text, dest_text, self)
        if dialog.exec_() == QDialog.Accepted:
            new_translation = dialog.get_translated_text()
            self.model.set_translation(row, new_translation)
            self.can_save = True
            self.setWindowTitle(f"Bundle Editor - {self.current_file} *")
            self.update_stats()

    def save_csv(self):
        self.table.setEnabled(False)
        self.save_action.setEnabled(False)
        if not self.model or not self.current_file:
            return
        with open(self.current_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(RAW_HEADERS)
            for row in self.model.original_data:
                writer.writerow(row)
        self.table.setEnabled(True)
        self.save_action.setEnabled(True)
        self.can_save = False
        self.setWindowTitle(f"Bundle Editor - {self.current_file}")

    def closeEvent(self, event):
        if self.can_save:
            reply = QMessageBox.question(
                self,
                "Exit",
                "Exit and save file?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Abort,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.save_csv()
                event.accept()
            elif reply == QMessageBox.Abort:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(MY_APP_ID)
    app = QApplication([])
    window = CSVEditor()
    window.show()
    app.exec_()
