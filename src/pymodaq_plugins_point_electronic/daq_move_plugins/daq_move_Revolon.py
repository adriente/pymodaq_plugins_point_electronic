
from typing import Union, List, Dict
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter
from pymodaq_plugins_point_electronic.hardware.revolon import Revolon
from pymodaq_plugins_point_electronic.hardware import scan_control as consts_sc
import numpy as np

class DAQ_Move_Revolon(DAQ_Move_base):
    """ Instrument plugin class for an actuator.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Move module through inheritance via
    DAQ_Move_base. It makes a bridge between the DAQ_Move module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of controllers and actuators that should be compatible with this instrument plugin.
        * With which instrument and controller it has been tested.
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
    is_multiaxes = False  # TODO for your plugin set to True if this plugin is controlled for a multiaxis controller
    _axis_names: Union[List[str], Dict[str, int]] = ['X', 'Y']  # TODO for your plugin: complete the list
    _controller_units: Union[str, List[str]] = "pixel"  # TODO for your plugin: put the correct unit here, it could be
    # TODO  a single str (the same one is applied to all axes) or a list of str (as much as the number of axes)
    _epsilon: Union[float, List[float]] = 0.1  # TODO replace this by a value that is correct depending on your controller
    # TODO it could be a single float of a list of float (as much as the number of axes)
    data_actuator_type = DataActuatorType.DataActuator  # wether you use the new data style for actuator otherwise set this
    # as  DataActuatorType.float  (or entirely remove the line)

    params = [   # TODO for your custom plugin: elements to be added here as dicts in order to control your custom stage
                ] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilon)
    # _epsilon is the initial default value for the epsilon parameter allowing pymodaq to know if the controller reached
    # the target value. It is the developer responsibility to put here a meaningful value

    def ini_attributes(self):
        #  TODO declare the type of the wrapper (and assign it to self.controller) you're going to use for easy
        #  autocompletion
        self.controller : Revolon = None

        #TODO declare here attributes you want/need to init with a default value

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        float: The position obtained after scaling conversion.
        """
        ## TODO for your custom plugin
        if self.axis_name == self.axis_names[0]:
            int_pos = self.controller.x_position
        if self.axis_name == self.axis_names[1]:
            int_pos = self.controller.y_position
        pos = DataActuator(data = int_pos)

        self.current_position = pos
        
        return pos

    # def user_condition_to_reach_target(self) -> bool:
    #     """ Implement a condition for exiting the polling mechanism and specifying that the
    #     target value has been reached

    #    Returns
    #     -------
    #     bool: if True, PyMoDAQ considers the target value has been reached
    #     """
    #     # TODO either delete this method if the usual polling is fine with you, but if need you can
    #     #  add here some other condition to be fullfilled either a completely new one or
    #     #  using or/and operations between the epsilon_bool and some other custom booleans
    #     #  for a usage example see DAQ_Move_brushlessMotor from the Thorlabs plugin
    #     return True

    def close(self):
        """Terminate the communication protocol"""
        ## TODO for your custom plugin
        if self.is_master :
            self.controller.close() # when writing your own plugin remove this line
        #  self.controller.your_method_to_terminate_the_communication()  # when writing your own plugin replace this line

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        ## TODO for your custom plugin
        if param.name() == 'pouic':
            pass
            # self.axis_unit = self.controller.your_method_to_get_correct_axis_unit()
            # do this only if you can and if the units are not known beforehand, for instance
            # if the motors connected to the controller are of different type (mm, µm, nm, , etc...)
            # see BrushlessDCMotor from the thorlabs plugin for an exemple

        elif param.name() == "a_parameter_you've_added_in_self.params":
            pass
        #    self.controller.your_method_to_apply_this_param_change()
        else:
            pass

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator by controller (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.controller = self.ini_stage_init(slave_controller=controller, new_controller=Revolon())  # will be useful when controller is slave
        if self.is_master :
            connect_rc = self.controller.connect()
        else :
            connect_rc = consts_sc.SUCCESS
            
        if connect_rc == consts_sc.SUCCESS :
            info = "The DAQ_move Revolon scan engine has successfully started"
            initialized = True
            self.settings.child('bounds', 'is_bounds').setValue(True)
            self.settings.child('bounds', 'min_bound').setValue(0)

            if self.axis_name == self.axis_names[0]:
                self.settings.child('bounds', 'max_bound').setValue(self.controller.image_width - 1)
            else:
                self.settings.child('bounds', 'max_bound').setValue(self.controller.image_height - 1)
        else :
            info = f"Init failed (return code {connect_rc:08X})!"
            initialized = False
        return info, initialized

    def move_abs(self, value: DataActuator):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """

        value = self.check_bound(value)  #if user checked bounds, the defined bounds are applied here
        self.target_value = value
        # value = self.set_position_with_scaling(value)  # apply scaling if the user specified one
        ## TODO for your custom plugin
        if self.axis_name == self.axis_names[0]:
            px = round(self.target_value.value())
            self.controller.x_position = px
            self.current_position = DataActuator(data = px)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {px}']))
        if self.axis_name == self.axis_names[1]:
            py = round(self.target_value.value())
            self.controller.y_position = py
            self.current_position = DataActuator(data = py)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {py}']))

    def move_rel(self, value: DataActuator):
        """ Move the actuator to the relative target actuator value defined by value

        Parameters
        ----------
        value: (float) value of the relative target positioning
        """
        value = self.check_bound(self.current_position + value) - self.current_position
        self.target_value = value + self.current_position
        # value = self.set_position_relative_with_scaling(value)

        ## TODO for your custom plugin
        if self.axis_name == self.axis_names[0]:
            px = round(self.target_value.value())
            self.controller.x_position = px
            self.current_position = DataActuator(data = px)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {px}']))
        if self.axis_name == self.axis_names[1]:
            py = round(self.target_value.value())
            self.controller.y_position = py
            self.current_position = DataActuator(data = py)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {py}']))

    def move_home(self):
        """Call the reference method of the controller"""

        if self.axis_name == self.axis_names[0]:
            self.controller.x_position = 0
            self.current_position = DataActuator(data = 0)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {0}']))
        if self.axis_name == self.axis_names[1]:
            py = round(self.target_value.value())
            self.controller.y_position = 0
            self.current_position = DataActuator(data = 0)
            self.emit_status(ThreadCommand('Update_Status', [f'Moved to {0}']))


    # def stop_motion(self):
    #   """Stop the actuator and emits move_done signal"""

    #   ## TODO for your custom plugin
    #   raise NotImplemented  # when writing your own plugin remove this line
    #   self.controller.your_method_to_stop_positioning()  # when writing your own plugin replace this line
    #   self.emit_status(ThreadCommand('Update_Status', ['Some info you want to log']))


if __name__ == '__main__':
    main(__file__)
