#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author: Rinze de Laat

Copyright © 2012 Rinze de Laat, Éric Piel, Delmic

This file is part of Odemis.

Odemis is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License version 2 as published by the Free Software
Foundation.

Odemis is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
Odemis. If not, see http://www.gnu.org/licenses/.

"""

from odemis import model
from odemis.gui import main_xrc, log
import odemis.gui.model as guimodel
from odemis.gui.cont import set_main_tab_controller, get_main_tab_controller
from odemis.gui.model.dye import DyeDatabase
from odemis.gui.model.img import InstrumentalImage
from odemis.gui.model.stream import StaticSEMStream, StaticSpectrumStream
from odemis.gui.xmlh import odemis_get_resources
from odemis.util import driver
from wx.lib.pubsub import pub
import Pyro4.errors
import logging
import numpy
import odemis.gui.conf
import odemis.gui.cont.tabs as tabs
import os.path
import pkg_resources
import scipy.io
import sys
import threading
import traceback
import wx


class OdemisGUIApp(wx.App):
    """ This is Odemis' main GUI application class
    """

    def __init__(self):
        # Replace the standard 'get_resources' with our augmented one, that
        # can handle more control types. See the xhandler package for more info.
        main_xrc.get_resources = odemis_get_resources

        # Declare attributes BEFORE calling the super class constructor
        # because it will call 'OnInit' which uses them.

        # HTTP documentation http server process
        self.http_proc = None

        self.main_data = None
        self.main_frame = None

        try:
            driver.speedUpPyroConnect(model.getMicroscope())
        except Exception:
            logging.exception("Failed to speed up start up")

        # Output catcher using a helper class
        wx.App.outputWindowClass = OdemisOutputWindow

        # Constructor of the parent class
        # ONLY CALL IT AT THE END OF :py:method:`__init__` BECAUSE OnInit will
        # be called
        # and it needs the attributes defined in this constructor!
        wx.App.__init__(self, redirect=True)

        # TODO: need to set WM_CLASS to a better value than "main.py". For now
        # almost all wxPython windows get agglomerated together and Odemis is
        # named "FirstStep" sometimes.
        # Not clear whether wxPython supports it. http://trac.wxwidgets.org/ticket/12778
        # Maybe just change the name of this module to something more unique? (eg, odemis.py)

    def OnInit(self):
        """ Application initialization, automatically run from the :wx:`App`
        constructor.
        """

        try:
            microscope = model.getMicroscope()
        except (IOError, Pyro4.errors.CommunicationError), e:
            logging.exception("Failed to connect to back-end")
            msg = ("The Odemis GUI could not connect to the Odemis back-end:\n\n"
                   "{0}\n\n"
                   "Launch user interface anyway?").format(e)

            answer = wx.MessageBox(msg,
                                   "Connection error",
                                    style=wx.YES | wx.NO | wx.ICON_ERROR)
            if answer == wx.NO:
                sys.exit(1)
            microscope = None

        self.main_data = guimodel.MainGUIData(microscope)
        # Load the main frame
        self.main_frame = main_xrc.xrcfr_main(None)

        #self.main_frame.Bind(wx.EVT_CHAR, self.on_key)

        log.create_gui_logger(self.main_frame.txt_log)
        logging.info("***********************************************")
        logging.info("************  Starting Odemis GUI  ************")
        logging.info("***********************************************")
        logging.info(wx.version())

        self.init_gui()

        # Application successfully launched
        return True

    def init_gui(self):
        """ This method binds events to menu items and initializes
        GUI controls """

        try:
            # Add frame icon
            ib = wx.IconBundle()
            ib.AddIconFromFile(os.path.join(self._module_path(),
                                            "img/icon128.png"),
                                            wx.BITMAP_TYPE_ANY)
            self.main_frame.SetIcons(ib)

            # TODO: move to menu controller?
            # Menu events
            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_quit.GetId(),
                        self.on_close_window)

            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_debug.GetId(),
                        self.on_debug_menu)
            # no need for init as we know debug is False at init.
            self.main_data.debug.subscribe(self.on_debug_va)

            # TODO: View menu with:
            # 2x2 view    F5 (Toggle, enabled only if tab has not 4 views)
            # Crosshair      (Toggle, changes according to the current view of the current tab)


            gc = odemis.gui.conf.get_general_conf()

            if os.path.exists(gc.html_dev_doc):
                self.main_frame.menu_item_htmldoc.Enable(True)

            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_htmldoc.GetId(),
                        self.on_htmldoc)

            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_inspect.GetId(),
                        self.on_inspect)

            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_about.GetId(),
                        self.on_about)

            wx.EVT_MENU(self.main_frame,
                        self.main_frame.menu_item_halt.GetId(),
                        self.on_stop_axes)

            if not self.main_data.role or self.main_data.role == "sparc":
                # works with the analysis tab
                wx.EVT_MENU(self.main_frame,
                            self.main_frame.menu_item_load1.GetId(),
                            self.on_load_example_sparc1)
                self.main_frame.menu_item_load2.Enable(False)
            elif self.main_data.role == "secom":
                # Displayed in the SECOM live view tab
                # TODO: display in the analysis tab?
                wx.EVT_MENU(self.main_frame,
                            self.main_frame.menu_item_load1.GetId(),
                            self.on_load_example_secom1)

                wx.EVT_MENU(self.main_frame,
                            self.main_frame.menu_item_load2.GetId(),
                            self.on_load_example_secom2)
            else:
                self.main_frame.menu_item_load1.Enable(False)
                self.main_frame.menu_item_load2.Enable(False)


            # The escape accelerator has to be added manually, because for some
            # reason, the 'ESC' key will not register using XRCED.
            accel_tbl = wx.AcceleratorTable([
                (wx.ACCEL_NORMAL, wx.WXK_ESCAPE,
                 self.main_frame.menu_item_halt.GetId())
            ])

            self.main_frame.SetAcceleratorTable(accel_tbl)

            self.main_frame.Bind(wx.EVT_CLOSE, self.on_close_window)
            self.main_frame.Maximize() # must be done before Show()

            # List of all possible tabs used in Odemis' main GUI
            # microscope role(s), internal name, class, tab btn, tab panel
            # order matters, as the first matching tab is be the default one

            tab_defs = [
                (
                    ("secom",),
                    ("LENS ALIGNMENT", ),
                    "secom_align",
                    tabs.LensAlignTab,
                    self.main_frame.btn_tab_secom_align,
                    self.main_frame.pnl_tab_secom_align
                ),
                (
                    ("secom", "sem", "optical"),
                    ("STREAMS", "STREAMS", "STREAMS"),
                    "secom_live",
                    tabs.SecomStreamsTab,
                    self.main_frame.btn_tab_secom_streams,
                    self.main_frame.pnl_tab_secom_streams
                ),
                (
                    ("sparc",),
                    ("MIRROR ALIGNMENT",),
                    "sparc_align",
                    tabs.MirrorAlignTab,
                    self.main_frame.btn_tab_sparc_align,
                    self.main_frame.pnl_tab_sparc_align
                ),
                (
                    ("sparc",),
                    ("ACQUISITION",),
                    "sparc_acqui",
                    tabs.SparcAcquisitionTab,
                    self.main_frame.btn_tab_sparc_acqui,
                    self.main_frame.pnl_tab_sparc_acqui
                ),
                (
                    (None, "secom", "sparc"),
                    ("GALLERY", "GALLERY", "ANALYSIS"),
                    "analysis",
                    tabs.AnalysisTab,
                    self.main_frame.btn_tab_inspection,
                    self.main_frame.pnl_tab_inspection),
            ]

            # Create the main tab controller and store a global reference
            # in the odemis.gui.cont package
            tc = tabs.TabBarController(tab_defs, self.main_frame, self.main_data)
            set_main_tab_controller(tc)

            # making it very late seems to make it smoother
            wx.CallAfter(self.main_frame.Show)
            logging.debug("Frame will be displayed soon")
        except Exception:  #pylint: disable=W0703
            self.excepthook(*sys.exc_info())
            # Re-raise the exception, so the program will exit. If this is not
            # done and exception will prevent the GUI from being shown, while
            # the program keeps running in the background.
            raise


    def init_config(self):
        """ Initialize GUI configuration """
        # TODO: Process GUI configuration here
        pass

    def _module_path(self):
        encoding = sys.getfilesystemencoding()
        return os.path.dirname(unicode(__file__, encoding))

    def on_load_example_secom1(self, e):
        """ Open the two files for example """
        mtc = get_main_tab_controller()
        secom_tab = mtc['secom_live']

        pos = secom_tab.tab_data_model.focussedView.value.view_pos.value
        opt_im = pkg_resources.resource_stream("odemis.gui.img",
                                               "example/1-optical-rot7.png")
        opt_iim = InstrumentalImage(wx.ImageFromStream(opt_im), 7.14286e-7, pos)

        pos = (pos[0] + 2e-6, pos[1] - 1e-5)
        sem_im = pkg_resources.resource_stream("odemis.gui.img",
                                               "example/1-sem-bse.png")
        sem_iim = InstrumentalImage(wx.ImageFromStream(sem_im), 4.54545e-7, pos)

        stream_controller = secom_tab.stream_controller

        stream_controller.addStatic("Fluorescence", opt_iim)
        stream_controller.addStatic("Secondary electrons", sem_iim,
                                    cls=StaticSEMStream)

    def on_load_example_secom2(self, e):
        """ Open the two files for example """
        mtc = get_main_tab_controller()
        secom_tab = mtc['secom_live']

        sem_im = pkg_resources.resource_stream("odemis.gui.img",
                                               "example/3-sem.png")
        pos = secom_tab.tab_data_model.focussedView.value.view_pos.value
        sem_iim = InstrumentalImage(wx.ImageFromStream(sem_im), 2.5e-07, pos)

        pos = (pos[0] + 5.5e-06, pos[1] + 1e-6)
        opt_im = pkg_resources.resource_stream("odemis.gui.img",
                                               "example/3-optical.png")
        opt_iim = InstrumentalImage(wx.ImageFromStream(opt_im), 1.34e-07, pos)

        mtc = get_main_tab_controller()
        stream_controller = secom_tab.stream_controller

        stream_controller.addStatic("Fluorescence", opt_iim)
        stream_controller.addStatic("Secondary electrons", sem_iim,
                                    cls=StaticSEMStream)

    def on_load_example_sparc1(self, e):
        """ Open a SEM view and spectrum cube for example
            Must be in the analysis tab of the Sparc
        """
        # It uses raw data, not images
        try:
            mtc = get_main_tab_controller()
            # TODO: put all of it in an hdf5 file and use hdf5.read_data() +
            # _display_new_data()
            sem_mat = pkg_resources.resource_stream("odemis.gui.img",
                                                    "example/s1-sem-bse.mat")
            mdsem = {model.MD_PIXEL_SIZE: (178e-9, 178e-9),
                     model.MD_POS: (0, 0)}
            semdata = scipy.io.loadmat(sem_mat)["sem"]
            semdatas = model.DataArray(numpy.array(semdata - semdata.min(),
                                                   dtype=numpy.float32),
                                       mdsem)

            spec_mat = pkg_resources.resource_stream("odemis.gui.img",
                                                    "example/s1-spectrum.mat")
            mdspec = {model.MD_PIXEL_SIZE: (178e-9, 178e-9),
                      model.MD_POS: (0, 0),
                      # 335px : 409nm -> 695 nm (about linear)
                      model.MD_WL_POLYNOMIAL: [552e-9, 0.85373e-9]
                      }
            # first dim is the wavelength, then Y, X
            specdata = scipy.io.loadmat(spec_mat)["spectraldat"]
            specdatai = model.DataArray(numpy.array(specdata - specdata.min(),
                                                    dtype=numpy.uint16),
                                        mdspec)

            # put only these streams and switch to the analysis tab
            stream_controller = mtc['analysis'].stream_controller
            stream_controller.clear()

            stream_controller.addStatic("Secondary electrons", semdatas,
                                        cls=StaticSEMStream,
                                        add_to_all_views=True)
            stream_controller.addStatic("Spectrum", specdatai,
                                        cls=StaticSpectrumStream,
                                        add_to_all_views=True)

            tab_data_model = mtc['analysis'].tab_data_model
            # This is just to fill the metadata
            # TODO: avoid this by getting the metadata from the stream =>
            # better metadata + avoid copy if packaged in an egg.
            spec_fn = pkg_resources.resource_filename("odemis.gui.img",
                                                      "example/s1-spectrum.mat")
            tab_data_model.fileinfo.value = guimodel.FileInfo(spec_fn)
            mtc.switch("analysis")
        except KeyError:
            self.goto_debug_mode()
            logging.exception("Failed to load example")

    def on_timer(self, event): #pylint: disable=W0613
        """ Timer stuff """
        pass

    def on_stop_axes(self, evt):
        if self.main_data:
            self.main_data.stopMotion()
        else:
            evt.Skip()

    def on_about(self, evt):

        info = wx.AboutDialogInfo()
        info.SetIcon(wx.Icon(os.path.join(self._module_path(), "img/icon128.png"),
                             wx.BITMAP_TYPE_PNG))
        info.Name = odemis.__shortname__
        info.Version = odemis.__version__
        info.Description = odemis.__fullname__
        info.Copyright = odemis.__copyright__
        info.WebSite = ("http://delmic.com", "delmic.com")
        info.Licence = odemis.__licensetxt__
        info.Developers = ["Éric Piel", "Rinze de Laat"]
        # info.DocWriter = '???'
        # info.Artist = '???'
        # info.Translator = '???'

        if DyeDatabase:
            info.Developers += ["", "Dye database from http://fluorophores.org"]
            info.Licence += ("""
The dye database is provided as-is, from the Fluorobase consortium.
The Fluorobase consortium provides this data and software in good faith, but
akes no warranty, expressed or implied, nor assumes any legal liability or
responsibility for any purpose for which they are used. For further information
see http://www.fluorophores.org/disclaimer/.
""")
        wx.AboutBox(info)

    def on_inspect(self, evt):
        from wx.lib.inspection import InspectionTool
        InspectionTool().Show()

    def on_htmldoc(self, evt):
        import subprocess
        self.http_proc = subprocess.Popen(
            ["python", "-m", "SimpleHTTPServer"],
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            cwd=os.path.dirname(odemis.gui.conf.get_general_conf().html_dev_doc))

        import webbrowser
        webbrowser.open('http://localhost:8000')

        #subprocess.call(('xdg-open', HTML_DOC))

    def on_debug_menu(self, evt):
        """ Update the debug VA according to the menu
        """
        self.main_data.debug.value = self.main_frame.menu_item_debug.IsChecked()

    def on_debug_va(self, enabled):
        """ This method (un)sets the application into debug mode, setting the
        log level and opening the log panel. """
        self.main_frame.menu_item_debug.Check(enabled)
        self.main_frame.pnl_log.Show(enabled)
        self.main_frame.Layout()

    def on_close_window(self, evt=None): #pylint: disable=W0613
        """ This method cleans up and closes the Odemis GUI. """
        logging.info("Exiting Odemis")

        try:
            # Put cleanup actions here (like disconnect from odemisd)

            pub.unsubAll()

            # Stop live view
            try:
                self.main_data.opticalState.value = guimodel.STATE_OFF
            except AttributeError:
                pass # just no such microscope present
            try:
                self.main_data.emState.value = guimodel.STATE_OFF
            except AttributeError:
                pass

            # let all the tabs know we are stopping
            mtc = get_main_tab_controller()
            mtc.terminate()

            if self.http_proc:
                self.http_proc.terminate()  #pylint: disable=E1101
        except Exception:
            logging.exception("Error during GUI shutdown")

        try:
            log.stop_gui_logger()
        except Exception:
            logging.exception("Error stopping GUI logging")

        self.main_frame.Destroy()

    def excepthook(self, etype, value, trace): #pylint: disable=W0622
        """ Method to intercept unexpected errors that are not caught
        anywhere else and redirects them to the logger. """
        # in case of error here, don't call again, it'd create infinite recurssion
        if sys and traceback:
            sys.excepthook = sys.__excepthook__

            try:
                exc = traceback.format_exception(type, value, trace)
                logging.error("".join(exc))

                # When an exception occurs, automatically got to debug mode.
                if not isinstance(value, NotImplementedError):
                    self.main_data.debug.value = True
            finally:
                # put us back
                sys.excepthook = self.excepthook
        else:
            print etype, value, trace

class OdemisOutputWindow(object):
    """ Helper class which allows ``wx`` to display uncaught
        messages in the way defined by the :py:mod:`log` module. """
    def __init__(self):
        pass

    def write(self, txt):
        if txt.strip() != "":
            logging.error("[CAP] %s", txt.strip())

def installThreadExcepthook():
    """ Workaround for sys.excepthook thread bug
    http://spyced.blogspot.com/2007/06/workaround-for-sysexcepthook-bug.html

    Call once from ``__main__`` before creating any threads.
    """
    init_old = threading.Thread.__init__
    def init(self, *args, **kwargs):
        init_old(self, *args, **kwargs)
        run_old = self.run
        def run_with_except_hook(*args, **kw):
            try:
                run_old(*args, **kw)
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                sys.excepthook(*sys.exc_info())
        self.run = run_with_except_hook
    threading.Thread.__init__ = init

def main():
    log.init_logger()

    # Create application
    app = OdemisGUIApp()
    # Change exception hook so unexpected exception
    # get caught by the logger
    backup_excepthook, sys.excepthook = sys.excepthook, app.excepthook

    # Start the application
    app.MainLoop()
    app.Destroy()

    sys.excepthook = backup_excepthook

if __name__ == '__main__':
    installThreadExcepthook()
    main()
