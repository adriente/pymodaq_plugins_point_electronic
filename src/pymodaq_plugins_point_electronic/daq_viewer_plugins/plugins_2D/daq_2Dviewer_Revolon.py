import numpy as np

from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport, Axis
from pymodaq_gui.parameter import Parameter
from pymodaq_gui.plotting.utils.plot_utils import RoiInfo

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

from pymodaq_plugins_point_electronic.hardware.revolon import Revolon, config
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
    callback_signal = QtCore.Signal(int)
    params = comon_parameters + [
        {'title' : 'Scan parameters', 'name' : 'scan_params', 'type' : 'group', 'children' : [
            {'title': 'Image width', 'name': 'image_width', 'type': 'int', 'value': 512},
            {'title': 'Image height', 'name': 'image_height', 'type': 'int', 'value': 512},
            {'title': 'x2:', 'name': 'mult2', 'type': 'bool_push', 'value': False},
            {'title': '/2:', 'name': 'div2', 'type': 'bool_push', 'value': False},
            {'title': 'Line averaging:', 'name': 'line_averaging', 'type': 'list','value': 1,'limits' : [0,1,2,4,8,16,32,64,128,256]},
            {'title' : 'Dwell time (us)', 'name' : 'dwell_time', 'type' : 'int', 'value' : 10},
            # {'title' : 'Use Roi', 'name' : 'use_roi', 'type' : 'bool', 'value' : False}
            {'title' : 'Gain intensity', 'name' : 'gain_intensity', 'type' : 'slide', 'limits' : [0.0,100.0]},
            {'title' : 'Gain aspect ratio', 'name' : 'gain_ar', 'type' : 'slide', 'limits' : [-100.0,100.0]},
            {'title' : 'Scan rotation', 'name' : 'scan_rotation', 'type' : 'slide', 'limits' : [0.,359.9], 'value' : 0.0}
        ]},
        {'title' : 'Internal scan control', 'name' : 'int_scan_control', 'type' : 'group', 'children' : [
            {'title' : 'Disable internal scan', 'name' : 'scan_switch_state', 'type' : 'bool', 'value' : False},
            {'title' : 'Internal scan disabled', 'name' : 'scan_switch_led', 'type' : 'led', 'value' : False}
        ] },
    ]

    def ini_attributes(self):
        self.controller : Revolon = None
        self.x_axis = None
        self.y_axis = None
        self.roi_select_info : RoiInfo = None
        self.roi_select_viewer_index : int = None
        self.scan_gain_intensity = 0.0
        self.scan_gain_aspect_ratio = 0.0


    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "image_width":
            self.controller.image_width = param.value()
            self.set_axes()
        if param.name() == "image_height" :
            self.controller.image_height = param.value()
            self.set_axes()
        if param.name() == 'mult2' :
            if param.value():
                self.mult_img()
                param.setValue(False)
        if param.name() == 'div2' :
            if param.value():
                self.div_img()
                param.setValue(False)
        if param.name() == 'line_averaging' :
            self.controller.line_averaging = param.value()
        if param.name() == "dwell_time" :
            self.controller.dwell_time = param.value()
        if param.name() == "scan_switch_state" :
            self.controller.scan_switch_state = param.value()
        if param.name() == "gain_intensity" :
            self.scan_gain_intensity = param.value()
            self.set_scan_gain()
            self.update_gain_aspect_ratio()
        if param.name() == "gain_ar" :
            self.scan_gain_aspect_ratio = param.value()
            self.set_scan_gain()
        if param.name() == 'scan_rotation' : 
            self.controller.scan_rotation = param.value()
        #elif ...

    def mult_img(self) -> None :
        """
        Multiplies by two the width and height of the image, in pixels.
        """
        self.controller.image_width *= 2
        self.controller.image_height *= 2
        self.settings.child('scan_params', 'image_width').setValue(self.controller.image_width)
        self.settings.child('scan_params', 'image_height').setValue(self.controller.image_height)
        self.set_axes()

    def div_img(self) -> None :
        """
        Divides by two the width and height of the image, in pixels.
        """
        self.controller.image_width //= 2
        self.controller.image_height //= 2
        self.settings.child('scan_params', 'image_width').setValue(self.controller.image_width)
        self.settings.child('scan_params', 'image_height').setValue(self.controller.image_height)
        self.set_axes()

    def set_scan_gain(self) -> None :
        min_x, max_x, min_y, max_y = self.controller._get_scan_gain_range()
        self.scan_gain_aspect_ratio = ru.within_limits(self.scan_gain_aspect_ratio,
                                                       lower = -100.0 + self.scan_gain_intensity,
                                                       upper=100.0 - self.scan_gain_intensity)
        if self.scan_gain_aspect_ratio >= 0.0 :
            value_x = (max_x - min_x)*self.scan_gain_intensity/100.0 + min_x
            value_y = (max_y - min_y)*(self.scan_gain_intensity+self.scan_gain_aspect_ratio)/100.0 + min_y
        else :
            value_x = (max_x - min_x)*(self.scan_gain_intensity-self.scan_gain_aspect_ratio)/100.0 + min_x
            value_y = (max_y - min_y)*self.scan_gain_intensity/100.0 + min_y
        self.controller.scan_gain_x = value_x
        self.controller.scan_gain_y = value_y

    def update_gain_aspect_ratio(self) -> None :
        self.settings.child('scan_params', 'gain_ar').setValue(ru.within_limits(self.scan_gain_aspect_ratio,
                                                                                lower = -100.0 + self.scan_gain_intensity,
                                                                                upper=100.0 - self.scan_gain_intensity))
        self.settings.child('scan_params', 'gain_ar').setLimits([-100.0 + self.scan_gain_intensity,100.0 - self.scan_gain_intensity])

    # def roi_select(self, roi_info, ind_viewer = 0):
    #     self.roi_select_info = roi_info
    #     self.roi_select_viewer_index = ind_viewer
    
    def crosshair(self, crosshair_info, ind_viewer = 0):
        return super().crosshair(crosshair_info, ind_viewer)

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
            dfp = self.prepare_dfp(data)
            if status:
                self.dte_signal.emit(DataToExport('STEM image',
                                                data=dfp,
                                                dim='Data2D'))
            else :
                self.dte_signal_temp.emit(DataToExport('STEM image',
                                                data=dfp,
                                                dim='Data2D'))
        except Exception as e:
            print("An exception occured in emit data")
            self.emit_status(ThreadCommand('Update_Status', [str(e), 'log']))

    def set_axes(self) :
        data_x_axis = np.linspace(start= 0,
                                  stop = self.controller.image_width,
                                  num = self.controller.image_width)
        data_y_axis = np.linspace(start= 0,
                                  stop = self.controller.image_height,
                                  num = self.controller.image_height)
        channel_number = len(self.controller.config.channels)
        dummy_data = [np.zeros((self.controller.image_height,self.controller.image_width)),]*channel_number
        self.y_axis = Axis(data=data_y_axis, label='', units='', index=0)
        self.x_axis = Axis(data=data_x_axis, label='', units='', index=1)
        dfp = self.prepare_dfp(dummy_data)
        self.dte_signal_temp.emit(DataToExport('STEM',data=dfp))
    
    def prepare_dfp(self,data_list : list) :
        dfp = [DataFromPlugins(name = config('REVOLON',
                                             'scan_profiles',
                                             self.controller.scan_profile,
                                             'channels')[i],
                               data = [np.atleast_1d(data.reshape((self.controller.image_height,
                                                                   self.controller.image_width)))],
                               dim = 'Data2D',axes=[self.x_axis, self.y_axis]
                               )
                                for i,data in enumerate(data_list) ]
        return dfp
    
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
        self.controller = self.ini_detector_init(slave_controller=controller, new_controller= Revolon())
        if self.is_master :
            connect_rc = self.controller.connect()

            if connect_rc == consts_sc.SUCCESS :

            # init axes from image
                info = "The DAQ_viewer Revolon scan engine has successfully started"
                initialized = True

                self.callback = RevolonCallback(self.controller)
                self.callback_thread = QtCore.QThread()
                self.callback.moveToThread(self.callback_thread)
                self.callback.data_sig.connect(self.emit_data)  # when the wait for acquisition returns (with data taken), emit_data will be fired

                self.callback_signal.connect(self.callback.readout)
                self.callback_thread.callback = self.callback
                self.callback_thread.start()

            else :
                info = f"Init failed (return code {connect_rc:08X})!"
                initialized = False

        else : 
            self.controller = controller
            info = "A slave Revolon has been initialised"
            initialized = True

        self.set_axes()

        return info, initialized

    def close(self):
        """Gives the control of the internal scan back to the microscope and terminates the communication protocol."""
        if self.is_master :
            self.controller.scan_switch_state = False
            self.controller.dll.SetKeepInternalScanEnabled(self.controller.h_scan_job, self.controller._scan_switch_state)
            self.controller.close() 

    def stop(self):
        """
            stop the camera's actions.
        """
        try:
            self.controller.stop_immediately() 
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

            if kwargs.get('live',False) :
                # if self.settings['use_roi'] : 
                #     x_origin, y_origin, x_end, y_end = ru.from_roi_info_to_int_coordinates(self.roi_select_info)
                #     self.controller.start(num_frame=0, x_start=x_origin, y_start=y_origin, x_end=x_end, y_end=y_end)
                # else : 
                self.controller.start(num_frame=0)
                self.callback_signal.emit(0)

            else:
                # if self.settings['use_roi'] : 
                #     x_origin, y_origin, x_end, y_end = ru.from_roi_info_to_int_coordinates(self.roi_select_info)
                #     self.controller.start(num_frame=1, x_start=x_origin, y_start=y_origin, x_end=x_end, y_end=y_end)
                # else :
                self.controller.start(num_frame=Naverage)
                self.callback_signal.emit(Naverage)  # will trigger the waitfor acquisition

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [str(e), "log"]))


class RevolonCallback(QtCore.QObject):
    """

    """
    data_sig = QtCore.Signal(list,bool)
    # bool dans le data sig pour gérer le data_sig_temp

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def readout(self,num_frame : int):
        if num_frame == 0 :
            last_emit_time = time.time()
            while True :
                if self.controller.wait_for_acq() : 
                    status, data_list = self.controller.read_data()
                    current_time = time.time()
                    if (current_time -last_emit_time) > 0.1 :
                        if status.value in ((consts_sc.READ_STATUS_FRAME_END | consts_sc.READ_STATUS_BUFFER_EMPTY),
                                            consts_sc.READ_STATUS_FRAME_END) :
                            self.data_sig.emit(data_list, True)
                            last_emit_time = time.time()
                        else :
                            self.data_sig.emit(data_list,False)
                            last_emit_time = time.time()
                else :
                    break
        else :
            for _ in range(num_frame) :
                while True :
                    if self.controller.wait_for_acq() :
                        status, data_list = self.controller.read_data()
                        if status.value in ((consts_sc.READ_STATUS_FRAME_END | consts_sc.READ_STATUS_BUFFER_EMPTY),
                                            consts_sc.READ_STATUS_FRAME_END) :
                            self.data_sig.emit(data_list, True)
                            break
                        else :
                            self.data_sig.emit(data_list,False)
                    else :
                        break

if __name__ == '__main__':
    main(__file__)
