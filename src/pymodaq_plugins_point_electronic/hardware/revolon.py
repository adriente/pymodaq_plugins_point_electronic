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

import time

class ScanControllerConfig :

    _acceptable_channels = {'none' : sc.CHANNEL_SOURCE_NONE,
                            'a_fast_a' : sc.CHANNEL_SOURCE_A_FAST_A,
                            'a_fast_b' : sc.CHANNEL_SOURCE_A_FAST_B,
                            'a_slow' : sc.CHANNEL_SOURCE_A_SLOW,
                            'a_lia' : sc.CHANNEL_SOURCE_A_LIA,
                            'counter' : sc.CHANNEL_SOURCE_COUNTER,
                            'ecl_counter' : sc.CHANNEL_SOURCE_ECL_COUNTER}
    _acceptable_dtypes = {'invalid' : sc.CHANNEL_DATATYPE_INVALID,
                          'u8' : sc.CHANNEL_DATATYPE_U8,
                          'u16' : sc.CHANNEL_DATATYPE_U16,
                          'u32' : sc.CHANNEL_DATATYPE_U32}

    def __init__(self):
        self.config = Config()
        self.time_scale_converter = ru.TimeScaleConverter()

    def load_profile(self, profile_name : str = 'basic_scan') : 
        # flyback parameters
        self.flyback_steps = self.config['REVOLON'][profile_name]['flyback_steps']
        self.flyback_line_step_time = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_line_step_time']
            )
        self.flyback_line_start_delay = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_line_start_delay']
            )
        self.flyback_line_prescan_pixels = self.config['REVOLON'][profile_name]['flyback_line_prescan_pixels']
        self.flyback_frame_step_time = self.time_scale_converter.from_quantity_to_int(
            self.config['REVOLON'][profile_name]['flyback_frame_step_time']
            )
        self.flyback_frame_prescan_lines = self.config['REVOLON'][profile_name]['flyback_frame_prescan_lines']
        self.load_channels(profile_name)

    def load_channels(self, profile_name : str = 'basic_scan') :
        self.channels = [] 
        try : 
            for ch in self.config['REVOLON'][profile_name]['channels'] :
                assert ch in self._acceptable_channels.keys(), f"{ch} is an invalid channel type, check ScanControllerConfig"
                self.channels.append(self._acceptable_channels[ch])
        except AssertionError : 
            print('Only the following channels were loaded : \n')
            print('\n'.join('{}'.format(*k) for k in self.channels))

        self.dtypes = []
        try : 
            for dt in self.config['REVOLON'][profile_name]['dtypes'] : 
                assert dt in self._acceptable_dtypes.keys(), f"{dt} is an invalid channel type, check ScanControllerConfig"
                self.dtypes.append(self._acceptable_dtypes[dt])
        except AssertionError : 
            print('Only the following channels were loaded : \n')
            print('\n'.join('{}'.format(*k) for k in self.channels))

        assert len(self.channels) == len(self.dtypes), f"dtypes and channels don't match.\nChannels : {self.channels}, Dtypes : {self.dtypes}"


class  ScanController : 
    def __init__(self) : 
        self.config = ScanControllerConfig()
        self.dll = self.load_dll()
        
        self.config.load_profile('basic_scan')
        # Properties
        self._image_width = 1024 # pixels
        self._image_height = 1024 # pixels
        self._dwell_time = Quantity('10000 ns') #ns/pixel units, must be multiple of 10
        self._dwell_time_int = self._dwell_time.magnitude // 10
        self._status = c_uint32(0)
        self.full = 0
        # self.thread_called = 0

        # Advanced settings
        self._DAC_x_step, self._DAC_offset_x, self._DAC_offset_y = ru.calculate_DAC_increment(
            self._image_width,
            self._image_height,
            self.config.flyback_line_prescan_pixels,
            self.config.flyback_frame_prescan_lines
                                                      )
        self._DAC_y_step = self._DAC_x_step
        
        self.eventHandles = (c_void_p * 4)()

        self._DAC_x_off_pos, self._DAC_y_off_pos = (c_uint16(0),c_uint16(0))
        self.dll.GetScanOffPosition(byref(self._DAC_x_off_pos), byref(self._DAC_y_off_pos))
        self._x_position, self._y_position = ru.DAC_to_pixel(
            self._DAC_x_off_pos,
            self._DAC_y_off_pos,
            self._DAC_x_step,
            self._DAC_offset_x,
            self._DAC_offset_y
            )


    def load_dll(self) : 
        if op_sys == "win32" or  op_sys == "win64":
            os.add_dll_directory(self.config.config['REVOLON']['connection']['dll_path'])
            if p.architecture()[0] == "32bit":
                scan_control_lib = cdll.LoadLibrary("DISS6Control32.dll")
            elif p.architecture()[0] == "64bit":
                scan_control_lib = cdll.LoadLibrary("DISS6Control64.dll")
        elif op_sys == "linux" or op_sys == "linux2":
            scan_control_lib = cdll.LoadLibrary("libdiss6control.so")
        elif op_sys == "darwin":
            scan_control_lib = cdll.LoadLibrary("libdiss6control.dylib")
        else : 
            raise FileNotFoundError('There is no dll corresponding to your OS.')
        return scan_control_lib

    def connect(self) :
        if self.config.config['REVOLON']['connection']['connection_type'] == "USB": 
            returnCode = self.dll.InitUSB(None)
        if self.config.config['REVOLON']['connection']['connection_type'] == "LAN":
            addr_byte = bytes(self.config.config['REVOLON']['connection']['IP'], 'ascii') 
            returnCode = self.dll.InitTCP(create_string_buffer(addr_byte), 7701, 7702, 7703, 7704, 7705)
        if returnCode != sc.SUCCESS:
            print(f"Init failed (return code {returnCode:08X})!")
            msg = create_unicode_buffer(255)
            self.dll.GetLastErrorMessage(msg, 255)
            exit(msg.value)
        return returnCode

    def close(self) : 
        self.dll.AbortAllScans(0)
        returnCode = self.dll.UnInit()
        if returnCode == sc.SUCCESS : 
            print("Successfully unloaded the Revolon scan box.")
        else : 
            print("Something went wrong when unloading the Revolon scan box.")
            print(f"UnInit failed (return code {returnCode:08X})!")

    ############
    # Scanning #
    ############

    def wait_for_acq(self) :
        while 1 : 
            ret = self.dll.SysWaitForMultipleEvents(byref(self.eventHandles), len(self.eventHandles), False, 5000, byref(self._status)) 
            if self._status.value == 0 :
                pass
            if self._status.value == 1 : 
                return True
            if self._status.value == 2 :
                return False
            
    # def wait_for_acq(self) :
    #     while 1 : 
    #         ret = self.dll.SysWaitForMultipleEvents(byref(self.eventHandles), len(self.eventHandles), False, 5000, byref(self._status)) 
    #         if self._status.value == 0 :
    #             pass
    #         if self._status.value == 1 : 
    #             return 1
    #         if self._status.value == 2 and not(self.full) :
    #             return 2
            
    # def update_status(self) : 
    #     ret = self.dll.SysWaitForMultipleEvents(byref(self.eventHandles), len(self.eventHandles), False, 5000, byref(self._status))
    #     return self._status.value

    def start(self,
              num_frame = 0,
              x_start : int = None,
              y_start : int = None,
              x_end : int = None,
              y_end : int = None) : 
        self.prepare_acquisition(num_frame,x_start,y_start,x_end,y_end)
        # self.pixelCount = c_uint32(self.image_height * self.image_height)
        # self.pixelOffset = c_uint32()
        # self.data_status = c_uint32()
        # self.t = Thread(target=self.acquired_data)
        # Start acquisition
        returnCode = self.dll.StartScanJob(self.hScanJob, sc.ABORT_SCAN_IMMEDIATELY)
        if returnCode != sc.SUCCESS: exit(f"StartScanJob failed! Error code: {returnCode:08X}")
        # t = Thread(target=self.wait_for_acq)
        # t.start()
        # pixelCount = c_uint32(self.image_height*self.image_width)
        # pixelOffset = c_uint32()
        # status = c_uint32()
        # returnCode = sc.ReadChannelData(self.hScanJob,
        #                                 byref(self.scanFrameBufferArray),
        #                                 byref(pixelCount),
        #                                 sc.READ_FLAG_USE_PIXEL_OFFSET,
        #                                 None,
        #                                 byref(pixelOffset),
        #                                 byref(status))
        # if returnCode != sc.SUCCESS: exit(f"ReadChannelData failed! Error code: {returnCode:08X}")

    # def async_acquired_data(self) :
    #     if self.full and not(self.thread_called) :
    #         t = Thread(target=self.acquired_data)
    #         t.start()
    #         self.thread_called = 1
    #         print('I am called in')

    #     print('I am called')
    #     return self.data
        

    def acquired_data(self) :
        pixelCount = c_uint32(self.image_height*self.image_width)
        pixelOffset = c_uint32()
        status = c_uint32() 
        returnCode = self.dll.ReadChannelData(self.hScanJob, byref(self.scanFrameBufferArray), byref(pixelCount), sc.READ_FLAG_USE_PIXEL_OFFSET, None, byref(pixelOffset), byref(status))
        if returnCode != sc.SUCCESS: exit(f"ReadChannelData failed! Error code: {returnCode:08X}")
        # time.sleep(0.01)
        # check status
        # print("Read ", pixelCount.value, " at offset ", pixelOffset.value)
        # print(f'box status {self._status}')
        # print(f'data status {self.data_status}')
        # print(self.data.sum())
        # if (status.value == sc.READ_STATUS_DATA_LOSS):
        #     print("Data loss!") 
    
        # if (status.value == sc.READ_STATUS_BUFFER_EMPTY):
        #     break
                # print("Empty buffer")
        
        return status, pixelCount, pixelOffset, np.frombuffer(self.scanFrameBuffer, dtype=np.uint16)
    
    # def acquired_data(self) :
    #     pixelCount = c_uint32(self.image_height*self.image_width)
    #     pixelOffset = c_uint32()
    #     status = c_uint32()
    #     returnCode = self.dll.ReadChannelData(self.hScanJob, byref(self.scanFrameBufferArray), byref(pixelCount), sc.READ_FLAG_USE_PIXEL_OFFSET, None, byref(pixelOffset), byref(status))
    #     if returnCode != sc.SUCCESS: exit(f"ReadChannelData failed! Error code: {returnCode:08X}")
    #     # time.sleep(0.01)
    #     # check status
    #     # print("Read ", pixelCount.value, " at offset ", pixelOffset.value)
    #     # print(f'box status {self._status}')
    #     # print(f'data status {self.data_status}')
    #     # print(self.data.sum())
    #     if (status.value == sc.READ_STATUS_DATA_LOSS):
    #         print("Data loss!") 

    #     if (status.value == sc.READ_STATUS_BUFFER_EMPTY):
    #         self.full = 0
    #         # print("Empty buffer")
        
    #     return pixelCount, pixelOffset, np.frombuffer(self.scan

    def prepare_acquisition(self,
                            num_frame,
                            x_start,
                            y_start,
                            x_end,
                            y_end) : 
        if x_start and y_start and x_end and y_end :
            assert (x_end - x_start) > 0, "There is something wrong with ROI selection"
            assert (y_end - y_start) > 0, "There is something wrong with ROI selection" 
            scanPixels = (x_end - x_start) * (y_end - y_start)
        else :
            scanPixels = self.image_height * self.image_width

        scan_tuple = (sc.ChannelInfo_t(sc.ChannelId_t(ch, 0),0,self.config.dtypes[i]) for i,ch in enumerate(self.config.channels))
        scanChannels = (sc.ChannelInfo_t * len(self.config.channels))(*scan_tuple)
        self.scanFrameBuffer = (c_uint16 * scanPixels)()
        self.scanFrameBufferArray = (c_void_p * 1)(addressof(self.scanFrameBuffer))

        # Init job
        self.hScanJob = c_uint16(0)
        returnCode = self.dll.CreateImageScanJob(len(scanChannels), byref(scanChannels), byref(self.hScanJob))
        if returnCode != sc.SUCCESS: exit(f"CreateImageScanJob failed! Error code: {returnCode:08X}")
        # Image geometry
        if x_start and y_start and x_end and y_end :
            roi_DAC_offset_x, roi_DAC_offset_y = ru.pixel_to_DAC(pixel_x=x_start,
                                                                 pixel_y=y_start,
                                                                 DAC_offset_x=self._DAC_offset_x,
                                                                 DAC_offset_y=self._DAC_offset_y,
                                                                 DAC_increment=self._DAC_x_step)
            returnCode = self.dll.SetImageGeometry(self.hScanJob,
                                                   x_end - x_start,
                                                   y_end - y_start,
                                                   roi_DAC_offset_x,
                                                   roi_DAC_offset_y,
                                                   self._DAC_x_step,
                                                   self._DAC_y_step,
                                                   self.config.flyback_line_prescan_pixels,
                                                   self.config.flyback_frame_prescan_lines)
        else :
            returnCode = self.dll.SetImageGeometry(self.hScanJob,
                                            self.image_width,
                                            self.image_height,
                                            self._DAC_offset_x,
                                            self._DAC_offset_y,
                                            self._DAC_x_step,
                                            self._DAC_y_step,
                                            self.config.flyback_line_prescan_pixels,
                                            self.config.flyback_frame_prescan_lines)
        if returnCode != sc.SUCCESS: exit(f"SetImageGeometry failed! Error code: {returnCode:08X}")

        # Flyback parameters
        returnCode = self.dll.SetBeamReturnTiming(self.hScanJob,
                                            self.config.flyback_steps,
                                            self.config.flyback_line_step_time,
                                            self.config.flyback_frame_step_time)
        if returnCode != sc.SUCCESS: exit(f"SetBeamReturnTiming failed! Error code: {returnCode:08X}")

        returnCode = self.dll.SetLineStartDelay(self.hScanJob,
                                          self.config.flyback_line_start_delay)
        if returnCode != sc.SUCCESS: exit(f"SetLineStartDelay failed! Error code: {returnCode:08X}")

        # Dwell time
        returnCode = self.dll.SetAcquisitionTime(self.hScanJob, self._dwell_time_int)
        if returnCode != sc.SUCCESS: exit(f"SetAcquisitionTime failed! Error code: {returnCode:08X}")

        # Frame count
        returnCode = self.dll.SetFrameCount(self.hScanJob, num_frame)
        if returnCode != sc.SUCCESS: exit(f"SetFrameCount failed! Error code: {returnCode:08X}")

        self.dll.SetKeepInternalScanEnabled(self.hScanJob, True)

        for i in range(4):
            self.eventHandles[i] = self.dll.SysCreateEvent(False, False)
        self.dll.SetEventScanJobStarted(self.hScanJob, self.eventHandles[0]);
        self.dll.SetEventDataReady(self.hScanJob, self.eventHandles[1]);
        self.dll.SetEventScanJobFinished(self.hScanJob, self.eventHandles[2]);
        self.dll.SetEventScanJobAborted(self.hScanJob, self.eventHandles[3]);

    def stop_after_frame(self) : 
        returnCode = self.dll.StopScanJob(self.hScanJob, sc.ABORT_SCAN_AFTER_FRAME)
        if returnCode != sc.SUCCESS: exit(f"StopScanJob failed! Error code: {returnCode:08X}")

    def stop_immediately(self) : 
        returnCode = self.dll.StopScanJob(self.hScanJob, sc.ABORT_SCAN_IMMEDIATELY)
        if returnCode != sc.SUCCESS: exit(f"StopScanJob failed! Error code: {returnCode:08X}")

    ################
    # Moving probe #
    ################

    def _set_DAC_x_scan_pos(self, DAC_x_val : c_uint16) :
        self.dll.SetScanOffPosition(DAC_x_val, self._DAC_y_off_pos)

    def _set_DAC_y_scan_pos(self, DAC_y_val : c_uint16) : 
        self.dll.SetScanOffPosition(self._DAC_x_off_pos, DAC_y_val)

    def _get_DAC_scan_pos(self) : 
        self.dll.GetScanOffPosition(byref(self._DAC_x_off_pos), byref(self._DAC_y_off_pos))
        return self._DAC_x_off_pos, self._DAC_y_off_pos
    
    @property
    def x_position(self) :
        DAC_x, DAC_y = self._get_DAC_scan_pos() 
        self._x_positon, y = ru.DAC_to_pixel(DAC_x=DAC_x,
                               DAC_y=DAC_y,
                               DAC_increment=self._DAC_x_step,
                               DAC_offset_x=self._DAC_offset_x,
                               DAC_offset_y=self._DAC_offset_y)
        return self._x_positon
    
    @x_position.setter
    def x_position(self,value : int) : 
        DAC_x, DAC_y = ru.pixel_to_DAC(value,
                                       self._y_position,
                                       self._DAC_x_step,
                                       self._DAC_offset_x,
                                       self._DAC_offset_y)
        self._set_DAC_x_scan_pos(DAC_x)

    @property
    def y_position(self) :
        DAC_x, DAC_y = self._get_DAC_scan_pos() 
        x, self._y_position = ru.DAC_to_pixel(DAC_x=DAC_x,
                               DAC_y=DAC_y,
                               DAC_increment=self._DAC_x_step,
                               DAC_offset_x=self._DAC_offset_x,
                               DAC_offset_y=self._DAC_offset_y)
        return self._y_position

    @y_position.setter
    def y_position(self,value : int) : 
        DAC_x, DAC_y = ru.pixel_to_DAC(self._x_position,
                                       value,
                                       self._DAC_x_step,
                                       self._DAC_offset_x,
                                       self._DAC_offset_y)
        self._set_DAC_y_scan_pos(DAC_y)


    ##############
    # Properties #
    ##############

    @property
    def image_width(self) : 
        return self._image_width
    
    @image_width.setter
    def image_width(self,value : int) : 
        try : 
            self._DAC_x_step, self._DAC_offset_x, self._DAC_offset_y = ru.calculate_DAC_increment(
                value,
                self._image_height,
                self.config.flyback_line_prescan_pixels,
                self.config.flyback_frame_prescan_lines
                                                      )
            self._DAC_y_step = self._DAC_x_step
            self._image_width = value
        except AssertionError : 
            print("The image width in pixel could not be changed. Check DAC offsets")

    @property
    def image_height(self) : 
        return self._image_height
    
    @image_height.setter
    def image_height(self, value : int) :
        try :
            self._DAC_y_step, self._DAC_offset_x, self._DAC_offset_y = ru.calculate_DAC_increment(
                self._image_width,
                value,
                self.config.flyback_line_prescan_pixels,
                self.config.flyback_frame_prescan_lines
                                                          )
            self._DAC_x_step = self._DAC_y_step
            self._image_height = value
        except AssertionError : 
            print("The image height in pixel could not be changed. Check DAC offsets")

    @property
    def dwell_time(self) : 
        return self._dwell_time.to('ns')
    
    @dwell_time.setter
    def dwell_time(self, value) : 
        ns_value = value.to('ns').magnitude
        self._dwell_time_int = ns_value//10
        self._dwell_time = value.to('ns')

    # @property
    # def status(self) : 
    #     return self._status.value

    #####
    # 

if __name__ == '__main__' : 
    Revolon = ScanController()
    Revolon.connect()
    # scan_tuple = (sc.ChannelInfo_t(sc.ChannelId_t(1, 0),0,2),)
    # scanChannels = (sc.ChannelInfo_t * len([1]))(*scan_tuple)
    # hScanJob = c_uint16(0)
    # returnCode1 = Revolon.dll.CreateImageScanJob(len(scanChannels), byref(scanChannels), byref(hScanJob))
    # if returnCode1 != sc.SUCCESS: exit(f"CreateImageScanJob failed! Error code: {returnCode1:08X}")
    # x = int(input('x ? : '))
    # y = int(input('y ? : '))
    # off_x = int(input('off x ? : '))
    # off_y = int(input('off_y ? : '))
    # stp_x = int(input('stp x ? : '))
    # stp_y = int(input('off y ? : '))
    # fpx = int(input('fpx ? : '))
    # fpl = int(input('fpl ? : '))
    # returnCode = Revolon.dll.SetImageGeometry(hScanJob,
    #                                      x,
    #                                      y,
    #                                      off_x,
    #                                      off_y,
    #                                      stp_x,
    #                                      stp_y,
    #                                      fpx,
    #                                      fpl)
    # if returnCode != sc.SUCCESS: exit(f"SetImageGeometry failed! Error code: {returnCode:08X}")
    # print(f"SetImageGeometry failed! Error code: {returnCode:08X}")


    x = int(input('x ? : '))
    y = int(input('y ? : '))
    Revolon.image_height = y
    Revolon.image_width = x
    Revolon.start(1)
    time.sleep(5.0)
    dt1 = Revolon.acquired_data()
   
            
    # print('Stopping')
    # Revolon.stop_immediately()
