#!/usr/bin/env python3

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QDialog, QTableWidget, QTableWidgetItem, QLineEdit, QLabel, QSpacerItem, QSizePolicy, QFrame, QAction, QProgressDialog, QFileDialog
from PyQt5.QtWebEngineWidgets import QWebEngineView
import pyqtgraph as pg
import numpy as np
import time
import sys
# Bluetooth is imported solely to handle exceptions; needs some rethinking.
import bluetooth
import cms50ew

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        btDialogAction = QAction(QtGui.QIcon('icons/network-bluetooth.svg'),
                                 'Open Bluetooth device', self)
        btDialogAction.triggered.connect(self.on_btDialogAction)
        
        serDialogAction = QAction(QtGui.QIcon('icons/usb.svg'), 
                                  'Open USB device', self)
        serDialogAction.triggered.connect(self.on_serDialogAction)
        
        self.sessDialogAction = QAction(QtGui.QIcon('icons/appointment-new.svg'), 
                                        'Retrieve recorded data', self)
        self.sessDialogAction.setEnabled(False)
        self.sessDialogAction.triggered.connect(self.on_sessDialogAction)
        
        self.liveRunAction = QAction(QtGui.QIcon('icons/media-playback-start-symbolic.svg'), 
                                     'Retrieve live data', self)
        self.liveRunAction.setEnabled(False)
        self.liveRunAction.triggered.connect(self.on_liveRunAction)
        self.live_running = False
        
        self.liveSaveAction = QAction(QtGui.QIcon('icons/document-save-as-symbolic.svg'), 
                                      'Save recorded live data', self)
        self.liveSaveAction.setEnabled(False)
        self.liveSaveAction.triggered.connect(self.on_liveSaveAction)
        
        quitAction = QAction(QtGui.QIcon('icons/application-exit-symbolic.svg'),
                             'Quit', self)
        quitAction.setShortcut('Ctrl+q')
        quitAction.triggered.connect(self.on_quitAction)
        
        spacer = QtGui.QWidget()
        spacer.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
                                  
        toolBar = self.addToolBar('Toolbar')
        toolBar.setMovable(0)
        toolBar.addAction(btDialogAction)
        toolBar.addAction(serDialogAction)
        toolBar.addSeparator()
        toolBar.addAction(self.liveRunAction)
        toolBar.addAction(self.liveSaveAction)
        toolBar.addSeparator()
        toolBar.addAction(self.sessDialogAction)
        toolBar.addWidget(spacer)
        toolBar.addAction(quitAction)
        toolBar.setIconSize(QtCore.QSize(32, 32))
        
        self.statusBar = self.statusBar()
        self.statusBar.showMessage('Status: Disconnected')
        
        self.setGeometry(300, 300, 1800, 800)
        self.setWindowTitle('CMS50EW Plotter') 
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg'))  
        
        self.cw = MainWidget()
        self.setCentralWidget(self.cw)
        
        self.show()
        
    def on_btDialogAction(self):
        self.devDialog = DeviceDialog(is_bluetooth=True)
        self.devDialog.exec_()
        
    def on_serDialogAction(self):
        self.devDialog = DeviceDialog()
        self.devDialog.exec_()
        
    def on_sessDialogAction(self):
        self.sessDialog = SessionDialog()
        self.sessDialog.exec_()
        
    def on_liveRunAction(self):
        if not self.live_running:
            self.live_running = True
            self.liveThread = LiveThread(self.oxi)
            self.liveThread.start()
            self.liveRunAction.setIcon(QtGui.QIcon('icons/media-playback-stop-symbolic.svg'))
            self.sessDialogAction.setEnabled(False)
            self.statusBar.showMessage('Status: Initiating live stream ...')
        else:
            self.live_running = False
            self.oxi.close_device()
            self.oxi.setup_device(self.oxi.target, is_bluetooth=self.oxi.is_bluetooth)
            self.liveRunAction.setIcon(QtGui.QIcon('icons/media-playback-start-symbolic.svg'))
            self.statusBar.showMessage('Status: Disconnected')
            self.label_pulse_rate = QtGui.QLabel('Pulse rate: n/a')
            self.label_spo2 = QtGui.QLabel('SpO2: n/a')
            self.liveSaveAction.setEnabled(True)
            self.sessDialogAction.setEnabled(True)
            
    def on_liveSaveAction(self):
        self.saveDialog = LiveSaveDialog()
        self.saveDialog.exec_()
    
    def on_quitAction(self):
        self.live_running = False
        app.quit()

class MainWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        ## Use a grid layout
        layout = QtGui.QGridLayout()
        self.setLayout(layout)
        
        ## Create widgets
        self.label_pulse_rate = QtGui.QLabel('Pulse rate: n/a')
        self.label_spo2 = QtGui.QLabel('SpO2: n/a')

        ### Create pyqtgraph widgets
        pulse_plot = pg.PlotWidget(title='Pulse rate')
        pulse_plot.setLabel('left', text='Pulse rate [bpm]')
        pulse_plot.setLabel('bottom', text='Time [s]')
        pulse_plot.setYRange(0, 220)

        spo2_plot = pg.PlotWidget(title='SpO2')
        spo2_plot.setLabel('left', text='SpO2 [%]')
        spo2_plot.setLabel('bottom', text='Time [s]')
        spo2_plot.setYRange(0, 100)

        pg.setConfigOptions(antialias=True)

        self.pulse_curve = pulse_plot.plot(pen=pg.mkPen('g', width=2))
        self.spo2_curve = spo2_plot.plot(pen=pg.mkPen('r', width=2))
        
        layout.addWidget(self.label_pulse_rate, 0, 0, 1, 0)
        layout.addWidget(self.label_spo2, 1, 0, 1, 0)
        layout.addWidget(pulse_plot, 2, 0, 1, 1)
        layout.addWidget(spo2_plot, 2, 1, 1, 1)
        
class LiveSaveDialog(QDialog):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle('Save live data')
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg'))
        
        self.buttonBox = QtGui.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel)
        self.buttonBox.rejected.connect(self.close)
        
        self.plotPygalButton = QtGui.QPushButton(self)
        self.plotPygalButton.setText('Plot with Pygal')
        self.plotPygalButton.clicked.connect(self.on_plotPygal)
        
        self.plotMplButton = QtGui.QPushButton(self)
        self.plotMplButton.setText('Plot with Matplotlib')
        self.plotMplButton.clicked.connect(self.on_plotMpl)
        
        self.saveCSVButton = QtGui.QPushButton(self)
        self.saveCSVButton.setText('Save data as CSV file')
        self.saveCSVButton.clicked.connect(self.on_saveCSV)
        
        self.verticalLayout = QtGui.QVBoxLayout(self)
        self.verticalLayout.addWidget(self.plotPygalButton)
        self.verticalLayout.addWidget(self.plotMplButton)
        self.verticalLayout.addWidget(self.saveCSVButton)
        self.verticalLayout.addWidget(self.buttonBox)
        
        self.build_data_list()
        
    def build_data_list(self):
        # Empty list in case a session was download before
        w.oxi.stored_data = []
        data_point = 1 # Skip first points as they have hard-coded values
        counter = 1
        save_every = round((len(w.oxi.pulse_xdata) / w.oxi.pulse_xdata[-1]) * 2)
        while data_point != w.oxi.n_data_points:
            # The device sends approx. 60 data points per second.
            # To save two per second is plenty, I think.
            if counter == save_every:
                # Build list of values in format [time, finger_status, pulse_rate, spo2_value]
                values = [ w.oxi.pulse_xdata[data_point], w.oxi.finger_data[data_point],
                          w.oxi.pulse_ydata[data_point], w.oxi.spo2_ydata[data_point]]
                # Append value list to stored_data list.
                w.oxi.stored_data.append(values)
                counter = 1
            else:
                counter += 1
            data_point += 1
        print(w.oxi.stored_data)
        print(len(w.oxi.stored_data))
        print(w.oxi.n_data_points)
            
        
    def on_plotPygal(self):
        self.close()
        plotPygal = PlotPygal(live=True)
        plotPygal.exec_()
        
    def on_plotMpl(self):
        self.close()
        w.oxi.plot_mpl()
        
    def on_saveCSV(self):
        self.close()
        filename = QFileDialog.getSaveFileName(self)[0]
        if filename:
            print(filename)
            w.oxi.write_csv(filename)
        else:
            print('No file selected')
        
class SessionDialog(QDialog):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle('Select stored data')
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg')) 
        
        self.buttonBox = QtGui.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel)
        self.buttonBox.rejected.connect(self.close)
        
        self.getInfoButton = QtGui.QPushButton(self)
        self.getInfoButton.setText('Retrieve session information')
        self.getInfoButton.clicked.connect(self.getInfo)
        
        self.sessionTable = QTableWidget()
        # Make the table uneditable
        self.sessionTable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.sessionTable.setRowCount(5)
        self.sessionTable.setColumnCount(1)
        self.sessionTable.setHorizontalHeaderLabels(['Session information'])
        self.sessionTable.setVerticalHeaderLabels(['Stored data', 'User', 'Duration', 'Data points (calc)', 'Actual data points:'])
        self.sessionTable.horizontalHeader().setStretchLastSection(True)
        self.sessionTable.itemDoubleClicked.connect(self.getSessionData)
        
        self.plotButton = QtGui.QPushButton(self)
        self.plotButton.setText('Plot data')
        self.plotButton.setEnabled(False)
        self.plotButton.clicked.connect(self.on_plotData)
        
        self.plotPygalButton = QtGui.QPushButton(self)
        self.plotPygalButton.setText('Plot with Pygal')
        self.plotPygalButton.setEnabled(False)
        self.plotPygalButton.clicked.connect(self.on_plotPygal)
        
        self.plotMplButton = QtGui.QPushButton(self)
        self.plotMplButton.setText('Plot with Matplotlib')
        self.plotMplButton.setEnabled(False)
        self.plotMplButton.clicked.connect(self.on_plotMpl)
        
        self.saveCSVButton = QtGui.QPushButton(self)
        self.saveCSVButton.setText('Save data as CSV file')
        self.saveCSVButton.setEnabled(False)
        self.saveCSVButton.clicked.connect(self.on_saveCSV)
        
        self.verticalLayout = QtGui.QVBoxLayout(self)
        self.verticalLayout.addWidget(self.getInfoButton)
        self.verticalLayout.addWidget(self.sessionTable)
        self.verticalLayout.addWidget(self.plotButton)
        self.verticalLayout.addWidget(self.plotPygalButton)
        self.verticalLayout.addWidget(self.plotMplButton)
        self.verticalLayout.addWidget(self.saveCSVButton)
        self.verticalLayout.addWidget(self.buttonBox)
        self.resize(600, 700)
        
    def getInfo(self):
        self.getInfoButton.setText('Retrieving session information ...')
        
        w.oxi.initiate_device()
        w.oxi.get_user()
        w.oxi.get_session_count()
        w.oxi.get_session_duration()
        
        self.sessionTable.setItem(0, 0, QTableWidgetItem(w.oxi.sess_available))
        self.sessionTable.setItem(1, 0, QTableWidgetItem(w.oxi.user))
        self.sessionTable.setItem(2, 0, QTableWidgetItem(str(w.oxi.sess_duration)))
        self.sessionTable.setItem(3, 0, QTableWidgetItem(str(w.oxi.sess_data_points)))
        self.getInfoButton.setText('Done. Double-click info to download')
        
    def getSessionData(self):
        self.dlThread = DownloadDataThread()
        self.dlThread.start()
        
    def on_plotData(self):
        # Reset plot data and rendered plot
        w.oxi.pulse_xdata = []
        w.oxi.pulse_ydata = []
        w.oxi.spo2_xdata = []
        w.oxi.spo2_ydata = []
        w.cw.pulse_curve.clear()
        w.cw.spo2_curve.clear()
        
        # Fill plot data
        for data in w.oxi.stored_data:
            w.oxi.pulse_ydata.append(data[2])
            w.oxi.pulse_xdata.append(data[0])
            w.oxi.spo2_ydata.append(data[3])
            w.oxi.spo2_xdata.append(data[0])
        
        # Render plot
        w.cw.pulse_curve.setData(w.oxi.pulse_xdata, w.oxi.pulse_ydata)
        w.cw.spo2_curve.setData(w.oxi.spo2_xdata, w.oxi.spo2_ydata)
        
    def on_plotPygal(self):
        self.close()
        plotPygal = PlotPygal()
        plotPygal.exec_()
        
    def on_plotMpl(self):
        self.close()
        w.oxi.plot_mpl()
        
    def on_saveCSV(self):
        filename = QFileDialog.getSaveFileName(self)[0]
        if filename:
            print(filename)
            w.oxi.write_csv(filename)
        else:
            print('No file selected')
            
class PlotPygal(QDialog):
    def __init__(self, live=False):
        super().__init__()
        
        self.live = live
        
        self.setWindowTitle('Saved session plotted with Pygal')
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg')) 
        
        self.webW = QWebEngineView()
        
        self.saveButton = QtGui.QPushButton(self)
        self.saveButton.setText('Save as SVG')
        self.saveButton.clicked.connect(self.saveSVG)
        
        self.verticalLayout = QtGui.QVBoxLayout(self)
        self.verticalLayout.addWidget(self.webW)
        self.verticalLayout.addWidget(self.saveButton)
        
        self.plotPygal()
        
    def plotPygal(self):
        w.oxi.plot_pygal(live=self.live)
        
        self.webW.setContent(w.oxi.chart, mimeType='image/svg+xml')
        self.show()
        
    def saveSVG(self):
        filename = QFileDialog.getSaveFileName(self)[0]
        if filename:
            print(filename)
            w.oxi.write_svg(filename)
        else:
            print('No file selected')

class DownloadDataThread(QtCore.QThread):
    """Downloads stored session data as a thread to allow UI responsiveness"""
    def __init__(self):
        super().__init__()
        
    def run(self):
        self.diag = DownloadData()
        self.diag.show()
        time.sleep(0.1) # Allow the window to be constructed to avoid crash when 
                        # download is finished too fast
        self.downloadData()

    def downloadData(self):
        w.oxi.send_cmd(w.oxi.cmd_get_session_data)
        value = 1
        w.oxi.stored_data = []
        while w.oxi.download_data(): # CMS50EW.download_data() return False if no data is left
            if self.diag.wasCanceled():
                print('Download canceled by user')
                # Now reset device
                w.oxi.close_device()
                w.oxi.setup_device()
                w.oxi.initiate_device()
                break
            if value < w.oxi.sess_data_points:
                self.diag.setValue(value)
            else:
                self.diag.setValue(w.oxi.sess_data_points)
                print('Setting value to:', w.oxi.sess_data_points)
            value += 1
        self.diag.setValue(w.oxi.sess_data_points)
        w.sessDialog.sessionTable.setItem(4, 0,
                                             QTableWidgetItem(str(len(w.oxi.stored_data))))
        w.sessDialog.plotButton.setEnabled(True)
        w.sessDialog.plotPygalButton.setEnabled(True)
        w.sessDialog.plotMplButton.setEnabled(True)
        w.sessDialog.saveCSVButton.setEnabled(True)
        print('Downloading data finished')
        
class DownloadData(QProgressDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Downloading data ...')
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg')) 
        self.setLabelText('Downloading data ...')
        self.setCancelButtonText('Abort')
        self.setMinimum(0)
        print('Data points:', w.oxi.sess_data_points)
        self.setMaximum(w.oxi.sess_data_points)
        self.setModal(True)
        self.setFocus()
        
class DeviceDialog(QDialog):
    def __init__(self, is_bluetooth=False):
        super().__init__()
        
        self.is_bluetooth = is_bluetooth
        
        if self.is_bluetooth:
            type = 'Bluetooth'
            target_type = 'address'
        else:
            type = 'serial'
            target_type = 'port'
        
        self.setWindowIcon(QtGui.QIcon('icons/pulse.svg')) 
        self.setWindowTitle(str('Select or enter ' + type + ' device'))
        self.buttonBox = QtGui.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel)
        self.buttonBox.rejected.connect(self.close)
        
        self.scanButton = QtGui.QPushButton(self)
        self.scanButton.setText(str('Scan for ' + type + ' devices'))
        self.scanButton.clicked.connect(self.scan)
        
        self.horizontalSpacer = QFrame()
        self.horizontalSpacer.setFrameShape(QFrame.HLine)
        
        self.deviceTextBox = QLineEdit(self)
        self.deviceTextBox.returnPressed.connect(self.onReturnPressed)
        self.deviceTextBoxLabel = QLabel(self)
        self.deviceTextBoxLabel.setText(str('Enter device ' + target_type + ':'))
        
        
        self.devicesTable = QTableWidget()
        # Make the table uneditable
        self.devicesTable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        if self.is_bluetooth:
            self.devicesTable.setRowCount(0)
            self.devicesTable.setColumnCount(2)
            self.devicesTable.setHorizontalHeaderLabels(('MAC address', 'Device name'))
        else:
            self.devicesTable.setRowCount(0)
            self.devicesTable.setColumnCount(1)
            self.devicesTable.setHorizontalHeaderLabels(['List of serial ports'])
        self.devicesTable.horizontalHeader().setStretchLastSection(True)
        self.devicesTable.itemDoubleClicked.connect(self.onItemClicked)
        
        self.infoTable = QTableWidget()
        # Make the table uneditable
        self.infoTable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)  
        self.infoTable.setRowCount(4)
        self.infoTable.setColumnCount(1)
        self.infoTable.setHorizontalHeaderLabels(['Information string'])
        self.infoTable.horizontalHeader().setStretchLastSection(True)
        self.infoTable.setVerticalHeaderLabels(['Vendor', 'Model', 'User', 'Stored data'])
        self.infoTable.resizeRowsToContents()
        self.infoTable.resizeColumnsToContents()
        self.infoTable.itemDoubleClicked.connect(self.onDeviceClicked)
        
        self.verticalLayout = QtGui.QVBoxLayout(self)
        self.verticalLayout.addWidget(self.deviceTextBoxLabel)
        self.verticalLayout.addWidget(self.deviceTextBox)
        self.verticalLayout.addWidget(self.horizontalSpacer)
        self.verticalLayout.addWidget(self.scanButton)
        self.verticalLayout.addWidget(self.devicesTable)
        self.verticalLayout.addWidget(self.infoTable)
        self.verticalLayout.addWidget(self.buttonBox)
        self.resize(600, 800)
        
    def scan(self):
        """Scan for devices and populate table with results. """
        self.scanButton.setText('Scanning ...')
        QtGui.QApplication.processEvents()
        
        devicescan = cms50ew.DeviceScan(is_bluetooth=self.is_bluetooth)
        
        row = 0
        if self.is_bluetooth:
            self.devicesTable.setRowCount(len(devicescan.devices_dict))
            for address, name in devicescan.devices_dict.items():
                self.devicesTable.setItem(row, 0, QTableWidgetItem(address))
                self.devicesTable.setItem(row, 1, QTableWidgetItem(name))
                row += 1
        else:
            self.devicesTable.setRowCount(len(devicescan.accessible_ports))
            for port in devicescan.accessible_ports:
                self.devicesTable.setItem(row, 0, QTableWidgetItem(port))
                row += 1

        self.scanButton.setText('Scan finished')
        QtGui.QApplication.processEvents()
        
    def onItemClicked(self):
        """Get wanted device from table and retrieve information"""
        item = self.devicesTable.selectedItems()[0]        
        self.target = self.devicesTable.item(item.row(), 0).text()

        self.getDeviceInformation()
        
    def getDeviceInformation(self):
        self.scanButton.setText('Retrieving info from ' + self.target + ' ...')
        QtGui.QApplication.processEvents()
        
        oxi = cms50ew.CMS50EW()
        
        oxi.setup_device(self.target, is_bluetooth=self.is_bluetooth)
            
        if not oxi.initiate_device():
            self.scanButton.setText('No response from device')
            QtGui.QApplication.processEvents()
        else:
            oxi.get_model()
            oxi.get_vendor()
            oxi.get_user()
            oxi.get_session_count()
            oxi.get_session_duration()
        
            self.infoTable.setItem(0, 0, QTableWidgetItem(oxi.vendor))
            self.infoTable.setItem(1, 0, QTableWidgetItem(oxi.model))
            self.infoTable.setItem(2, 0, QTableWidgetItem(oxi.user))
            self.infoTable.setItem(3, 0, 
                                   QTableWidgetItem(str(oxi.sess_available + ' (Duration: ' + str(oxi.sess_duration) + ')')))
            
            self.scanButton.setText('Device information received')
            QtGui.QApplication.processEvents()
            
    def onDeviceClicked(self):
        self.setupDevice()
        
    def onReturnPressed(self):
        self.target = self.deviceTextBox.text()
        self.setupDevice()
        
    def setupDevice(self):
        self.scanButton.setText('Connecting to ' + self.target + ' ...')
        QtGui.QApplication.processEvents()
        w.oxi = cms50ew.CMS50EW()
        
        if w.oxi.setup_device(self.target, is_bluetooth=self.is_bluetooth):
            if w.oxi.is_bluetooth:
                w.statusBar.showMessage('Status: Connected to Bluetooth device')
            else:
                w.statusBar.showMessage('Status: Opened serial port')
            w.liveRunAction.setEnabled(True)
            w.sessDialogAction.setEnabled(True)
            self.close()
        else:
            w.statusBar.showMessage('Status: Connection attempt unsuccessful')
            self.close()

class LiveThread(QtCore.QThread):
    def __init__(self, oxi):
        super().__init__()
        self.oxi = oxi

    def run(self):
        """
        Initiates live data feed and keeps it alive as long as our main QWidget is running.
        """
        w.cw.pulse_curve.clear()
        w.cw.spo2_curve.clear()
        starttime = time.time()
        while w.live_running:
            w.oxi.initiate_device()
            w.oxi.send_cmd(w.oxi.cmd_get_live_data)
            try:
                self.update_plot(starttime)
            except (TypeError, bluetooth.btcommon.BluetoothError):
                # The following if condition prevents printing the restarting message 
                # if oxi.close_device is called while thread is running
                if w.live_running:
                    print('Something happened.\nRestarting live feed ...')
    
    def append_plot_data(self, pulse_rate, spo2):
        """
        Helper function for self.update_plot() to append the actual live 
        data to the lists which get plotted eventually.
        """
        # Pulse rate and finger can be supplied as arguments to support appending
        # 'Finger out' and 'Low signal quality' events; see self.update_plot() 
        # for more details
        self.oxi.timer = time.time()
        self.oxi.pulse_xdata.append(self.oxi.timer - self.starttime)
        self.oxi.pulse_ydata.append(pulse_rate)
        self.oxi.spo2_xdata.append(self.oxi.timer - self.starttime)
        self.oxi.spo2_ydata.append(spo2)
        self.oxi.finger_data.append(self.finger)
        
    def update_plot(self, starttime):
        """Feeds plotting process with live data."""

        # The following variables serve to update the status only once if nothing changes
        self.starttime = starttime
        finger_out = False
        low_signal_quality = False
        processing_data = False
        if w.oxi.is_bluetooth:
            counter = 11
        else:
            counter = 0
    
        while w.live_running:
            data = w.oxi.process_data()
            self.finger = data[0]
            self.pulse_rate = data[1]
            self.spo2 = data[2]
    
            if self.finger == 'Y':
                # The counter serves to suppress small hiccups where the device reports
                # "Finger out" when it in fact isn't.
                if not finger_out and (counter > 10):
                    self.append_plot_data(0, 0)
                    w.statusBar.showMessage('Status: Finger out')
                    w.cw.label_pulse_rate.setText('Pulse rate: n/a')
                    w.cw.label_spo2.setText('SpO2: n/a')
                    print('Finger out!')
                    finger_out = True
                    low_signal_quality = False
                    processing_data = False
                    counter = 0
                elif not finger_out and (counter < 11):
                    # If there have been less than 11 "Finger out" events, just
                    # append the last valid value.
                    self.append_plot_data(self.oxi.pulse_ydata[-1],
                                          self.oxi.spo2_ydata[-1])
                    counter += 1
                else:
                    # If 'finger_out' is 'True', also supply '0' values.
                    self.append_plot_data(pulse_rate=0, spo2=0)
                    
            elif (self.pulse_rate == 0) or (self.spo2 == 0):
                self.append_plot_data(0, 0)
                if not low_signal_quality:
                    w.statusBar.showMessage('Status: Low signal quality')
                    w.cw.label_pulse_rate.setText('Pulse rate: n/a')
                    w.cw.label_spo2.setText('SpO2: n/a')
                    print('Low signal quality!')
                    finger_out = False
                    low_signal_quality = True
                    processing_data = False
            else:
                self.append_plot_data(self.pulse_rate, self.spo2)
                if not processing_data:
                    w.statusBar.showMessage('Status: Processing data ...')
                finger_out = False
                low_signal_quality = False
                processing_data = True
                
            if (self.oxi.n_data_points % 20) == 0:
                w.cw.pulse_curve.setData(self.oxi.pulse_xdata, self.oxi.pulse_ydata)
                w.cw.spo2_curve.setData(self.oxi.spo2_xdata, self.oxi.spo2_ydata)
                
                w.cw.label_pulse_rate.setText(str('Pulse rate: ' + str(self.pulse_rate) + ' bpm'))
                w.cw.label_spo2.setText(str('SpO2: ' + str(self.spo2) + ' %'))

            self.oxi.n_data_points += 1
            
if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()

    app.exec_()  

