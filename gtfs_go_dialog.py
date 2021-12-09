# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GTFSGoDockWidget
                                 A QGIS plugin
 The plugin to show routes and stops from GTFS
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-10-29
        git sha              : $Format:%H$
        copyright            : (C) 2020 by MIERUNE Inc.
        email                : info@mierune.co.jp
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
import time
import json
import urllib
import shutil
import zipfile
import tempfile
import datetime

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from qgis.core import *
from qgis.gui import *
from qgis.PyQt import uic
from qgis.utils import iface

from .gtfs_parser import GTFSParser
from .gtfs_go_renderer import Renderer
from .gtfs_go_labeling import get_labeling_for_stops

from . import repository
from . import constants

from .gtfs_go_settings import (
    FILENAME_RESULT_CSV,
    STOPS_MINIMUM_VISIBLE_SCALE,
)
DATALIST_JSON_PATH = os.path.join(
    os.path.dirname(__file__), 'gtfs_go_datalist.json')
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'GTFSGo')

REPOSITORY_ENUM = {
    "preset": 0,
    "japanDpf": 1
}

WINDOW_HEIGHT = {
    # key is linked to values of REPOSITORY_ENUM
    0: 400,  # preset
    1: 800  # japanDpf
}


class GTFSGoDialog(QDialog):

    def __init__(self, iface):
        """Constructor."""
        super().__init__()
        self.ui = uic.loadUi(os.path.join(os.path.dirname(
            __file__), 'gtfs_go_dialog_base.ui'), self)
        with open(DATALIST_JSON_PATH, encoding='utf-8') as f:
            self.datalist = json.load(f)
        self.iface = iface
        self.combobox_zip_text = self.tr('---Load local ZipFile---')
        self.init_gui()

    def init_gui(self):
        # repository combobox
        self.repositoryCombobox.addItem(
            self.tr('Preset'), REPOSITORY_ENUM['preset'])
        self.repositoryCombobox.addItem(
            self.tr('Japanese GTFS data platform'), REPOSITORY_ENUM['japanDpf'])

        # local repository data select combobox
        self.ui.comboBox.addItem(self.combobox_zip_text, None)
        for data in self.datalist:
            self.ui.comboBox.addItem(self.make_combobox_text(data), data)

        self.init_local_repository_gui()
        self.init_japan_dpf_gui()

        # set refresh event on some ui
        self.ui.repositoryCombobox.currentIndexChanged.connect(self.refresh)
        self.ui.outputDirFileWidget.fileChanged.connect(self.refresh)
        self.ui.unifyCheckBox.stateChanged.connect(self.refresh)
        self.ui.timeFilterCheckBox.stateChanged.connect(self.refresh)

        # change mode by radio button
        self.ui.simpleRadioButton.clicked.connect(self.refresh)
        self.ui.freqRadioButton.clicked.connect(self.refresh)

        # time filter - validate user input
        self.ui.beginTimeLineEdit.editingFinished.connect(
            lambda: self.validate_time_lineedit(self.ui.beginTimeLineEdit))
        self.ui.endTimeLineEdit.editingFinished.connect(
            lambda: self.validate_time_lineedit(self.ui.endTimeLineEdit))

        # set today DateEdit
        now = datetime.datetime.now()
        self.ui.filterByDateDateEdit.setDate(
            QDate(now.year, now.month, now.day))

        self.refresh()

        self.ui.pushButton.clicked.connect(self.execution)

    def init_local_repository_gui(self):
        self.ui.comboBox.currentIndexChanged.connect(self.refresh)
        self.ui.zipFileWidget.fileChanged.connect(self.refresh)

    def init_japan_dpf_gui(self):
        self.japanDpfResultTableView.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        self.japan_dpf_set_table([])
        for idx, header in enumerate(repository.japan_dpf.table.HEADERS):
            if header in repository.japan_dpf.table.HEADERS_TO_HIDE:
                self.japanDpfResultTableView.hideColumn(idx)

        self.japanDpfPrefectureCombobox.addItem(self.tr("any"), None)
        for prefname in constants.JAPAN_PREFS:
            self.japanDpfPrefectureCombobox.addItem(
                prefname, prefname)

        now = datetime.datetime.now()
        self.ui.japanDpfTargetDateEdit.setDate(
            QDate(now.year, now.month, now.day))

        self.japanDpfExtentGroupBox.setMapCanvas(iface.mapCanvas())
        self.japanDpfExtentGroupBox.setOutputCrs(
            QgsCoordinateReferenceSystem("EPSG:4326"))

        self.japanDpfSearchButton.clicked.connect(self.japan_dpf_search)

    def make_combobox_text(self, data):
        """
        parse data to combobox-text
        data-schema: {
            country: str,
            region: str,
            name: str,
            url: str
        }

        Args:
            data ([type]): [description]

        Returns:
            str: combobox-text
        """
        return '[' + data["country"] + ']' + '[' + data["region"] + ']' + data["name"]

    def download_zip(self, url: str) -> str:
        data = urllib.request.urlopen(url).read()
        download_path = os.path.join(TEMP_DIR, str(int(time.time())) + '.zip')
        with open(download_path, mode='wb') as f:
            f.write(data)

        return download_path

    def extract_zip(self, zip_path: str) -> str:
        extracted_dir = os.path.join(TEMP_DIR, 'extract')
        os.makedirs(extracted_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extracted_dir)
        return extracted_dir

    def get_target_feed_infos(self):
        feed_infos = []
        if self.repositoryCombobox.currentData() == REPOSITORY_ENUM['preset']:
            if self.ui.comboBox.currentData():
                feed_infos.append({
                    "path": self.ui.comboBox.currentData().get("url"),
                    "group": self.ui.comboBox.currentData().get("name"),
                    "dir": self.ui.comboBox.currentData().get("name")
                })
            elif self.ui.comboBox.currentData() is None and self.ui.zipFileWidget.filePath():
                feed_infos.append({
                    "path": self.ui.zipFileWidget.filePath(),
                    "group": os.path.basename(self.ui.zipFileWidget.filePath()).split(".")[0],
                    "dir": os.path.basename(self.ui.zipFileWidget.filePath()).split(".")[0]
                })
        elif self.repositoryCombobox.currentData() == REPOSITORY_ENUM['japanDpf']:
            selected_rows = self.japanDpfResultTableView.selectionModel().selectedRows()
            for row in selected_rows:
                row_data = self.get_selected_row_data_in_japan_dpf_table(
                    row.row())
                feed_infos.append({
                    "path": row_data["gtfs_url"],
                    "group": row_data["agency_name"] + "-" + row_data["gtfs_name"],
                    "dir": row_data["agency_id"] + "-" + row_data["gtfs_id"],
                })
        return feed_infos

    def execution(self):
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)

        for feed_info in self.get_target_feed_infos():
            if feed_info["path"].startswith('http'):
                feed_info["path"] = self.download_zip(feed_info["path"])

            extracted_dir = self.extract_zip(feed_info["path"])
            output_dir = os.path.join(self.outputDirFileWidget.filePath(),
                                      feed_info["dir"])
            os.makedirs(output_dir, exist_ok=True)

            if self.ui.simpleRadioButton.isChecked():
                gtfs_parser = GTFSParser(extracted_dir)
                routes_geojson = {
                    'type': 'FeatureCollection',
                    'features': gtfs_parser.read_routes(no_shapes=self.ui.ignoreShapesCheckbox.isChecked())
                }
                stops_geojson = {
                    'type': 'FeatureCollection',
                    'features': gtfs_parser.read_stops(ignore_no_route=self.ui.ignoreNoRouteStopsCheckbox.isChecked())
                }
                route_filename = 'route.geojson'
                stops_filename = 'stops.geojson'
            else:
                gtfs_parser = GTFSParser(
                    extracted_dir,
                    as_frequency=True,
                    as_unify_stops=self.ui.unifyCheckBox.isChecked(),
                    delimiter=self.get_delimiter()
                )

                routes_geojson = {
                    'type': 'FeatureCollection',
                    'features': gtfs_parser.read_route_frequency(yyyymmdd=self.get_yyyymmdd(),
                                                                 begin_time=self.get_time_filter(
                        self.ui.beginTimeLineEdit),
                        end_time=self.get_time_filter(self.ui.endTimeLineEdit))
                }
                stops_geojson = {
                    'type': 'FeatureCollection',
                    'features': gtfs_parser.read_interpolated_stops()
                }

                route_filename = 'frequency.geojson'
                stops_filename = 'frequency_stops.geojson'

                # write stop_id conversion result csv
                with open(os.path.join(output_dir, FILENAME_RESULT_CSV), mode="w", encoding="cp932", errors="ignore")as f:
                    gtfs_parser.dataframes['stops'][[
                        'stop_id', 'stop_name', 'similar_stop_id', 'similar_stop_name']].to_csv(f, index=False)

            with open(os.path.join(output_dir, route_filename), mode='w', encoding='utf-8') as f:
                json.dump(routes_geojson, f, ensure_ascii=False)
            with open(os.path.join(output_dir, stops_filename), mode='w', encoding='utf-8') as f:
                json.dump(stops_geojson, f, ensure_ascii=False)

            self.show_geojson(output_dir,
                              stops_filename,
                              route_filename,
                              feed_info["group"])

        self.ui.close()

    def get_yyyymmdd(self):
        if not self.ui.filterByDateCheckBox.isChecked():
            return ''
        date = self.ui.filterByDateDateEdit.date()
        yyyy = str(date.year()).zfill(4)
        mm = str(date.month()).zfill(2)
        dd = str(date.day()).zfill(2)
        return yyyy + mm + dd

    def get_delimiter(self):
        if not self.ui.unifyCheckBox.isChecked():
            return ''
        if not self.ui.delimiterCheckBox.isChecked():
            return ''
        return self.ui.delimiterLineEdit.text()

    def get_time_filter(self, lineEdit):
        if not self.ui.timeFilterCheckBox.isChecked():
            return ''
        return lineEdit.text().replace(':', '')

    def show_geojson(self, geojson_dir: str, stops_filename: str, route_filename: str, group_name: str):
        # these geojsons will already have been generated
        stops_geojson = os.path.join(geojson_dir, stops_filename)
        routes_geojson = os.path.join(geojson_dir, route_filename)

        stops_vlayer = QgsVectorLayer(
            stops_geojson, stops_filename.split('.')[0], 'ogr')
        routes_vlayer = QgsVectorLayer(
            routes_geojson, route_filename.split('.')[0], 'ogr')

        # make and set labeling for stops
        stops_labeling = get_labeling_for_stops(
            target_field_name="stop_name" if self.ui.simpleRadioButton.isChecked() else "similar_stop_name")
        stops_vlayer.setLabelsEnabled(True)
        stops_vlayer.setLabeling(stops_labeling)

        # adjust layer visibility
        stops_vlayer.setMinimumScale(STOPS_MINIMUM_VISIBLE_SCALE)
        stops_vlayer.setScaleBasedVisibility(True)

        # there are two type route renderer, normal, frequency
        if self.ui.simpleRadioButton.isChecked():
            routes_renderer = Renderer(routes_vlayer, 'route_name')
            routes_vlayer.setRenderer(routes_renderer.make_renderer())
            added_layers = [routes_vlayer, stops_vlayer]
            stops_renderer = Renderer(stops_vlayer, 'stop_name')
            stops_vlayer.setRenderer(stops_renderer.make_renderer())
        else:
            # frequency mode
            routes_vlayer.loadNamedStyle(os.path.join(
                os.path.dirname(__file__), 'frequency.qml'))
            stops_vlayer.loadNamedStyle(os.path.join(
                os.path.dirname(__file__), 'frequency_stops.qml'))
            csv_vlayer = QgsVectorLayer(os.path.join(
                geojson_dir, FILENAME_RESULT_CSV), FILENAME_RESULT_CSV, 'ogr')
            added_layers = [routes_vlayer, stops_vlayer, csv_vlayer]

        # add two layers as a group
        self.add_layers_as_group(group_name, added_layers)

        self.iface.messageBar().pushInfo(
            self.tr('finish'),
            self.tr('generated geojson files: ') + geojson_dir)
        self.ui.close()

    def refresh(self):
        self.localDataSelectAreaWidget.setVisible(
            self.repositoryCombobox.currentData() == REPOSITORY_ENUM['preset'])
        self.japanDpfDataSelectAreaWidget.setVisible(
            self.repositoryCombobox.currentData() == REPOSITORY_ENUM['japanDpf'])

        self.setFixedHeight(
            WINDOW_HEIGHT[self.repositoryCombobox.currentData()])

        self.ui.zipFileWidget.setEnabled(
            self.ui.comboBox.currentText() == self.combobox_zip_text)
        self.ui.pushButton.setEnabled((len(self.get_target_feed_infos()) > 0) and
                                      (self.ui.outputDirFileWidget.filePath() != ''))

        # stops unify mode
        is_unify = self.ui.unifyCheckBox.isChecked()
        self.ui.delimiterCheckBox.setEnabled(is_unify)
        self.ui.delimiterLineEdit.setEnabled(is_unify)

        # filter by times mode
        has_time_filter = self.ui.timeFilterCheckBox.isChecked()
        self.ui.beginTimeLineEdit.setEnabled(has_time_filter)
        self.ui.endTimeLineEdit.setEnabled(has_time_filter)

        # radio button - mode toggle
        self.ui.simpleFrame.setEnabled(self.ui.simpleRadioButton.isChecked())
        self.ui.freqFrame.setEnabled(self.ui.freqRadioButton.isChecked())

    def add_layers_as_group(self, group_name: str, layers: [QgsMapLayer]):
        """
        add layers into project as a group.
        the order of layers is reverse to layers list order.
        if layers: [layer_A, layer_B, layer_C]
        then in tree:
        - layer_C
        - layer_B
        - layer_A

        Args:
            group_name (str): [description]
            layers ([type]): [description]
        """
        root = QgsProject().instance().layerTreeRoot()
        group = root.insertGroup(0, group_name)
        group.setExpanded(True)
        for layer in layers:
            QgsProject.instance().addMapLayer(layer, False)
            group.insertLayer(0, layer)

    @staticmethod
    def validate_time_lineedit(lineedit):
        digits = ''.join(
            list(filter(lambda char: char.isdigit(), list(lineedit.text())))).ljust(6, "0")[-6:]

        # limit to 29:59:59
        hh = str(min(29, int(digits[0:2]))).zfill(2)
        mm = str(min(59, int(digits[2:4]))).zfill(2)
        ss = str(min(59, int(digits[4:6]))).zfill(2)

        formatted_time_text = hh + ":" + mm + ":" + ss
        lineedit.setText(formatted_time_text)

    def japan_dpf_search(self):
        target_date = self.ui.japanDpfTargetDateEdit.date()
        yyyy = str(target_date.year()).zfill(4)
        mm = str(target_date.month()).zfill(2)
        dd = str(target_date.day()).zfill(2)

        extent = None if self.japanDpfExtentGroupBox.outputExtent().isEmpty(
        ) else self.japanDpfExtentGroupBox.outputExtent().toString().replace(" : ", ",")

        pref = None if self.japanDpfPrefectureCombobox.currentData(
        ) is None else urllib.parse.quote(self.japanDpfPrefectureCombobox.currentData())

        results = repository.japan_dpf.api.get_feeds(yyyy+mm+dd,
                                                     extent=extent,
                                                     pref=pref)
        self.japan_dpf_set_table(results)

    def japan_dpf_set_table(self, results: list):
        model = repository.japan_dpf.table.Model(results)
        proxyModel = QSortFilterProxyModel()
        proxyModel.setDynamicSortFilter(True)
        proxyModel.setSortCaseSensitivity(Qt.CaseInsensitive)
        proxyModel.setSourceModel(model)

        self.japanDpfResultTableView.setModel(proxyModel)
        self.japanDpfResultTableView.setCornerButtonEnabled(True)
        self.japanDpfResultTableView.setSortingEnabled(True)

    def get_selected_row_data_in_japan_dpf_table(self, row: int):
        data = {}
        for col_idx, col_name in enumerate(repository.japan_dpf.table.HEADERS):
            data[col_name] = self.japanDpfResultTableView.model().index(row,
                                                                        col_idx).data()
        return data
