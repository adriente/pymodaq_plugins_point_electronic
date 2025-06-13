import ctypes

class PixelComponent_t(ctypes.Structure):
	_pack_ = 1
	_fields_ = [("Position", ctypes.c_uint16), ("Flags", ctypes.c_uint16)]

class Pixel_t(ctypes.Structure):
	_pack_ = 1
	_fields_ = [("X", PixelComponent_t), ("Y", PixelComponent_t)]
      
#Return codes for all library functions
SUCCESS                                = 0x0000000
NOT_INITIALIZED                        = 0x0000001
ALREADY_INITIALIZED                    = 0x0000002
CANNOT_LOCATE_DEVICE                    = 0x0000003
OPENING_USBCONNECTION_FAILED            = 0x0000004
CREATING_SUP_CONNECTION_FAILED            = 0x0000005
SUP_READ_FAILED                        = 0x0000006
SUP_WRITE_FAILED                        = 0x0000007
UDP_SEND_FAILED                        = 0x0000008
UDP_RECEIVE_FAILED                        = 0x0000009
UDP_LOCATOR_SECRET_MISMATCH            = 0x000000A
INVALID_IP_ADDRESS                        = 0x000000B
TCP_SEND_FAILED                        = 0x000000C
TCP_NOT_CONNECTED                        = 0x000000D
TCP_RECEIVE_FAILED                        = 0x000000E
TCP_PORT_ALREADY_IN_USE                = 0x000000F
INVALID_MICS_CARD_INDEX                = 0x0000010
INVALID_MICS_CARD_ADDRESS                = 0x0000011
INVALID_DISS_CARD_INDEX                = 0x0000012
INVALID_MICS_CHANNEL_INDEX                = 0x0000013
OPERATION_FAILED                        = 0x0000014
TIMEOUT_OCCURRED                        = 0x0000015
SEND_TIMEOUT_OCCURRED                    = 0x0000016
NULLPTR_PARAM_GIVEN                    = 0x0000017
INVALID_PARAM_GIVEN                    = 0x0000018
INVALID_PARAMETER_INDEX                = 0x0000019
CREATING_DEVICE_FAILED                    = 0x000001A
CREATING_DIIP_CONNECTION_FAILED        = 0x000001B
CREATING_DSCPMAILER_FAILED                = 0x000001C
CREATING_DSCP_SENDER_FAILED            = 0x000001D
CREATING_SCANDATARECEIVER_FAILED        = 0x000001E
CREATING_SCANDATADRIVER_FAILED            = 0x000001F
STARTING_SCAN_THREAD_FAILED            = 0x0000020
SCAN_THREAD_STALLED                    = 0x0000021
EVENT_THREAD_STALLED                    = 0x0000022
CREATING_SCANJOBHANDLER_FAILED            = 0x0000023
STARTING_EVENT_THREAD_FAILED            = 0x0000024
CREATING_SCANJOBEVENTDRIVER_FAILED        = 0x0000025
INVALID_EVENT_HANDLE                    = 0x0000026
CREATING_VIDEODATARECEIVER_FAILED        = 0x0000027
STARTING_VIDEO_DRIVER_FAILED            = 0x0000028
VIDEO_THREAD_STALLED                    = 0x0000029
VIDEO_CHANNEL_IN_USE                    = 0x000002A
NO_D6HW_CHANNEL                        = 0x000002B
NO_CHANNEL_SELECTED                    = 0x000002C
TOO_MANY_CHANNELS_SELECTED                = 0x000002D
UNSUPPORTED_CHANNEL_COMBINATION        = 0x000002E
INCONSISTENT_COUNTER_CASCADING            = 0x000002F
INCONSISTENT_GEOMETRY                    = 0x0000030
INVALID_CHANNEL_ID                        = 0x0000031
INVALID_SCAN_ID                        = 0x0000032
INVALID_SCAN_JOB_TYPE                    = 0x0000033
INVALID_RESOLUTION                        = 0x0000034
SCAN_JOB_GONE_AWAY                        = 0x0000035
SCAN_JOB_INEXISTENT                    = 0x0000036
SCAN_JOB_ABANDONED                        = 0x0000037
SCAN_JOB_REJECTED                        = 0x0000038
SCAN_JOB_TRANSMISSION_FAILED            = 0x0000039
SCAN_JOB_NOT_IN_PREPARED_STATE            = 0x000003A
INVALID_SUP_CARD_INDEX                    = 0x000003B
INVALID_SUP_CARDCFG_SIZE                 = 0x000003C
SUP_READ_SIZE_MISMATCH                    = 0x000003D
INVALID_SUP_PARAMETER_INDEX            = 0x000003E
INVALID_SUP_PARAMETER_COUNT            = 0x000003F


# scan job abort codes
ABORT_SCAN_NONE                        = 0
ABORT_SCAN_AFTER_FRAME                = 1
ABORT_SCAN_IMMEDIATELY                = 3

# scan mode
SCAN_MODE_NORMAL                    = 0
SCAN_MODE_CHOPPED                    = 1
SCAN_MODE_WOBBLE_A                    = 2
SCAN_MODE_WOBBLE_B                    = 3
SCAN_MODE_SUBPIXEL                    = 4
SCAN_MODE_SUBPIXEL_REVOLVING        = 5

# time scale
TIME_SCALE_NONE                        = 0
TIME_SCALE_10NS                        = 1
TIME_SCALE_20NS                        = 2
TIME_SCALE_50NS                        = 3
TIME_SCALE_100NS                    = 4
TIME_SCALE_200NS                    = 5
TIME_SCALE_500NS                    = 6
TIME_SCALE_1US                        = 7
TIME_SCALE_2US                        = 8
TIME_SCALE_5US                        = 9
TIME_SCALE_10US                        = 10
TIME_SCALE_20US                        = 11
TIME_SCALE_50US                        = 12
TIME_SCALE_100US                    = 13
TIME_SCALE_200US                    = 14
TIME_SCALE_500US                    = 15
TIME_SCALE_1MS                        = 16
TIME_SCALE_2MS                        = 17
TIME_SCALE_5MS                        = 18
TIME_SCALE_10MS                        = 19
TIME_SCALE_20MS                        = 20
TIME_SCALE_50MS                        = 21
TIME_SCALE_100MS                    = 22
TIME_SCALE_200MS                    = 23
TIME_SCALE_500MS                    = 24
TIME_SCALE_1S                        = 25
TIME_SCALE_2S                        = 26
TIME_SCALE_5S                        = 27
TIME_SCALE_10S                        = 28

# channel source
CHANNEL_SOURCE_NONE                    = 0
CHANNEL_SOURCE_A_FAST_A                = 1
CHANNEL_SOURCE_A_FAST_B                = 2
CHANNEL_SOURCE_A_SLOW                = 3
CHANNEL_SOURCE_A_LIA                = 4
CHANNEL_SOURCE_COUNTER                = 5
CHANNEL_SOURCE_ECL_COUNTER            = 6

# channel selection SLOW/MICS
CHANNEL_SEL_SLOW_DIRECT                = 0
# SUM selection, only for MICS (optional)
CHANNEL_SEL_SLOW_SUM                = 1
# MIX selection, only with MICS (optional)
CHANNEL_SEL_SLOW_MIX                = 2
# AUX selection, only with MICS (optional)
CHANNEL_SEL_SLOW_AUX                = 3

# channel data type
CHANNEL_DATATYPE_INVALID            = 0
# 8 bit data, cannnot be mixed with other data types
CHANNEL_DATATYPE_U8                    = 1
# 16 bit data (default), cannnot be mixed with 8 bit data
CHANNEL_DATATYPE_U16                = 2
# 32 bit daten, only for counter channels (two 16 bit counter channels will be cascaded)
CHANNEL_DATATYPE_U32                = 3

# channel id/info structure
class ChannelId_t(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("source", ctypes.c_uint8),
                ("index", ctypes.c_uint8)]
    
class ChannelInfo_t(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("id", ChannelId_t),
                ("selection", ctypes.c_uint8),
                ("datatype", ctypes.c_uint8)]

# flags/status for ReadChannelData
READ_FLAG_USE_PIXEL_OFFSET            = 0x00000001

READ_STATUS_NONE                    = 0x00000000
READ_STATUS_BUFFER_EMPTY            = 0x00000001
READ_STATUS_BUFFER_OVERFLOW            = 0x00000002
READ_STATUS_OFFSET_MISMATCH            = 0x00000004
READ_STATUS_FRAME_END                = 0x00000010
READ_STATUS_USB_ERROR                = 0x80000000
READ_STATUS_DATA_LOSS                = (READ_STATUS_BUFFER_OVERFLOW | READ_STATUS_OFFSET_MISMATCH)

# LIA clock mode
LIA_CLOCKMODE_REFERENCE             = 0
LIA_CLOCKMODE_PIXEL                 = 1
LIA_CLOCKMODE_LINE                     = 2
LIA_CLOCKMODE_FRAME                 = 3

# scan job state
SCAN_JOB_STATE_INEXISTENT            = 0
SCAN_JOB_STATE_PREPARED                = 1
SCAN_JOB_STATE_TRANSMISSION_STARTED    = 2
SCAN_JOB_STATE_IN_TRANSMISSION        = 3
SCAN_JOB_STATE_TRANSMISSION_FAILED    = 4
SCAN_JOB_STATE_SENT                    = 5
SCAN_JOB_STATE_RUNNING                = 6
SCAN_JOB_STATE_REJECTED                = 7
SCAN_JOB_STATE_FINISHED                = 8
SCAN_JOB_STATE_ABANDONED            = 9

# DVI mode
DVI_MODE_DVI                        = 0
DVI_MODE_HDMI                        = 1

# DVI resolution
DVI_RESOLUTION_640X480                = 0
DVI_RESOLUTION_800X600                = 1
DVI_RESOLUTION_1024X768                = 2
DVI_RESOLUTION_1280X720                = 3
DVI_RESOLUTION_1360X768                = 4
DVI_RESOLUTION_1600X900                = 5
DVI_RESOLUTION_1920X1080            = 6
DVI_RESOLUTION_1920X1200            = 7

