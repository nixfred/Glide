import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('owner', Path(__file__).parents[1] / 'scripts/mouse-owner.py')
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
e = owner.ec

class OwnershipTests(unittest.TestCase):
    def test_keyboard_does_not_claim_pointer(self):
        for code in [e.KEY_A, e.KEY_LEFTSHIFT, e.KEY_ESC]:
            self.assertFalse(owner.pointer_activity(SimpleNamespace(type=e.EV_KEY, code=code, value=1)))

    def test_physical_key_press_reclaims_but_release_and_repeat_do_not(self):
        for code in [e.KEY_A, e.KEY_LEFTSHIFT, e.KEY_ESC]:
            for value in [0, 1, 2]:
                self.assertEqual(owner.input_activity(SimpleNamespace(type=e.EV_KEY, code=code, value=value)), value == 1)

    def test_only_real_keyboards_are_observed(self):
        fake = SimpleNamespace(path='/dev/input/event999', info=SimpleNamespace(bustype=e.BUS_USB), capabilities=lambda **kw: {e.EV_KEY:[e.KEY_A,e.KEY_Z,e.KEY_ENTER]})
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/pci0000/usb1/input999')):
            self.assertTrue(owner.physical_keyboard(fake))
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/virtual/input/input999')):
            self.assertFalse(owner.physical_keyboard(fake))
        fake.info.bustype = e.BUS_VIRTUAL
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/pci0000/usb1/input999')):
            self.assertFalse(owner.physical_keyboard(fake))

    def test_real_motion_and_click_claim(self):
        for kind, code, value in [(e.EV_REL,e.REL_X,4), (e.EV_REL,e.REL_Y,-3), (e.EV_KEY,e.BTN_LEFT,1), (e.EV_ABS,e.ABS_MT_POSITION_X,42)]:
            self.assertTrue(owner.pointer_activity(SimpleNamespace(type=kind,code=code,value=value)))
        self.assertFalse(owner.pointer_activity(SimpleNamespace(type=e.EV_REL,code=e.REL_X,value=0)))

    def test_uinput_does_not_create_feedback(self):
        fake = SimpleNamespace(path='/dev/input/event999', info=SimpleNamespace(bustype=e.BUS_USB), capabilities=lambda **kw: {e.EV_REL:[e.REL_X,e.REL_Y]})
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/virtual/input/input999')):
            self.assertFalse(owner.physical_pointer(fake))
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/pci0000/usb1/input999')):
            self.assertTrue(owner.physical_pointer(fake))
        with patch.object(Path, 'resolve', return_value=Path('/sys/devices/virtual/misc/uhid/input999')):
            self.assertTrue(owner.physical_pointer(fake))

if __name__ == '__main__': unittest.main()
