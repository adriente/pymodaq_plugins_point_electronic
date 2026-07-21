from pymodaq_plugins_point_electronic.utils import Config
from pymodaq_plugins_point_electronic.hardware import scan_control as sc
import os
from ctypes import *
from sys import platform as op_sys
import platform as p
from pymodaq_plugins_point_electronic.hardware import revolon_utils as ru
from pint import Quantity
import numpy as np
from threading import Thread
from pymodaq_utils.logger import set_logger, get_module_name
import sys

import time

logger = set_logger(get_module_name(__file__))

################
# Code Outline #
################

# I. RevolonConfig
# II. Revolon
# I. 2. Initialisation
# I. 3. Data acquisition and axes
# I. 4. Properties
# II. Callback class
# III. Local testing code

# PyMoDAQ's Singleton config object
config = Config()

#################
# RevolonConfig #
#################

class RevolonConfig :
    """
    Class to convert human-readable config file parameters into dll-readable integers

    Attributes
    ----------
    channels : list[int]
        list of selected output channels (in dll-compatible integer)
    dtypes : list[int]
        list of selected dtype for each channel (in dll-compatible integer)
    
    Notes
    -----
    The flyback parameters are not documented here.
    See the SDK's documentation (especially the schematics related to the SetImageGeometry function) for further details.
    """
    _acceptable_channels = {'none' : sc.CHANNEL_SOURCE_NONE,
                            'a_fast_a' : sc.CHANNEL_SOURCE_A_FAST_A,
                            'a_fast_b' : sc.CHANNEL_SOURCE_A_FAST_B,
                            'a_slow' : sc.CHANNEL_SOURCE_A_SLOW,
                            'a_lia' : sc.CHANNEL_SOURCE_A_LIA,
                            'counter' : sc.CHANNEL_SOURCE_COUNTER,
                            'ecl_counter' : sc.CHANNEL_SOURCE_ECL_COUNTER}
    _acceptable_dtypes = {'invalid' : sc.CHANNEL_DATATYPE_INVALID,
                          'uint8' : sc.CHANNEL_DATATYPE_U8,
                          'uint16' : sc.CHANNEL_DATATYPE_U16,
                          'uint32' : sc.CHANNEL_DATATYPE_U32}

    def __init__(self):
        self.time_scale_converter = ru.TimeScaleConverter()
        self.channels = []
        self.dtypes = []
        self.flyback_steps = 0
        self.flyback_line_step_time = '0s'
        self.flyback_line_start_delay = '0s'
        self.flyback_line_prescan_pixels = 0
        self.flyback_frame_step_time = '0s'
        self.flyback_frame_prescan_lines = 0

    def load_profile(self, profile_name : str = 'basic_scan') :
        """
        For a given profile, loads the different flyback parameters.
        It performs the necessary conversions from human-readable values to dll-compatible integers.
        It also loads the associated channels (see load_channels). 
        
        Parameters
        ----------
        profile_name : str
            Name of the selected scan profile as written in the config file.
        """
        self.flyback_steps = config('REVOLON','scan_profiles',profile_name,'flyback_steps')
        self.flyback_line_step_time = self.time_scale_converter.from_quantity_to_int(
            config('REVOLON','scan_profiles',profile_name,'flyback_line_step_time')
            )
        self.flyback_line_start_delay = self.time_scale_converter.from_quantity_to_int(
            config('REVOLON','scan_profiles',profile_name,'flyback_line_start_delay')
            )
        self.flyback_line_prescan_pixels = config('REVOLON','scan_profiles',profile_name,'flyback_line_prescan_pixels')
        self.flyback_frame_step_time = self.time_scale_converter.from_quantity_to_int(
            config('REVOLON','scan_profiles',profile_name,'flyback_frame_step_time')
            )
        self.flyback_frame_prescan_lines = config('REVOLON','scan_profiles',profile_name,'flyback_frame_prescan_lines')
        self.load_channels(profile_name)

    def load_channels(self, profile_name : str = 'basic_scan') :
        """
        For a given profile, loads the different channel parameters (source + data type). 
        
        Parameters
        ----------
        profile_name : str
            Name of the selected scan profile as written in the config file.
        """
        self.channels = []
        try :
            for ch in config('REVOLON','scan_profiles',profile_name,'channels') :
                assert ch in self._acceptable_channels, f"{ch} is an invalid channel type, check RevolonConfig"
                self.channels.append(self._acceptable_channels[ch])
        except AssertionError : 
            ch_string = '\n'.join('{}'.format(*k) for k in self.channels)
            logger.info('Only the following channels were loaded : %s .',ch_string)

        self.dtypes = []
        try :
            for dt in config('REVOLON','scan_profiles',profile_name,'dtypes') :
                assert dt in self._acceptable_dtypes, f"{dt} is an invalid channel type, check RevolonConfig"
                self.dtypes.append(self._acceptable_dtypes[dt])
        except AssertionError :
            ch_string = '\n'.join('{}'.format(*k) for k in self.channels)
            logger.info('Only the following channels were loaded : %s .',ch_string)

        assert len(self.channels) == len(self.dtypes), f"dtypes and channels don't match.\nChannels : {self.channels}, Dtypes : {self.dtypes}"

###########
# Revolon #
###########

class Revolon :
    """
    Controller class that manages the communication with the Revolon hardware. 

    Attributes
    ----------
    config : RevolonConfig
        config object to manage flyback and channel parameters
    dll
        python object to call the method of the point electronic dll
    
    """
    def __init__(self, camera_controller = None) :
        self.config = RevolonConfig()
        self.camera_controller = camera_controller
        self.dll = self.load_dll()
        self._scan_profile = 'basic_scan'
        self.config.load_profile(self.scan_profile)
        self.h_scan_job = c_uint16(0)
        
        # Properties
        self._image_width = 512 # pixels
        self._image_height = 512 # pixels
        self._dwell_time = Quantity('10000 ns') #ns/pixel units, must be multiple of 10
        self._dwell_time_int = self._dwell_time.magnitude // 10
        self._status = c_uint32(0)
        self._frame_count = c_uint16(0)
        self._scan_switch_state = c_bool()
        self._scan_gain_x = c_float(1.21)
        self._scan_gain_y = c_float(1.21)
        self._line_averaging = c_uint16()
        

        # Advanced settings
        self._dac_x_step, self._dac_offset_x, self._dac_offset_y = ru.calculate_dac_increment(
            self._image_width,
            self._image_height,
            self.config.flyback_line_prescan_pixels,
            self.config.flyback_frame_prescan_lines
                                                      )
        self._dac_y_step = self._dac_x_step
        
        self.event_handles = (c_void_p * 4)()

        self._dac_x_off_pos, self._dac_y_off_pos = (c_uint16(0),c_uint16(0))
        self.dll.GetScanOffPosition(byref(self._dac_x_off_pos), byref(self._dac_y_off_pos))
        self._x_position, self._y_position = ru.dac_to_pixel(
            self._dac_x_off_pos,
            self._dac_y_off_pos,
            self._dac_x_step,
            self._dac_offset_x,
            self._dac_offset_y
            )

    def load_dll(self) : 
        if op_sys in ("win32","win64"):
            os.add_dll_directory(config('REVOLON','connection','dll_path'))
            if p.architecture()[0] == "32bit":
                scan_control_lib = cdll.LoadLibrary("DISS6Control32.dll")
            elif p.architecture()[0] == "64bit":
                scan_control_lib = cdll.LoadLibrary("DISS6Control64.dll")
        elif op_sys in ("linux","linux2"):
            scan_control_lib = cdll.LoadLibrary("libdiss6control.so")
        elif op_sys == "darwin":
            scan_control_lib = cdll.LoadLibrary("libdiss6control.dylib")
        else :
            raise FileNotFoundError('There is no dll corresponding to your OS.')
        return scan_control_lib

    def connect(self) :
        if config('REVOLON','connection','connection_type') == "USB":
            return_code = self.dll.InitUSB(None)
        elif config('REVOLON','connection','connection_type') == "LAN":
            addr_byte = bytes(config('REVOLON','connection','IP'), 'ascii')
            return_code = self.dll.InitTCP(create_string_buffer(addr_byte), 7701, 7702, 7703, 7704, 7705)
        else :
            return_code = sc.CANNOT_LOCATE_DEVICE
        if return_code != sc.SUCCESS:
            logger.info("Init failed with return code %08X!", return_code)
            msg = create_unicode_buffer(255)
            self.dll.GetLastErrorMessage(msg, 255)
            sys.exit(msg.value)
        return return_code

    def close(self) : 
        self.dll.AbortAllScans(0)
        for eh in self.event_handles:
            if eh != 0:
                self.dll.SysDestroyEvent(eh)
        return_code = self.dll.UnInit()
        if return_code == sc.SUCCESS :
            logger.info("Successfully unloaded the Revolon scan box.")
        else :
            logger.info("UnInit failed with return code %08X!",return_code)

    ############
    # Scanning #
    ############

    def wait_for_acq(self) :
        while True :
            self.dll.SysWaitForMultipleEvents(byref(self.event_handles), len(self.event_handles), False, 5000, byref(self._status))
            if self._status.value == 0 :
                pass
            if self._status.value == 1 :
                return True
            if self._status.value == 2 :
                return False
            if self._status.value == 3 :
                return False

    def start(self,
              num_frame = 0,
              x_start : int = None,
              y_start : int = None,
              x_end : int = None,
              y_end : int = None) : 
        self.prepare_acquisition(num_frame,x_start,y_start,x_end,y_end)
        return_code = self.dll.StartScanJob(self.h_scan_job, sc.ABORT_SCAN_IMMEDIATELY)
        if return_code != sc.SUCCESS: 
            sys.exit("StartScanJob failed! Error code: %08X",return_code)
    
    def read_data(self) :
        pixel_count = c_uint32(self.image_height*self.image_width)
        pixel_offset = c_uint32()
        status = c_uint32()
        return_code = self.dll.ReadChannelData(self.h_scan_job,
                                               byref(self.scan_frame_buffer_array),
                                               byref(pixel_count),
                                               sc.READ_FLAG_USE_PIXEL_OFFSET,
                                               None,
                                               byref(pixel_offset),
                                               byref(status))
        if return_code != sc.SUCCESS:
            sys.exit("ReadChannelData failed! Error code: %08X",return_code)
        data_list = self.build_data_list()
        return status, data_list
    
    def get_frame_index(self) : 
        # TODO : make a better readchanneldata function. this is quick fix, that might enter in conflict when using thecheetah3
        pixel_count = c_uint32(self.image_height*self.image_width)
        pixel_offset = c_uint32()
        frame_index = c_uint32()
        status = c_uint32()
        return_code = self.dll.ReadChannelData(self.h_scan_job,
                                               byref(self.scan_frame_buffer_array),
                                               byref(pixel_count),
                                               sc.READ_FLAG_USE_PIXEL_OFFSET,
                                               byref(frame_index),
                                               byref(pixel_offset),
                                               byref(status))
        if return_code != sc.SUCCESS:
            sys.exit("ReadChannelData failed! Error code: %08X",return_code)
        # data_list = self.build_data_list()
        return frame_index.value
    
    def build_data_list(self) :
        data_list = []
        for i, scan_frame_buffer in enumerate(self.scan_frame_buffers) :
            dtype_name = config('REVOLON','scan_profiles',self.scan_profile,'dtypes')[i]
            dtype = getattr(np,dtype_name)
            data_list.append(
                np.frombuffer(scan_frame_buffer, dtype = dtype)
            )
        return data_list

    def prepare_acquisition(self,
                            num_frame,
                            x_start,
                            y_start,
                            x_end,
                            y_end) :
        if x_start and y_start and x_end and y_end :
            assert (x_end - x_start) > 0, "There is something wrong with ROI selection"
            assert (y_end - y_start) > 0, "There is something wrong with ROI selection"
            scan_pixels = (x_end - x_start) * (y_end - y_start)
        else :
            scan_pixels = self.image_height * self.image_width

        scan_tuple = (sc.ChannelInfo_t(sc.ChannelId_t(ch, i),0,self.config.dtypes[i])
                      for i,ch in enumerate(self.config.channels))
        scan_channels = (sc.ChannelInfo_t * len(self.config.channels))(*scan_tuple)
        self.scan_frame_buffers = tuple(
            ((ru.C_TYPE_DICT[config('REVOLON',
                                    'scan_profiles',
                                    self.scan_profile,
                                    'dtypes')[i]] * scan_pixels)()
            for i,_ in enumerate(scan_channels)))
        addr_tuple = (addressof(sfb) for sfb in self.scan_frame_buffers)
        self.scan_frame_buffer_array = (c_void_p * len(scan_channels))(*addr_tuple)

        # Init job
        
        return_code = self.dll.CreateImageScanJob(len(scan_channels), byref(scan_channels), byref(self.h_scan_job))
        if return_code != sc.SUCCESS:
            sys.exit("CreateImageScanJob failed! Error code: %08X", return_code)
        # Image geometry
        if x_start and y_start and x_end and y_end :
            roi_dac_offset_x, roi_dac_offset_y = ru.pixel_to_dac(pixel_x=x_start,
                                                                 pixel_y=y_start,
                                                                 dac_offset_x=self._dac_offset_x,
                                                                 dac_offset_y=self._dac_offset_y,
                                                                 dac_increment=self._dac_x_step)
            return_code = self.dll.SetImageGeometry(self.h_scan_job,
                                                   x_end - x_start,
                                                   y_end - y_start,
                                                   roi_dac_offset_x,
                                                   roi_dac_offset_y,
                                                   self._dac_x_step,
                                                   self._dac_y_step,
                                                   self.config.flyback_line_prescan_pixels,
                                                   self.config.flyback_frame_prescan_lines)
        else :
            return_code = self.dll.SetImageGeometry(self.h_scan_job,
                                            self.image_width,
                                            self.image_height,
                                            self._dac_offset_x,
                                            self._dac_offset_y,
                                            self._dac_x_step,
                                            self._dac_y_step,
                                            self.config.flyback_line_prescan_pixels,
                                            self.config.flyback_frame_prescan_lines)
        if return_code != sc.SUCCESS:
            sys.exit("SetImageGeometry failed! Error code: %08X",return_code)

        self.dll.SetPixelClockLength(sc.TIME_SCALE_5S)
        self.dll.SetClockInvertMask(1)

        # Flyback parameters
        return_code = self.dll.SetBeamReturnTiming(self.h_scan_job,
                                            self.config.flyback_steps,
                                            self.config.flyback_line_step_time,
                                            self.config.flyback_frame_step_time)
        if return_code != sc.SUCCESS:
            sys.exit("SetBeamReturnTiming failed! Error code: %08X",return_code)

        return_code = self.dll.SetLineStartDelay(self.h_scan_job,
                                          self.config.flyback_line_start_delay)
        if return_code != sc.SUCCESS:
            sys.exit("SetLineStartDelay failed! Error code: %08X",return_code)

        # Dwell time
        return_code = self.dll.SetAcquisitionTime(self.h_scan_job, self._dwell_time_int)
        if return_code != sc.SUCCESS:
            sys.exit("SetAcquisitionTime failed! Error code: %08X",return_code)

        # Frame count
        return_code = self.dll.SetFrameCount(self.h_scan_job, num_frame)
        if return_code != sc.SUCCESS:
            sys.exit("SetFrameCount failed! Error code: %08X",return_code)

        return_code = self.dll.SetKeepInternalScanEnabled(self.h_scan_job, self._scan_switch_state)
        if return_code != sc.SUCCESS:
            sys.exit("SetKeepInternalScanEnabled failed! Error code: %08X",return_code)
        return_code = self.dll.SetLineAveragingCount(self.h_scan_job,self._line_averaging)
        if return_code != sc.SUCCESS:
            sys.exit("SetLineAveragingCount failed! Error code: %08X",return_code)

        for i in range(4):
            self.event_handles[i] = self.dll.SysCreateEvent(False, False)
        self.dll.SetEventScanJobStarted(self.h_scan_job, self.event_handles[0])
        self.dll.SetEventDataReady(self.h_scan_job, self.event_handles[1])
        self.dll.SetEventScanJobFinished(self.h_scan_job, self.event_handles[2])
        self.dll.SetEventScanJobAborted(self.h_scan_job, self.event_handles[3])

    def stop_after_frame(self) :
        return_code = self.dll.StopScanJob(self.h_scan_job, sc.ABORT_SCAN_AFTER_FRAME)
        if return_code != sc.SUCCESS:
            sys.exit("StopScanJob failed! Error code: %08X",return_code)

    def stop_immediately(self) :
        return_code = self.dll.StopScanJob(self.h_scan_job, sc.ABORT_SCAN_IMMEDIATELY)
        if return_code != sc.SUCCESS:
            sys.exit("StopScanJob failed! Error code: %08X",return_code)

    def _get_scan_gain_range(self) -> tuple[float, float, float, float]:
        min_x = c_float()
        max_x = c_float()
        _val_x = c_float()
        self.dll.GetScanGainXRange(byref(_val_x),byref(min_x),byref(max_x))
        min_y = c_float()
        max_y = c_float()
        _val_y = c_float()
        self.dll.GetScanGainYRange(byref(_val_y),byref(min_y),byref(max_y))
        return (min_x.value, max_x.value, min_y.value, max_y.value)

    ################
    # Moving probe #
    ################

    def _set_dac_x_scan_pos(self, dac_x_val : c_uint16) :
        return_code = self.dll.SetScanOffPosition(dac_x_val, self._dac_y_off_pos)
        if return_code != sc.SUCCESS:
            logger.warning("SetScanOffPosition from _set_dac_x_scan_pos failed! Error code: %08X",return_code)

    def _set_dac_y_scan_pos(self, dac_y_val : c_uint16) :
        return_code = self.dll.SetScanOffPosition(self._dac_x_off_pos, dac_y_val)
        if return_code != sc.SUCCESS:
            logger.warning("SetScanOffPosition from _set_dac_y_scan_pos failed! Error code: %08X",return_code)

    def _get_dac_scan_pos(self) -> tuple[c_uint16,c_uint16] : 
        self.dll.GetScanOffPosition(byref(self._dac_x_off_pos), byref(self._dac_y_off_pos))
        return self._dac_x_off_pos, self._dac_y_off_pos
    
    @property
    def x_position(self) -> int :
        dac_x, dac_y = self._get_dac_scan_pos()
        self._x_position, _ = ru.dac_to_pixel(dac_x=dac_x,
                               dac_y=dac_y,
                               dac_increment=self._dac_x_step,
                               dac_offset_x=self._dac_offset_x,
                               dac_offset_y=self._dac_offset_y)
        return self._x_position
    
    @x_position.setter
    def x_position(self,value : int) -> None :
        dac_x, _ = ru.pixel_to_dac(value,
                                       self._y_position,
                                       self._dac_x_step,
                                       self._dac_offset_x,
                                       self._dac_offset_y)
        self._set_dac_x_scan_pos(dac_x)

    @property
    def y_position(self) -> int :
        dac_x, dac_y = self._get_dac_scan_pos()
        _, self._y_position = ru.dac_to_pixel(dac_x=dac_x,
                               dac_y=dac_y,
                               dac_increment=self._dac_x_step,
                               dac_offset_x=self._dac_offset_x,
                               dac_offset_y=self._dac_offset_y)
        return self._y_position

    @y_position.setter
    def y_position(self,value : int) -> None :
        _, dac_y = ru.pixel_to_dac(self._x_position,
                                       value,
                                       self._dac_x_step,
                                       self._dac_offset_x,
                                       self._dac_offset_y)
        self._set_dac_y_scan_pos(dac_y)


    ##############
    # Properties #
    ##############

    @property
    def scan_switch_state(self) -> bool :
        self.dll.GetKeepInternalScanEnabled(self.h_scan_job, byref(self._scan_switch_state))
        return self._scan_switch_state.value
    
    @scan_switch_state.setter
    def scan_switch_state(self, value : bool) -> None :
        self._scan_switch_state = c_bool(value)

    @property
    def scan_gain_x(self) -> float : 
        _min = c_float()
        _max = c_float()
        self.dll.GetScanGainXRange(byref(self._scan_gain_x),byref(_min),byref(_max))
        return self._scan_gain_x.value
    
    @scan_gain_x.setter
    def scan_gain_x(self,value : float) -> None :
        min_x = c_float()
        max_x = c_float()
        c_val = c_float(value)
        self.dll.GetScanGainXRange(byref(self._scan_gain_x),byref(min_x),byref(max_x))
        if (c_val.value < max_x.value) and (c_val.value > min_x.value) :
            return_code = self.dll.SetScanGainX(c_val)
            if return_code != sc.SUCCESS:
                logger.warning("SetScanGainX failed! Error code: %08X",return_code)
            self.dll.GetScanGainXRange(byref(self._scan_gain_x),byref(min_x),byref(max_x))
        else :
            logger.info("The x scan gain can take values between %s and %s. The given x gain input is %s.", min_x.value, max_x.value, self._scan_gain_x.value)

    @property
    def scan_gain_y(self) -> float : 
        _min = c_float()
        _max = c_float()
        self.dll.GetScanGainYRange(byref(self._scan_gain_y),byref(_min),byref(_max))
        return self._scan_gain_y.value
    
    @scan_gain_y.setter
    def scan_gain_y(self,value : float) -> None :
        min_y = c_float()
        max_y = c_float()
        c_val = c_float(value)
        self.dll.GetScanGainYRange(byref(self._scan_gain_y),byref(min_y),byref(max_y))
        if (c_val.value < max_y.value) and (c_val.value > min_y.value) :
            return_code = self.dll.SetScanGainY(c_val)
            if return_code != sc.SUCCESS:
                logger.warning("SetScanGainY failed! Error code: %08X",return_code)
            self.dll.GetScanGainYRange(byref(self._scan_gain_y),byref(min_y),byref(max_y))
        else :
            logger.info("The y scan gain can take values between %s and %s. The given y gain input is %s.", min_y.value, max_y.value, self._scan_gain_y.value)

    @property
    def scan_profile(self) -> str :
        return self._scan_profile

    @scan_profile.setter
    def scan_profile(self, value : str) :
        assert value in config('Revolon','scan_profiles')("The selected profile %s isn't part of the avalaible profiles : %s",
                                                                       value,
                                                                       list(config('Revolon','scan_profiles').keys()))
        self._scan_profile = value
        self.config.load_profile(value)

    @property
    def image_width(self) :
        return self._image_width

    @image_width.setter
    def image_width(self,value : int) :
        try :
            self._dac_x_step, self._dac_offset_x, self._dac_offset_y = ru.calculate_dac_increment(
                value,
                self._image_height,
                self.config.flyback_line_prescan_pixels,
                self.config.flyback_frame_prescan_lines
                                                      )
            self._dac_y_step = self._dac_x_step
            self._image_width = value
        except AssertionError :
            logger.info("The image width in pixel could not be changed. Check dac offsets")

    @property
    def image_height(self) :
        return self._image_height

    @image_height.setter
    def image_height(self, value : int) :
        try :
            self._dac_y_step, self._dac_offset_x, self._dac_offset_y = ru.calculate_dac_increment(
                self._image_width,
                value,
                self.config.flyback_line_prescan_pixels,
                self.config.flyback_frame_prescan_lines
                                                          )
            self._dac_x_step = self._dac_y_step
            self._image_height = value
        except AssertionError : 
            print("The image height in pixel could not be changed. Check dac offsets")

    @property
    def dwell_time(self) :
        return self._dwell_time.to('us')

    @dwell_time.setter
    def dwell_time(self, value) :
        if isinstance(value,str) :
            q = Quantity(value)
        else :
            q = Quantity(value,'us')
        self._dwell_time_int = round(q.to('ns').magnitude//10)
        self._dwell_time = q
        
    @property
    def frame_count(self) -> int :
        # Not very useful. Gets the set number of frames. It is 0 for endless acquisition.
        self.dll.GetFrameCount(self.h_scan_job,byref(self._frame_count))
        return self._frame_count.value
    
    @property
    def line_averaging(self) -> int :
        c_val = c_uint16()
        self.dll.GetLineAveragingCount(self.h_scan_job,byref(c_val))
        return c_val
    
    @line_averaging.setter
    def line_averaging(self,value : int) -> None :
        try :
            assert value in [0,1,2,4,8,16,32,64,128,256]
            self._line_averaging = c_uint16(value)
        except AssertionError :
            pass

    @property
    def scan_rotation(self) -> float :
        c_val = c_float()
        self.dll.GetScanRotationAngle(byref(c_val))
        return c_val.value
    
    @scan_rotation.setter
    def scan_rotation(self, value : float) -> None :
        rot_enabled = c_bool()
        self.dll.GetScanRotationEnabled(byref(rot_enabled))
        if not rot_enabled.value : 
            self.dll.SetScanRotationEnabled(c_bool(True))
        c_val = c_float(value)
        return_code  = self.dll.SetScanRotationAngle(c_val)
        if return_code != sc.SUCCESS:
            logger.warning("SetScanRotationAngle failed! Error code: %08X",return_code)

if __name__ == '__main__' : 
    Revolon = Revolon()
    Revolon.connect()
    print(Revolon.dll.GetPixelClockLength())
    x = 256 #int(input('x ? : '))
    y = 256 # int(input('y ? : '))
    Revolon.image_height = y
    Revolon.image_width = x
    Revolon.start(100)
    time.sleep(5.0)
    # dt1 = Revolon.read_data()
