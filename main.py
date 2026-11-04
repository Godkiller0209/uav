import sys

from PyQt5.QtWidgets import QApplication

from GUI.main_window import GPSMap



if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = GPSMap()

    window.show()

    sys.exit(app.exec_())
