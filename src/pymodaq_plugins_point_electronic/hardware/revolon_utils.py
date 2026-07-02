from pint import Quantity
from pint import UnitRegistry
from ctypes import *
# Returns in dac units the step size in x or y direction for a scan.
# It is mainly based on the number of pixels in the image

C_TYPE_DICT = {
    'uint8' : c_uint8,
    'uint16' : c_uint16,
    'uint32' : c_uint32
}

def from_roi_info_to_int_coordinates(roi_info) : 
    x_origin, y_origin = roi_info.origin
    size_x, size_y = roi_info.size
    x_origin, y_origin, size_x, size_y = round(x_origin), round(y_origin), round(size_x), round(size_y)
    x_end = x_origin + size_x
    y_end = y_origin + size_y
    return x_origin, y_origin, x_end, y_end


def calculate_dac_increment(pixel_length_x : int,
                            pixel_length_y : int,
                            prescan_x : int,
                            prescan_y : int,
                            dac_max_value: int = 65535) :
    r"""
    Returns the dac increment value as well as the corresponding dac offsets for a sawtooth scan. 
    This functions accounts for prescan (flyback) pixels.
    If given a non-square image, it will maximize the number of pixels in the direction with the highest number of pixels.

    Parameters
    ----------
    pixel_length_x : int
        Number of pixels of the image in the x direction (fast scan)
    pixel_length_y : int
        Number of pixels of the image in the y direction (slow scan)
    prescan_x : int
        Number of pixels in the line flyback
    prescan_y : int
        Number of pixels in the frame (to be checked) flyback
    dac_max_value : int
        Maximum value of the dac. By default 16 bits.

    Returns
    -------
    dac_increment : int
        Value of the increment per pixel in dac unit
    dac_x_offset : int
        Value of the line offset in dac unit
    dac_y_offset : int
        Value of the frame offset in dac unit
    """
    
    if pixel_length_y >= pixel_length_x : 
        dac_increment = min(dac_max_value // (pixel_length_y + 2*prescan_x),
                            dac_max_value//(pixel_length_y + 2*prescan_y))

    else : 
        dac_increment = min(dac_max_value // (pixel_length_x + 2*prescan_x),
                            dac_max_value//(pixel_length_x + 2*prescan_y))
        
    dac_offset_x, dac_offset_y = prescan_x*dac_increment, prescan_y*dac_increment
        
    return dac_increment, dac_offset_x, dac_offset_y

def dac_to_pixel(dac_x : c_uint16,
                 dac_y: c_uint16,
                 dac_increment : int,
                 dac_offset_x : int,
                 dac_offset_y : int,
                 dac_max_value: int = 65535) -> tuple[int,int] :
    r"""
    Returns x and y coordinates of a scan in pixels from x and y coordinates in dac unit.

    Parameters
    ----------
    dac_x : int
        Input x dac value to be converted to x pixel
    dac_y : int
        Input y dac value to be converted to y pixel
    dac_increment : int
        dac increment value of the current scan job
    dac_offset_x : int
        x dac offset of the current scan job
    dac_offset_y : int
        y dac offset of the current scan job
    dac_max_value : int
        Maximum value of the dac. By default 16 bits.

    Returns
    -------
    pixel_x : int
        x position in pixel
    pixel_y : int
        y position in pixel
    """
    dac_x_val = within_limits(dac_x.value, lower=dac_offset_x, upper=dac_max_value - dac_offset_x)
    dac_y_val = within_limits(dac_y.value, lower=dac_offset_y, upper=dac_max_value - dac_offset_y)
    dac_x_val -= dac_offset_x
    dac_y_val -= dac_offset_y
    pixel_x = dac_x_val//dac_increment
    pixel_y = dac_y_val//dac_increment
    return pixel_x, pixel_y

def pixel_to_dac(pixel_x : int,
                 pixel_y : int,
                 dac_increment : int,
                 dac_offset_x : int,
                 dac_offset_y : int,
                 dac_max_value : int = 65535) -> tuple[c_uint16,c_uint16] :
    r"""
    Returns x and y coordinates of a scan in pixels from x and y coordinates in dac unit.

    Parameters
    ----------
    pixel_x : int
        Input x pixel value to be converted to x dac unit
    pixel_y : int
        Input y pixel value to be converted to y dac unit
    dac_increment : int
        dac increment value of the current scan job
    dac_offset_x : int
        x dac offset of the current scan job
    dac_offset_y : int
        y dac offset of the current scan job
    dac_max_value : int
        Maximum value of the dac. By default 16 bits.

    Returns
    -------
    dac_x : c_uint16
        x position in dac unit
    dac_y : c_uint16
        y position in dac unit
    """
    dac_x = within_limits(dac_offset_x + pixel_x*dac_increment, lower = dac_offset_x, upper = dac_max_value-dac_offset_x)
    dac_y = within_limits(dac_offset_y + pixel_y*dac_increment, lower = dac_offset_y, upper = dac_max_value-dac_offset_y)
    return c_uint16(dac_x), c_uint16(dac_y)


def within_limits(val,
                  lower = None,
                  upper = None):
    """ limit a value to be within a minimum and maximum
    """
    if lower is not None and upper is not None:
        assert upper > lower, "input range given is impossible"
    if lower is not None:
        val = max(lower, val)
    if upper is not None:
        val = min(val, upper)
    return val

class TimeScaleConverter : 
    def __init__(self) :
        self.ureg = UnitRegistry()
        self.available_durations = {
        # "0" : None,
        "1" : Quantity('10 ns'),
        "2" : Quantity('20 ns'),
        "3" : Quantity('50 ns'),
        "4" : Quantity('100 ns'),
        "5" : Quantity('200 ns'),
        "6" : Quantity('500 ns'),
        "7" : Quantity('1 us'),
        "8" : Quantity('2 us'),
        "9" : Quantity('5 us'),
        "10" : Quantity('10 us'),
        "11" : Quantity('20 us'),
        "12" : Quantity('50 us'),
        "13" : Quantity('100 us'),
        "14" : Quantity('200 us'),
        "15" : Quantity('500 us'),
        "16" : Quantity('1 ms'),
        "17" : Quantity('2 ms'),
        "18" : Quantity('5 ms'),
        "19" : Quantity('10 ms'),
        "20" : Quantity('20 ms'),
        "21" : Quantity('50 ms'),
        "22" : Quantity('100 ms'),
        "23" : Quantity('200 ms'),
        "24" : Quantity('500 ms'),
        "25" : Quantity('1 s'),
        "26" : Quantity('2 s'),
        "27" : Quantity('5 s'),
        "28" : Quantity('10 s')}

    def find_closest_int(self, quantity : Quantity) :
        compare = [(i, abs(self.available_durations[i] - quantity)) for i in self.available_durations]
        compare.sort(key = lambda q : q[1])
        return int(compare[0][0])

    def from_quantity_to_int(self, quantity) :
        to_check = Quantity(quantity)
        # Could be improved by not going through the whole dict
        found = [int(i) for i in self.available_durations if to_check == self.available_durations[i]]
        if len(found) == 0 : 
            new_index = self.find_closest_int(to_check)
            print(f"The duration is invalid, using {self.available_durations[str(new_index)]} instead.")
            return new_index
        return found[0]
        
    def find_closest_quantity(self, index : int) :
        compare = [(i, abs(self.available_durations(i) - self.available_durations[str(index)])) for i in self.available_durations]
        compare.sort(compare, key = lambda q : q[1])
        return compare[0]
    
    def from_int_to_quantity(self, index : int) :
        if str(index) in self.available_durations.keys() :
            return self.available_durations[str(index)]
        else : 
            new_quant = self.find_closest_quantity()
            print(f"The duration is invalid, using {new_quant} instead.")
            return new_quant
    
