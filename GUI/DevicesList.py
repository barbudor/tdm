from functools import partial

from PyQt5.QtCore import Qt, QSettings, QSortFilterProxyModel
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QMessageBox, QDialog, QMenu, QApplication, QAction

from GUI import VLayout, Toolbar, TableView, columns
from GUI.DeviceEdit import DeviceEditDialog
from Util import DevMdl, initial_queries
from Util.models import DeviceDelegate
from Util.nodes import TasmotaDevice


class DevicesListWidget(QWidget):
    def __init__(self, parent, *args, **kwargs):
        super(DevicesListWidget, self).__init__(*args, **kwargs)
        self.setWindowTitle("Devices list")
        self.setWindowState(Qt.WindowMaximized)
        self.setLayout(VLayout(margin=0))

        self.mqtt = parent.mqtt

        self.settings = QSettings()
        self.settings.beginGroup('Devices')

        self.tb = Toolbar(Qt.Horizontal, 16, Qt.ToolButtonTextBesideIcon)
        self.tb.addAction(QIcon("GUI/icons/add.png"), "Add", self.device_add)

        self.actDevDelete = self.tb.addAction(QIcon("GUI/icons/delete.png"), "Remove", self.device_delete)
        self.actDevDelete.setEnabled(False)

        self.layout().addWidget(self.tb)

        self.device_list = TableView()
        self.model = parent.device_model
        self.telemetry_model = parent.telemetry_model
        self.sorted_device_model = QSortFilterProxyModel()
        self.sorted_device_model.setSourceModel(parent.device_model)
        self.device_list.setModel(self.sorted_device_model)
        self.device_list.setupColumns(columns)
        self.device_list.setSortingEnabled(True)
        self.device_list.setWordWrap(True)
        self.device_list.setItemDelegate(DeviceDelegate())
        self.device_list.sortByColumn(DevMdl.TOPIC, Qt.AscendingOrder)
        self.device_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layout().addWidget(self.device_list)

        self.device_list.clicked.connect(self.select_device)
        self.device_list.customContextMenuRequested.connect(self.show_list_ctx_menu)
        self.build_ctx_menu()

    def build_ctx_menu(self):
        self.ctx_menu = QMenu()
        self.ctx_menu.addAction("Refresh state", self.ctx_menu_refresh)
        self.ctx_menu.addAction("Refresh telemetry", self.ctx_menu_telemetry)
        self.ctx_menu.addSeparator()
        self.ctx_menu.addAction("Power ON", lambda: self.ctx_menu_power(state="ON"))
        self.ctx_menu.addAction("Power OFF", lambda: self.ctx_menu_power(state="OFF"))
        self.ctx_menu_relays = self.ctx_menu.addMenu("Relays")
        self.ctx_menu_relays.setEnabled(False)
        self.ctx_menu.addSeparator()
        self.ctx_menu.addAction("Delete retained messages for relays", lambda: self.ctx_menu_clean_retained)
        self.ctx_menu.addSeparator()
        ctx_menu_copy = self.ctx_menu.addMenu("Copy")
        self.ctx_menu.addSeparator()
        self.ctx_menu.addAction("Restart", self.ctx_menu_restart)

        ctx_menu_copy.addAction("IP", lambda: self.ctx_menu_copy_value(DevMdl.IP))
        ctx_menu_copy.addAction("MAC", lambda: self.ctx_menu_copy_value(DevMdl.MAC))
        ctx_menu_copy.addSeparator()
        ctx_menu_copy.addAction("Topic", lambda: self.ctx_menu_copy_value(DevMdl.TOPIC))
        ctx_menu_copy.addAction("FullTopic", lambda: self.ctx_menu_copy_value(DevMdl.FULL_TOPIC))
        ctx_menu_copy.addAction("STAT topic", lambda: self.ctx_menu_copy_prefix_topic("STAT"))
        ctx_menu_copy.addAction("CMND topic", lambda: self.ctx_menu_copy_prefix_topic("CMND"))
        ctx_menu_copy.addAction("TELE topic", lambda: self.ctx_menu_copy_prefix_topic("TELE"))

    def ctx_menu_copy_value(self, column):
        row = self.idx.row()
        value = self.model.data(self.model.index(row, column))
        QApplication.clipboard().setText(value)

    def ctx_menu_copy_prefix_topic(self, prefix):
        if prefix == "STAT":
            topic = self.model.statTopic(self.idx)
        elif prefix == "CMND":
            topic = self.model.commandTopic(self.idx)
        elif prefix == "TELE":
            topic = self.model.teleTopic(self.idx)
        QApplication.clipboard().setText(topic)

    def ctx_menu_clean_retained(self):
        relays = self.model.data(self.model.index(self.idx.row(), DevMdl.POWER))
        cmnd_topic = self.model.cmndTopic(self.idx)

        for r in relays.keys():
            self.mqtt.publish(cmnd_topic + r, retain=True)

    def ctx_menu_power(self, relay=None, state=None):
        relays = self.model.data(self.model.index(self.idx.row(), DevMdl.POWER))
        cmnd_topic = self.model.commandTopic(self.idx)
        if relay:
            self.mqtt.publish(cmnd_topic+relay, payload=state)

        elif relays:
            for r in relays.keys():
                self.mqtt.publish(cmnd_topic+r, payload=state)

    def ctx_menu_restart(self):
        self.mqtt.publish("{}/restart".format(self.model.commandTopic(self.idx)), payload="1")

    def ctx_menu_refresh(self):
        for q in initial_queries:
            self.mqtt.publish("{}/status".format(self.model.commandTopic(self.idx)), payload=q)

    def ctx_menu_telemetry(self):
        self.mqtt.publish("{}/status".format(self.model.commandTopic(self.idx)), payload=8)

    def show_list_ctx_menu(self, at):
        self.select_device(self.device_list.indexAt(at))
        relays = self.model.data(self.model.index(self.idx.row(), DevMdl.POWER))
        if relays and len(relays.keys()) > 1:
            self.ctx_menu_relays.setEnabled(True)
            self.ctx_menu_relays.clear()

            for r in relays.keys():
                actR = self.ctx_menu_relays.addAction("{} ON".format(r))
                actR.triggered.connect(lambda st, x=r: self.ctx_menu_power(x, "ON"))
                actR = self.ctx_menu_relays.addAction("{} OFF".format(r))
                actR.triggered.connect(lambda st, x=r: self.ctx_menu_power(x, "OFF"))
                self.ctx_menu_relays.addSeparator()
        else:
            self.ctx_menu_relays.setEnabled(False)
            self.ctx_menu_relays.clear()

        self.ctx_menu.popup(self.device_list.viewport().mapToGlobal(at))

    def select_device(self, idx):
        self.idx = self.sorted_device_model.mapToSource(idx)
        # self.actDevEdit.setEnabled(True)
        self.actDevDelete.setEnabled(True)
        self.device = self.model.data(self.model.index(idx.row(), DevMdl.TOPIC))

    def device_add(self):
        rc = self.model.rowCount()
        self.model.insertRow(rc)
        dlg = DeviceEditDialog(self.model, rc)
        dlg.full_topic.setText("%prefix%/%topic%/")

        if dlg.exec_() == QDialog.Accepted:
            self.model.setData(self.model.index(rc, DevMdl.FRIENDLY_NAME), self.model.data(self.model.index(rc, DevMdl.TOPIC)))
            topic = dlg.topic.text()
            tele_dev = self.telemetry_model.addDevice(TasmotaDevice, topic)
            self.telemetry_model.devices[topic] = tele_dev
        else:
            self.model.removeRow(rc)

    def device_delete(self):
        topic = self.model.topic(self.idx)
        if QMessageBox.question(self, "Confirm", "Do you want to remove '{}' from devices list?".format(topic)) == QMessageBox.Yes:
            self.model.removeRows(self.idx.row(),1)
            tele_idx = self.telemetry_model.devices.get(topic)
            if tele_idx:
                self.telemetry_model.removeRows(tele_idx.row(),1)

    def closeEvent(self, event):
        event.ignore()