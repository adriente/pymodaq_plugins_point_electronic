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

class ScanControllerConfig :

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
        self.config = Config()
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
        # flyback parameters
        self.flyback_steps = self.config['REVOLON']['scan_profiles'][profile_name]['flyback_steps']
        self.flyback_line_step_time = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_line_step_time']
            )
        self.flyback_line_start_delay = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_line_start_delay']
            )
        self.flyback_line_prescan_pixels = self.config['REVOLON']['scan_profiles'][profile_name]['flyback_line_prescan_pixels']
        self.flyback_frame_step_time = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_frame_step_time']
            )
        self.flyback_frame_prescan_lines = self.config['REVOLON']['scan_profiles'][profile_name]['flyback_frame_prescan_lines']
        self.load_channels(profile_name)

    def load_channels(self, profile_name : str = 'basic_scan') :
        self.channels = []
        try :
            for ch in self.config['REVOLON']['scan_profiles'][profile_name]['channels'] :
                assert ch in self._acceptable_channels, f"{ch} is an invalid channel type, check ScanControllerConfig"
                self.channels.append(self._acceptable_channels[ch])
        except AssertionError : 
            ch_string = '\n'.join('{}'.format(*k) for k in self.channels)
            logger.info('Only the following channels were loaded : %s .',ch_string)

        self.dtypes = []
        try :
            for dt in self.config['REVOLON']['scan_profiles'][profile_name]['dtypes'] : 
                assert dt in self._acceptable_dtypes, f"{dt} is an invalid channel type, check ScanControllerConfig"
                self.dtypes.append(self._acceptable_dtypes[dt])
        except AssertionError : 
            ch_string = '\n'.join('{}'.format(*k) for k in self.channels)
            logger.info('Only the following channels were loaded : %s .',ch_string)

        assert len(self.channels) == len(self.dtypes), f"dtypes and channels don't match.\nChannels : {self.channels}, Dtypes : {self.dtypes}"


class ScanController :
    def __init__(self) :
        self.config = ScanControllerConfig()
        self.dll = self.load_dll()
        self._scan_profile = 'basic_scan'
        self.config.load_profile(self.scan_profile)
        # Properties
        self._image_width = 1024 # pixels
        self._image_height = 1024 # pixels
        self._dwell_time = Quantity('10000 ns') #ns/pixel units, must be multiple of 10
        self._dwell_time_int = self._dwell_time.magnitude // 10
        self._status = c_uint32(0)
        self.full = 0
        # self.thread_called = 0

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
            os.add_dll_directory(self.config.config['REVOLON']['connection']['dll_path'])
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
        if self.config.config['REVOLON']['connection']['connection_type'] == "USB":
            return_code = self.dll.InitUSB(None)
        elif self.config.config['REVOLON']['connection']['connection_type'] == "LAN":
            addr_byte = bytes(self.config.config['REVOLON']['connection']['IP'], 'ascii') 
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
    
    def build_data_list(self) : 
        data_list = []
        for i, scan_frame_buffer in enumerate(self.scan_frame_buffers) :
            dtype_name = self.config.config['REVOLON']['scan_profiles'][self.scan_profile]['dtypes'][i]
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

        scan_tuple = (sc.ChannelInfo_t(sc.ChannelId_t(ch, i),0,self.config.dtypes[i]) for i,ch in enumerate(self.config.channels))
        scan_channels = (sc.ChannelInfo_t * len(self.config.channels))(*scan_tuple)
        self.scan_frame_buffers = tuple(((c_uint16 * scan_pixels)() for _ in scan_channels))
        addr_tuple = (addressof(sfb) for sfb in self.scan_frame_buffers) 
        self.scan_frame_buffer_array = (c_void_p * len(scan_channels))(*addr_tuple)

        # Init job
        self.h_scan_job = c_uint16(0)
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

        self.dll.SetKeepInternalScanEnabled(self.h_scan_job, True)

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

    ################
    # Moving probe #
    ################

    def _set_dac_x_scan_pos(self, dac_x_val : c_uint16) :
        self.dll.SetScanOffPosition(dac_x_val, self._dac_y_off_pos)

    def _set_dac_y_scan_pos(self, dac_y_val : c_uint16) :
        self.dll.SetScanOffPosition(self._dac_x_off_pos, dac_y_val)

    def _get_dac_scan_pos(self) : 
        self.dll.GetScanOffPosition(byref(self._dac_x_off_pos), byref(self._dac_y_off_pos))
        return self._dac_x_off_pos, self._dac_y_off_pos
    
    @property
    def x_position(self) :
        dac_x, dac_y = self._get_dac_scan_pos() 
        self._x_positon, _ = ru.dac_to_pixel(dac_x=dac_x,
                               dac_y=dac_y,
                               dac_increment=self._dac_x_step,
                               dac_offset_x=self._dac_offset_x,
                               dac_offset_y=self._dac_offset_y)
        return self._x_positon
    
    @x_position.setter
    def x_position(self,value : int) : 
        dac_x, _ = ru.pixel_to_dac(value,
                                       self._y_position,
                                       self._dac_x_step,
                                       self._dac_offset_x,
                                       self._dac_offset_y)
        self._set_dac_x_scan_pos(dac_x)

    @property
    def y_position(self) :
        dac_x, dac_y = self._get_dac_scan_pos() 
        _, self._y_position = ru.dac_to_pixel(dac_x=dac_x,
                               dac_y=dac_y,
                               dac_increment=self._dac_x_step,
                               dac_offset_x=self._dac_offset_x,
                               dac_offset_y=self._dac_offset_y)
        return self._y_position

    @y_position.setter
    def y_position(self,value : int) : 
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
    def scan_profile(self) -> str :
        return self._scan_profile

    @scan_profile.setter
    def scan_profile(self, value : str) :
        assert value in self.config.config['Revolon']['scan_profiles']("The selected profile %s isn't part of the avalaible profiles : %s",
                                                                       value,
                                                                       list(self.config.config['Revolon']['scan_profiles'].keys()))
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
        return self._dwell_time.to('ns')

    @dwell_time.setter
    def dwell_time(self, value) : 
        ns_value = value.to('ns').magnitude
        self._dwell_time_int = ns_value//10
        self._dwell_time = value.to('ns')

if __name__ == '__main__' : 
    Revolon = ScanController()
    Revolon.connect()
    x = int(input('x ? : '))
    y = int(input('y ? : '))
    Revolon.image_height = y
    Revolon.image_width = x
    Revolon.start(1)
    time.sleep(5.0)
    dt1 = Revolon.read_data()
