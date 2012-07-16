#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Created on 12 Jul 2012

@author: Éric Piel

Copyright © 2012 Éric Piel, Delmic

This file is part of Open Delmic Microscope Software.

Delmic Acquisition Software is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

Delmic Acquisition Software is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with Delmic Acquisition Software. If not, see http://www.gnu.org/licenses/.
'''
# This is a basic command line interface to the odemis back-end
import Pyro4
import __version__
import argparse
import collections
import inspect
import logging
import model
import os
import sys

BACKEND_RUNNING = "RUNNING"
BACKEND_DEAD = "DEAD"
BACKEND_STOPPED = "STOPPED"
def get_backend_status():
    try:
        microscope = model.getMicroscope()
        if len(microscope.name) > 0:
            return BACKEND_RUNNING
    except:
        if os.path.exists(model.BACKEND_FILE):
            return BACKEND_DEAD
        else:
            return BACKEND_STOPPED
    return BACKEND_DEAD

status_to_xtcode = {BACKEND_RUNNING: 0,
                    BACKEND_DEAD: 1,
                    BACKEND_STOPPED: 2
                    }

def kill_backend():
    try:
        backend = model.getContainer(model.BACKEND_NAME)
        backend.terminate()
    except:
        logging.error("Failed to stop the back-end")
        return 127
    return 0

def print_component(comp, level):
    """
    Pretty print on one line a component
    comp (Component): the component to print
    level (int > 0): hierarchy level (for indentation)
    """
    if level == 0:
        indent = ""
    else:
        indent = u" ↳"*level + " "
    print indent + comp.name + "\trole:" + comp.role
    # TODO display .affects
    # TODO would be nice to display which class is the component
    # TODO:
    # * if emitter, display .shape
    # * if detector, display .shape
    # * if actuator, display .axes

def print_component_tree(root, level=0):
    """
    Print all the components starting from the root. 
    root (Component): the component at the root of the tree
    level (int > 0): hierarchy level (for pretty printing)
    """
    # first print the root component
    print_component(root, level)

    # display all the children
    for comp in root.children:
            print_component_tree(comp, level + 1)

def print_microscope_tree(mic):
    """
    Print all the components starting from the microscope. 
    root (Microscope): a microscope
    """
    # first print the microscope
    print_component(mic, 0)
    # Microscope is a special case
    for comp in mic.detectors:
        print_component_tree(comp, 1)
    for comp in mic.emitters:
        print_component_tree(comp, 1)
    for comp in mic.actuators:
        print_component_tree(comp, 1)
    # no children

def list_components():
    # We actually just browse as a tree the microscope 
    try:
        microscope = model.getMicroscope()
    except:
        logging.error("Failed to contact the back-end")
        return 127
    print_microscope_tree(microscope)
    return 0

def print_roattribute(name, value):
    print "\t" + name + " (RO Attribute)\t value: %s" % str(value)

#known_fixed_attributes = ["shape", "axes", "ranges"]
non_roattributes_classes = (Pyro4.core._RemoteMethod, Pyro4.Proxy, model.Component,
                            model.DataFlowBase, model.VigilantAttributeBase)
non_roattributes_names = ("name", "role", "parent", "children", "affects", 
                          "actuators", "detectors", "emitters")
def print_roattributes(component):
    # roattributes are a bit tricky because they look like completely normal value
    # so we find them by elimination
    for name, value in inspect.getmembers(component):
        # it should not start with a "_"
        if name.startswith("_"):
            continue
        # it should not be a special name
        if name in non_roattributes_names:
            continue
        # it should not be callable
        if callable(value):
            continue
        # it should not be a special class
        if isinstance(value, non_roattributes_classes):
            continue
        print_roattribute(name, value)
        

def print_data_flow(name, df):
    print "\t" + name + " (Data-flow)"

def print_data_flows(component):
    # find all dataflows
    for name, value in inspect.getmembers(component, lambda x: isinstance(x, model.DataFlowBase)):
        print_data_flow(name, value)

def print_vattribute(name, va):
    if va.unit:
        unit = "(unit: %s)" % va.unit
    else:
        unit = ""
    print "\t" + name + " (Vigilant Attribute)\t value: %s %s" % (str(va.value), unit)

def print_vattributes(component):
    # find all vattributes
    # 
    for name, value in inspect.getmembers(component, lambda x: isinstance(x, model.VigilantAttributeBase)):
        print_vattribute(name, value)
    
def print_attributes(component):
    print "Component '%s':" % component.name
    print "\trole: %s" % component.role
    print "\taffects: " + ", ".join(["'"+c.name+"'" for c in component.affects]) 
    print_roattributes(component)
    print_vattributes(component)
    print_data_flows(component)

def get_component(comp_name):
    """
    return the component with the given name
    comp_name (string): name of the component to find
    raises
        LookupError if the component doesn't exist
        other exception if there is an error while contacting the backend
    """
    components = model.getComponents()
    component = None
    for c in components:
        if c.name == comp_name:
            component = c
            break
   
    if component is None:
        raise LookupError("Failed to find component '%s'", comp_name)
    
    return component

def get_actuator(comp_name):
    """
    return the actuator component with the given name
    comp_name (string): name of the component to find
    raises
        LookupError if the component doesn't exist
        other exception if there is an error while contacting the backend
    """
    # isinstance() doesn't work, so we just list every component in microscope.actuators
    microscope = model.getMicroscope()
    components = microscope.actuators
    component = None
    for c in components:
        if c.name == comp_name:
            component = c
            break
   
    if component is None:
        raise LookupError("Failed to find actuator '%s'", comp_name)
    
    return component

def list_properties(comp_name):
    """
    print the data-flows and vattributes of a component
    comp_name (string): name of the component
    """
    try:
        component = get_component(comp_name)
    except LookupError:
        logging.error("Failed to find component '%s'", comp_name)
        return 127
    except:
        logging.error("Failed to contact the back-end")
        return 127
   
    print_attributes(component)
    return 0
    
def boolify(s):
    if s == 'True' or s == 'true':
        return True
    if s == 'False' or s == 'false':
        return False
    raise ValueError('Not a boolean value: %s' % s)

def reproduceTypedValue(real_val, str_val):
    """
    Tries to convert a string to the type of the given value
    real_val (object): value with the type that must be converted to
    str_val (string): string that will be converted
    return the value contained in the string with the type of the real value
    raises 
      ValueError() if not possible to convert
      TypeError() if type of real value is not supported
    """
    if isinstance(real_val, bool):
        return boolify(str_val)
    elif isinstance(real_val, int):
        return int(str_val)
    elif isinstance(real_val, float):
        return float(str_val)
    elif isinstance(real_val, basestring):
        return str_val
    elif isinstance(real_val, dict): # must be before iterable
        if len(real_val) > 0:
            key_real_val = real_val.keys()[0]
            value_real_val = real_val[key_real_val]
        else:
            logging.warning("Type of attribute is unknown, using string")
            sub_real_val = ""
            value_real_val = ""
            
        dict_val = {}
        for sub_str in str_val.split(','):
            item = sub_str.split(':')
            assert(len(item) == 2)
            key =  reproduceTypedValue(key_real_val, item[0]) # TODO Should warn if len(item) != 2
            value = reproduceTypedValue(value_real_val, item[1])
            dict_val[key] = value
        return dict_val
    elif isinstance(real_val, collections.Iterable):
        if len(real_val) > 0:
            sub_real_val = real_val[0]
        else:
            logging.warning("Type of attribute is unknown, using string")
            sub_real_val = ""

        iter_val = [] # the most preserving iterable
        for sub_str in str_val.split(','):
            iter_val.append(reproduceTypedValue(sub_real_val, sub_str))
        final_val = type(real_val)(iter_val) # cast to real type
        return final_val
    
    raise TypeError("Type %r is not supported to convert %s" % (type(real_val), str_val))

def set_attr(comp_name, attr_name, str_val):
    """
    set the value of vigilant attribute of the given component using the type
    of the current value of the attribute.
    """
    try:
        component = get_component(comp_name)
    except LookupError:
        logging.error("Failed to find component '%s'", comp_name)
        return 127
    except:
        logging.error("Failed to contact the back-end")
        return 127

    try:
        attr = getattr(component, attr_name)
    except:
        logging.error("Failed to find attribute '%s' on component '%s'", attr_name, comp_name)
        return 129
    
    if not isinstance(attr, model.VigilantAttributeBase):
        logging.error("'%s' is not a vigilant attribute of component '%s'", attr_name, comp_name)
        return 129
    
    try:
        new_val = reproduceTypedValue(attr.value, str_val)
    except TypeError:
        logging.error("'%s' is of unsupported type %r", attr_name, type(attr.value))
        return 127
    except ValueError:
        logging.error("Impossible to convert '%s' to a %r", str_val, type(attr.value))
        return 127
    
    try:
        attr.value = new_val
    except:
        logging.exception("Failed to set %s.%s = '%s'", comp_name, attr_name, str_val)
        return 127
    return 0

MAX_DISTANCE = 0.1 #m
def move(comp_name, axis_name, str_distance):
    """
    move (relatively) the axis of the given component by the specified about of µm
    """
    # for safety reason, we use µm instead of meters, as it's harder to type a
    # huge distance
    try:
        component = get_actuator(comp_name)
    except LookupError:
        logging.error("Failed to find actuator '%s'", comp_name)
        return 127
    except:
        logging.error("Failed to contact the back-end")
        return 127

    if axis_name not in component.axes:
        logging.error("Actuator %s has not axis '%s'", comp_name, axis_name)
        return 129
    
    try:
        distance = float(str_distance) * 1e-6 # µm -> m
    except ValueError:
        logging.error("Distance '%s' cannot be converted to a number", str_distance)
        return 127
    
    if abs(distance) > MAX_DISTANCE:
        logging.error("Distance of %f m is too big (> %f m)", distance, MAX_DISTANCE)
        return 129
    
    try:
        component.moveRel({axis_name: distance})
    except:
        logging.error("Failed to move axis %s of component %s", axis_name, comp_name)
        return 127
    
    return 0

def stop_move():
    """
    stop the move of every axis of every actuators
    """
    # We actually just browse as a tree the microscope 
    try:
        microscope = model.getMicroscope()
        actuators = microscope.actuators
    except:
        logging.error("Failed to contact the back-end")
        return 127
    
    ret = 0
    for actuator in actuators:
        try:
            actuator.stop()
        except:
            logging.error("Failed to stop actuator %s", actuator.name)
            ret = 127
    
    return ret

def main(args):
    """
    Handles the command line arguments 
    args is the list of arguments passed
    return (int): value to return to the OS as program exit code
    """

    # arguments handling 
    parser = argparse.ArgumentParser(description=__version__.name)

    parser.add_argument('--version', action='version', 
                        version=__version__.name + " " + __version__.version + " – " + __version__.copyright)
    opt_grp = parser.add_argument_group('Options')
    opt_grp.add_argument("--log-level", dest="loglev", metavar="<level>", type=int,
                        default=0, help="Set verbosity level (0-2, default = 0)")
    dm_grp = parser.add_argument_group('Back-end management')
    dm_grpe = dm_grp.add_mutually_exclusive_group()
    dm_grpe.add_argument("--kill", "-k", dest="kill", action="store_true", default=False,
                         help="Kill the running back-end")
    dm_grpe.add_argument("--check", dest="check", action="store_true", default=False,
                         help="Check for a running back-end (only returns exit code)")
    dm_grpe.add_argument("--list", "-l", dest="list", action="store_true", default=False,
                         help="List the components of the microscope")
    dm_grpe.add_argument("--list-prop", "-L", dest="listprop", metavar="<component>",
                         help="List the properties of a component")
    dm_grpe.add_argument("--set-attr", "-s", dest="setattr", nargs=3, action='append',
                         metavar=("<component>", "<attribute>", "<value>"),
                         help="Set the attribute of a component (lists are delimited by commas)")
    dm_grpe.add_argument("--move", "-m", dest="move", nargs=3, action='append',
                         metavar=("<component>", "<axis>", "<distance>"),
                         help=u"move the axis by the amount of µm.")
    dm_grpe.add_argument("--stop", "-S", dest="stop", action="store_true", default=False,
                         help="Immediately stop all the actuators in all directions.")


    options = parser.parse_args(args[1:])
    
    # Set up logging before everything else
    if options.loglev < 0:
        parser.error("log-level must be positive.")
    loglev_names = [logging.WARNING, logging.INFO, logging.DEBUG]
    loglev = loglev_names[min(len(loglev_names) - 1, options.loglev)]
    logging.getLogger().setLevel(loglev)
    
    # change the log format to be more descriptive
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s (%(module)s) %(levelname)s: %(message)s'))
    logging.getLogger().addHandler(handler)
    
    # anything to do?
    if (not options.check and not options.kill and not options.list 
        and not options.stop and options.move is None
        and options.listprop is None and options.setattr is None):
        logging.error("No action specified.")
        return 127
    
    status = get_backend_status()
    if options.check:
        logging.info("Status of back-end is %s", status)
        return status_to_xtcode[status]
    
    # check if there is already a backend running
    if status == BACKEND_STOPPED:
        logging.error("No running back-end")
        return 127
    elif status == BACKEND_DEAD:
        logging.error("Back-end appears to be non-responsive.")
        return 127
    
    try:
        if options.kill:
            return kill_backend()
    
        if options.list:
            return list_components()
        
        if options.listprop is not None:
            return list_properties(options.listprop)
        
        if options.setattr is not None:
            for c, a, v in options.setattr:
                ret = set_attr(c, a, v)
                if ret != 0:
                    return ret
            return 0
        
        if options.move is not None:
            for c, a, d in options.move:
                ret = move(c, a, d)
                # TODO move commands to the same actuator should be agglomerated
                if ret != 0:
                    return ret
            return 0
        
        if options.stop:
            return stop_move()
    except:
        logging.exception("Unexpected error while performing action.")
        return 127
    
    return 0

if __name__ == '__main__':
    ret = main(sys.argv)
    logging.shutdown() 
    exit(ret)
    
# vim:tabstop=4:shiftwidth=4:expandtab:spelllang=en_gb:spell: