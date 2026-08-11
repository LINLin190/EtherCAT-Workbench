STYLE = """
QMainWindow { background: #F4F6FA; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 13px; color: #1F2937; }
QMenuBar, QMenu { background: #FFFFFF; }
QToolBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #DDE3EC; spacing: 7px; padding: 7px 10px; }
QToolBar#stateToolbar { background: #F8FAFD; padding-top: 6px; padding-bottom: 6px; }
QPushButton, QToolButton { min-height: 30px; padding: 2px 12px; border: 1px solid #C8D0DC; border-radius: 5px; background: #FFFFFF; }
QPushButton:hover, QToolButton:hover { border-color: #3977D4; background: #F1F6FF; }
QPushButton:disabled, QToolButton:disabled { color: #9AA3AF; background: #F4F5F7; border-color: #E2E5E9; }
QPushButton#primaryButton { color: #FFFFFF; background: #1769D2; border-color: #1769D2; font-weight: 600; }
QPushButton#primaryButton:hover { background: #0F5CBD; }
QPushButton#stateButton { min-width: 62px; padding-left: 8px; padding-right: 8px; font-weight: 600; }
QPushButton#stateButton:checked { color: #FFFFFF; background: #1769D2; border-color: #1769D2; }
QPushButton#dangerButton { color: #A82B24; border-color: #E0AAA6; background: #FFF8F7; }
QComboBox { min-height: 30px; padding: 0 8px; border: 1px solid #C8D0DC; border-radius: 5px; background: #FFFFFF; }
QTableWidget { background: #FFFFFF; alternate-background-color: #F7F9FC; gridline-color: #E5E9F0; border: 1px solid #DDE3EC; }
QHeaderView::section { background: #EEF2F7; padding: 7px; border: 0; border-right: 1px solid #D9DEE7; font-weight: 600; }
QLabel#pageTitle { font-size: 19px; font-weight: 650; margin: 8px; }
QLabel#sectionLabel { color: #667085; font-size: 12px; font-weight: 600; }
QLabel#targetLabel { color: #174EA6; font-weight: 650; padding: 4px 10px; background: #EAF2FF; border-radius: 4px; }
QLabel#heroTitle { font-size: 25px; font-weight: 650; color: #172B4D; }
QLabel#heroText { color: #596579; font-size: 14px; line-height: 1.5; }
QLabel#infoBanner { background: #EAF2FF; color: #174EA6; border: 1px solid #BDD3F7; border-radius: 5px; padding: 9px; }
QFrame#contextCard, QFrame#homeCard { background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 7px; }
QLabel#recommendation { color: #344054; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 5px; padding: 10px; }
QTabWidget::pane { border: 1px solid #DDE3EC; background: #FFFFFF; }
QTabBar::tab { background: #E9EDF3; padding: 8px 15px; margin-right: 2px; }
QTabBar::tab:selected { background: #FFFFFF; color: #175FBB; font-weight: 600; border-top: 2px solid #1769D2; }
QDockWidget::title { background: #EEF2F7; padding: 7px; font-weight: 600; }
QStatusBar { background: #FFFFFF; border-top: 1px solid #DDE3EC; }
"""
