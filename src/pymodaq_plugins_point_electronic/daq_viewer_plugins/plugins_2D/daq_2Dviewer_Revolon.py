import numpy as np

from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport, Axis
from pymodaq_gui.parameter import Parameter
from pymodaq_gui.plotting.utils.plot_utils import RoiInfo

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

from pymodaq_plugins_point_electronic.hardware.revolon import ScanController
from pymodaq_plugins_point_electronic.hardware import scan_control as consts_sc
from qtpy import QtWidgets, QtCore
from qtpy.QtCore import QThread
from pymodaq_plugins_point_electronic.hardware import revolon_utils as ru
from pymodaq_utils.logger import set_logger, get_module_name

import time

logger = set_logger(get_module_name(__file__))


class DAQ_2DViewer_Revolon(DAQ_Viewer_base):
    """ Instrument plugin class for a 2D viewer.

    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Viewer module through inheritance via
    DAQ_Viewer_base. It makes a bridge between the DAQ_Viewer module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of instruments that should be compatible with this instrument plugin.
        * With which instrument it has actually been tested.
        * The version of PyMoDAQ during the test.
        * The version of the operating system.
        * Installation instructions: what manufacturer’s drivers should be installed to make it run?

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.

    # TODO add your particular attributes here if any

    """
    live_mode_available = True
    callback_signal = QtCore.Signal()
    params = comon_parameters + [
        {'title': 'Image width', 'name': 'image_width', 'type': 'int', 'value': 512},
        {'title': 'Image height', 'name': 'image_height', 'type': 'int', 'value': 512},
        {'title' : 'Dwell time', 'name' : 'dwell_time', 'type' : 'int', 'value' : 1000},
        {'title' : 'Use Roi', 'name' : 'use_roi', 'type' : 'bool', 'value' : False}
    ]

    def ini_attributes(self):
        #  TODO declare the type of the wrapper (and assign it to self.controller) you're going to use for easy
        #  autocompletion
        self.controller : ScanController = None

        # TODO declare here attributes you want/need to init with a default value

        self.x_axis = None
        self.y_axis = None
        self.roi_select_info : RoiInfo = None
        self.roi_select_viewer_index : int = None
        self._data = None

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        # TODO for your custom plugin
        if param.name() == "image_width":
            self.controller.image_width = param.value()
            self.temp_data = np.zeros((self.controller.image_width, self.controller.image_height))
        if param.name() == "image_height" : 
            self.controller.image_height = param.value()
            self.temp_data = np.zeros((self.controller.image_width, self.controller.image_height))
        if param.name() == "dwell_time" : 
            self.controller.dwell_time = param.value()
        #elif ...

    def roi_select(self, roi_info, ind_viewer = 0):
        self.roi_select_info = roi_info
        self.roi_select_viewer_index = ind_viewer
    
    def crosshair(self, crosshair_info, ind_viewer = 0):
        return super().crosshair(crosshair_info, ind_viewer)

    # def emit_data(self):
    #     # Add a bool as arg so that I can pick finishing acquisition or current
    #     # Avant de broadcaster les données, il vaut mieux créer une copie pour éviter d'avoir des soucis de pointeur. Le reshape doit faire une copie à priori.
    #     """
    #         Fonction used to emit data obtained by callback.

    #         See Also
    #         --------
    #         daq_utils.ThreadCommand
    #     """
    #     try:
    #         self.controller.full = 1
    #         if self.settings['use_roi'] : 
    #             width, height = self.roi_select_info.size
    #             width = round(width)
    #             height = round(height)
    #             x_origin, y_origin, x_end, y_end = ru.from_roi_info_to_int_coordinates(self.roi_select_info)
    #             px_count, px_offset, data_slice = self.controller.acquired_data()
    #             data = self.temp_data.copy()
    #             data[x_origin:x_end,y_origin:y_end] = data_slice.reshape((width, height)).astype(float)
    #         else :
    #             width, height = self.controller.image_width, self.controller.image_height
    #         while self.controller.full :
    #             if self.settings['use_roi'] :
    #                 px_count, px_offset, data_slice = self.controller.acquired_data()
    #                 data = self.temp_data.copy()
    #                 data[x_origin:x_end,y_origin:y_end] = data_slice.reshape((width, height)).astype(float) 
                    
    #             else :
    #                 px_count, px_offset, data = self.controller.acquired_data()
                
    #             if (px_count.value == 0) and (px_offset.value == 0):
                    
    #                 self.dte_signal.emit(DataToExport('STEM image',
    #                                                 data=[DataFromPlugins(name='STEM image',
    #                                                 data=[np.atleast_1d(
    #                                                 data.reshape((self.controller.image_width,self.controller.image_height)).astype(float)) ],
    #                                                 dim='Data2D')]))
    #             else : 
    #                 self.dte_signal_temp.emit(DataToExport('STEM image',
    #                                                 data=[DataFromPlugins(name='STEM image',
    #                                                 data=[np.atleast_1d(
    #                                                 data.reshape((self.controller.image_width,self.controller.image_height)).astype(float)) ],
    #                                                 dim='Data2D')])
    #                 )
    #             QtWidgets.QApplication.processEvents()  # here to be sure the timeevents are executed even if in continuous grab mode
    #         if not(self.settings['use_roi']) : 
    #             self.temp_data = data.reshape((width,height)).astype(float)
    #         self.callback_signal.emit()


    #     except Exception as e:
    #         print("An exception occured in emit data")
    #         self.emit_status(ThreadCommand('Update_Status', [str(e), 'log']))
            
    def emit_data(self, data, status):
        # Add a bool as arg so that I can pick finishing acquisition or current
        # Avant de broadcaster les données, il vaut mieux créer une copie pour éviter d'avoir des soucis de pointeur. Le reshape doit faire une copie à priori.
        """
            Fonction used to emit data obtained by callback.

            See Also
            --------
            daq_utils.ThreadCommand
        """
        try:
            # self.controller.full = 
                
            if status:
                print('finished frame')
                self.dte_signal.emit(DataToExport('STEM image',
                                                data=[DataFromPlugins(name='STEM image',
                                                data=[np.atleast_1d(
                                                data.reshape((self.controller.image_width,self.controller.image_height)).astype(float)) ],
                                                dim='Data2D')]))
            else : 
                print('temp')
                self.dte_signal_temp.emit(DataToExport('STEM image',
                                                data=[DataFromPlugins(name='STEM image',
                                                data=[np.atleast_1d(
                                                data.reshape((self.controller.image_width,self.controller.image_height)).astype(float)) ],
                                                dim='Data2D')])
                )

        except Exception as e:
            print("An exception occured in emit data")
            self.emit_status(ThreadCommand('Update_Status', [str(e), 'log']))

    # def ini_detector(self, controller=None):
    #     """Detector communication initialization

    #     Parameters
    #     ----------
    #     controller: (object)
    #         custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
    #         (Master case)

    #     Returns
    #     -------
    #     info: str
    #     initialized: bool
    #         False if initialization failed otherwise True
    #     """
    #     self.controller = self.ini_detector_init(slave_controller=controller, new_controller= ScanController())
    #     if self.is_master : 
    #         connect_rc = self.controller.connect()

    #     if connect_rc == consts_sc.SUCCESS : 

    #     # init axes from image
    #         info = "The DAQ_viewer Revolon scan engine has successfully started"
    #         initialized = True
    #         iw, ih = self.controller.image_width, self.controller.image_height
    #         self.x_axis = Axis(data=np.linspace(0,  iw - 1, iw, dtype=int), label='Pixels', index=1)
    #         self.y_axis = Axis(data=np.linspace(0, ih - 1, ih, dtype=int), label='Pixels', index=1)
    #         self.temp_data = np.zeros((iw, ih))

    #         self.callback = MyCallback(self.controller.wait_for_acq)
    #         self.callback_thread = QtCore.QThread()
    #         self.callback.moveToThread(self.callback_thread)
    #         self.callback.data_sig.connect(self.emit_data)  # when the wait for acquisition returns (with data taken), emit_data will be fired

    #         self.callback_signal.connect(self.callback.read_status)
    #         self.callback_thread.callback = self.callback
    #         self.callback_thread.start()
    #     # self.previous_data = np.zeros((1048576,), dtype = np.uint16)

    #     else : 
    #         info = f"Init failed (return code {connect_rc:08X})!"
    #         initialized = False
    #     return info, initialized
    
    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.controller = self.ini_detector_init(slave_controller=controller, new_controller= ScanController())
        if self.is_master : 
            connect_rc = self.controller.connect()

        if connect_rc == consts_sc.SUCCESS : 

        # init axes from image
            info = "The DAQ_viewer Revolon scan engine has successfully started"
            initialized = True
            iw, ih = self.controller.image_width, self.controller.image_height
            self.x_axis = Axis(data=np.linspace(0,  iw - 1, iw, dtype=int), label='Pixels', index=1)
            self.y_axis = Axis(data=np.linspace(0, ih - 1, ih, dtype=int), label='Pixels', index=1)
            self._data = np.zeros((iw, ih))

            self.callback = MyCallback(self.controller)
            self.callback_thread = QtCore.QThread()
            self.callback.moveToThread(self.callback_thread)
            self.callback.data_sig.connect(self.emit_data)  # when the wait for acquisition returns (with data taken), emit_data will be fired

            self.callback_signal.connect(self.callback.readout)
            self.callback_thread.callback = self.callback
            self.callback_thread.start()
        # self.previous_data = np.zeros((1048576,), dtype = np.uint16)

        else : 
            info = f"Init failed (return code {connect_rc:08X})!"
            initialized = False
        return info, initialized

    def close(self):
        """Terminate the communication protocol"""
        ## TODO for your custom plugin
        if self.is_master :
            self.controller.close()  # when writing your own plugin remove this line
        #  self.controller.your_method_to_terminate_the_communication()  # when writing your own plugin replace this line

    def stop(self):
        """
            stop the camera's actions.
        """
        try:
            self.controller.stop_immediately()  # abort the camera actions
            # print('stopped')
        except:
            pass
        return ""

    def grab_data(self, Naverage=1, **kwargs):
        """
            Start new acquisition in two steps :
                * Initialize data: self.data for the memory to store new data and self.data_average to store the average data
                * Start acquisition with the given exposure in ms, in "1d" or "2d" mode

            =============== =========== =============================
            **Parameters**   **Type**    **Description**
            Naverage         int         Number of images to average
            =============== =========== =============================

            See Also
            --------
            daq_utils.ThreadCommand
        """
        try:

            if kwargs.get('live',False) == True :
                if self.settings['use_roi'] : 
                    x_origin, y_origin, x_end, y_end = ru.from_roi_info_to_int_coordinates(self.roi_select_info)
                    self.controller.start(num_frame=0, x_start=x_origin, y_start=y_origin, x_end=x_end, y_end=y_end)
                else : 
                    self.controller.start(num_frame=0)
                self.callback_signal.emit()

            else:
                if self.settings['use_roi'] : 
                    x_origin, y_origin, x_end, y_end = ru.from_roi_info_to_int_coordinates(self.roi_select_info)
                    self.controller.start(num_frame=1, x_start=x_origin, y_start=y_origin, x_end=x_end, y_end=y_end)
                else :
                    self.controller.start(num_frame=1)
                self.callback_signal.emit()  # will trigger the waitfor acquisition


        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [str(e), "log"]))


class MyCallback(QtCore.QObject):
    """

    """
    data_sig = QtCore.Signal(np.ndarray,bool)
    # bool dans le data sig pour gérer le data_sig_temp

    def __init__(self, controller):
        super(MyCallback, self).__init__()
        self.controller = controller

    def readout(self):
        last_emit_time = time.time()
        while True : 
            if self.controller.wait_for_acq() : 
                status, pix_count, pix_off, data = self.controller.acquired_data()
                print(f'pixel count : {pix_count.value} and pixel offset : {pix_off.value}')
                current_time = time.time()
                data[pix_off.value:pix_off.value+pix_count.value] +=np.random.randint(0,150)
                if (current_time -last_emit_time) > 0.25 : 
                    if status.value == 0x00000001 : 
                        self.data_sig.emit(data, True)
                        last_emit_time = time.time()
                    else : 
                        self.data_sig.emit(data,False)
                        last_emit_time = time.time()
            else :
                 
                break
            
# class MyCallback(QtCore.QObject):
#     """

#     """
#     data_sig = QtCore.Signal()
#     # bool dans le data sig pour gérer le data_sig_temp

#     def __init__(self, status_fn):
#         super(MyCallback, self).__init__()
#         self.status_fn = status_fn

#     def read_status(self):
#         ind = self.status_fn()
#         if ind == 0 :
#             pass
#         elif ind == 1 :
#             self.data_sig.emit()
#             # faire 2 cas, soit l'acqusition d'1 frame est en cours : data_sig_temp
#             # soit il a fini et il faut data_sig
#         elif ind == 2 :
#             logger.info("Acquisition Stopped")
#             #self.data_sig.emit(False)
#         else : 
#             raise NotImplementedError('Message to clarify TODO')





if __name__ == '__main__':
    main(__file__)
