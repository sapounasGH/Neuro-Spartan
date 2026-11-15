"""Application-wide Qt stylesheet (QSS) for NeuroSpartan.

Kept separate from any widget so the palette lives in one place.
Object names set in the UI classes map to the #selectors below.
"""

STYLESHEET = """
QMainWindow { background: #f4f7fa; }

QFrame#Sidebar { background: #15181d; }

QLabel#Brand { color: #e7ecf2; font-size: 13px; font-weight: 600; letter-spacing: 2px; }
QLabel#BrandMark { background: #7fc0f5; color: #0f1318; font-size: 11px; font-weight: 700;
                   border-radius: 4px; }
QLabel#Section { color: #7f8a99; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#Count   { color: #7fc0f5; font-size: 11px; font-family: Consolas, monospace; }
QLabel#Status  { color: #8e99a8; font-size: 11px; font-family: Consolas, monospace; }
QLabel#Status[state="error"] { color: #ff8b7a; }

QListWidget#CrewList { background: transparent; border: none; outline: 0;
                       color: #d7dfe9; font-size: 12.5px; }
QListWidget#CrewList::item { padding: 9px 10px; border-left: 3px solid transparent; }
QListWidget#CrewList::item:hover { background: #1e242d; }
QListWidget#CrewList::item:selected { background: #1c3554; border-left: 3px solid #7fc0f5;
                                      color: #ffffff; }

QPushButton { background: transparent; color: #9aa6b6; border: 1px solid #2c333d;
              border-radius: 4px; padding: 6px 8px; font-size: 12px; }
QPushButton:hover { background: #222a34; color: #ffffff; }
QPushButton:pressed { background: #2b333f; }
QPushButton#Toggle { font-family: Consolas, monospace; font-size: 13px;
                     padding: 4px 0px; min-width: 0px; }

QLabel#Title { color: #000000; font-size: 24px; font-weight: 600; }
QLabel#Title span { color: #2f6fdb; }
QLabel#Selected { color: #3c4753; font-size: 13px; }
QLabel#Hint { color: #6b7787; font-size: 12px; }
QFrame#Placeholder { background: #ffffff; border: 1px solid #dde4ec; border-radius: 6px; }

/* tabs above the main panel */
QTabBar#Tabs { background: transparent; qproperty-drawBase: 0; }
QTabBar#Tabs::tab { background: #eaeff5; color: #3c4753; padding: 8px 18px;
                    border: 1px solid #dde4ec; border-bottom: none;
                    margin-right: 3px; font-size: 13px;
                    border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar#Tabs::tab:hover { background: #e0e7ef; }
QTabBar#Tabs::tab:selected { background: #ffffff; color: #2f6fdb; font-weight: 600; }

QLabel#PageTitle { color: #151a21; font-size: 20px; font-weight: 600; }
QLabel#PageName { color: #2f6fdb; font-size: 34px; font-weight: 700; letter-spacing: 1px; }
QComboBox {
    color: #e6e6e6;
    background-color: #2b2b2b;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox:focus {
    border: 1px solid #7aa7d9;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    color: #e6e6e6;
    background-color: #2b2b2b;
    selection-background-color: #3d5a80;
    selection-color: #ffffff;
    border: 1px solid #555;
}
QGroupBox {
    color: #e6e6e6;
    background-color: #242424;
    border: 1px solid #555;
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #9ecbff;
    background-color: #242424;
}
QGroupBox QLabel {
    color: #e6e6e6;
    background: transparent;
}
"""
