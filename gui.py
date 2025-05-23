import csv
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
    QHeaderView,
)
from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant, QThread, pyqtSignal


class CSVLoaderThread(QThread):
    loaded = pyqtSignal(list, list)  # headers, rows

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        with open(self.file_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            data = list(reader)
        headers = data[0]
        rows = data[1:]
        self.loaded.emit(headers, rows)


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
        self.setWindowTitle("Редактирование строки")
        self.resize(800, 400)

        self.original_text = QTextEdit(self)
        self.original_text.setPlainText(original_text)
        self.original_text.setReadOnly(True)

        self.translated_text = QTextEdit(self)
        self.translated_text.setPlainText(translated_text)

        self.clone_button = QPushButton("Копировать в перевод")
        self.clone_button.clicked.connect(self.clone_text)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QFormLayout()
        layout.addRow("Исходный текст:", self.original_text)
        layout.addRow("Перевод:", self.translated_text)
        layout.addWidget(self.clone_button)
        layout.addWidget(self.buttons)
        self.setLayout(layout)

    def clone_text(self):
        self.translated_text.setPlainText(self.original_text.toPlainText())

    def get_translated_text(self):
        return self.translated_text.toPlainText()


class CSVEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bundle Editor v2")
        self.resize(1280, 600)
        self.model = None

        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText("Поиск по тексту")
        self.search_line_edit.textChanged.connect(self.apply_filter)

        self.file_type_filter = QLineEdit()
        self.file_type_filter.setPlaceholderText("Фильтр по file_type")
        self.file_type_filter.textChanged.connect(self.apply_filter)

        self.show_untranslated_checkbox = QCheckBox("Показать только непереведенные")
        self.show_untranslated_checkbox.stateChanged.connect(self.apply_filter)

        self.stats_label = QLabel("Нет данных")

        load_button = QPushButton("Открыть CSV")
        load_button.clicked.connect(self.load_csv)

        save_button = QPushButton("Сохранить CSV")
        save_button.clicked.connect(self.save_csv)

        buttons = QHBoxLayout()
        buttons.addWidget(load_button)
        buttons.addWidget(save_button)

        top_layout = QVBoxLayout()
        top_layout.addWidget(self.search_line_edit)
        top_layout.addWidget(self.file_type_filter)
        top_layout.addWidget(self.show_untranslated_checkbox)
        top_layout.addLayout(buttons)
        top_layout.addWidget(self.stats_label)

        self.table = QTableView()
        self.table.horizontalHeader().setStretchLastSection(True)
        # self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_translation)
        self.table.setWordWrap(True)
        self.table.resizeRowsToContents()

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self.table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.current_file = None

    def load_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Открыть CSV", "", "CSV файлы (*.csv)"
        )
        if not file_path:
            return
        self.current_file = file_path
        self.thread = CSVLoaderThread(file_path)
        self.thread.loaded.connect(self.on_csv_loaded)
        self.thread.start()

    def on_csv_loaded(self, headers, rows):
        self.model = CSVTableModel(headers, rows)
        self.table.setModel(self.model)
        self.apply_filter()

    def apply_filter(self):
        if not self.model:
            return
        self.model.apply_filter(
            self.search_line_edit.text(),
            self.file_type_filter.text(),
            self.show_untranslated_checkbox.isChecked(),
        )
        total, untranslated, percent = self.model.stats()
        self.stats_label.setText(
            f"Статистика: {total} строк, {untranslated} не переведено ({percent}% переведено)"
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
            # self.apply_filter()

    def save_csv(self):
        if not self.model or not self.current_file:
            return
        with open(self.current_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.model.headers)
            for row in self.model.original_data:
                writer.writerow(row)


if __name__ == "__main__":
    app = QApplication([])
    window = CSVEditor()
    window.show()
    app.exec_()
