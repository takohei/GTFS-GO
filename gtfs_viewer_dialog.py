# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GTFSViewerDockWidget
                                 A QGIS plugin
 The plugin to show routes and stops from GTFS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-10-29
        git sha              : $Format:%H$
        copyright            : (C) 2020 by Kanahiro Iguchi
        email                : kanahiro.iguchi@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from qgis.PyQt import QtGui, QtWidgets, uic

from .gtfs_viewer_datalist import DATALIST
from .gtfs_viewer_loader import GTFSViewerLoader


class GTFSViewerDialog(QtWidgets.QDialog):

    def __init__(self):
        """Constructor."""
        super().__init__()
        self.ui = uic.loadUi(os.path.join(os.path.dirname(
            __file__), 'gtfs_viewer_dialog_base.ui'), self)

        self.init_gui()

    def init_gui(self):
        self.ui.comboBox.addItem('---読み込むデータを選択---', None)
        for data in DATALIST:
            self.ui.comboBox.addItem(
                f'[{data["pref"]}] {data["name"]}', data['url'])
        self.ui.comboBox.addItem('zipファイルから読み込み', None)
        self.ui.comboBox.currentIndexChanged.connect(self.refresh)
        self.ui.mQgsFileWidget.fileChanged.connect(self.refresh)
        self.refresh()

        self.ui.pushButton.clicked.connect(self.execution)

    def execution(self):
        loader = GTFSViewerLoader(self.get_source())
        loader.show()

    def get_source(self):
        if self.ui.comboBox.currentData():
            return self.ui.comboBox.currentData()
        elif self.ui.comboBox.currentData() is None and self.ui.mQgsFileWidget.filePath():
            return self.ui.mQgsFileWidget.filePath()
        else:
            return None

    def refresh(self):
        self.ui.mQgsFileWidget.setEnabled(
            self.ui.comboBox.currentText() == 'zipファイルから読み込み')
        self.ui.pushButton.setEnabled(self.get_source() is not None)
