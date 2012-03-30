#
# openslide-python - Python bindings for the OpenSlide library
#
# Copyright (c) 2010-2011 Carnegie Mellon University
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of version 2.1 of the GNU Lesser General Public License
# as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
Low-level interface to the OpenSlide library.

Most users should use the openslide.OpenSlide class rather than this
module.

This module provides nearly direct equivalents to the OpenSlide C API.
(As an implementation detail, conversion of premultiplied image data
returned by OpenSlide into a non-premultiplied PIL.Image happens here
rather than in the high-level interface.)
"""

from ctypes import *
from itertools import count
import PIL.Image
import platform
import sys

if platform.system() == 'Windows':
    _lib = cdll.LoadLibrary('libopenslide-0.dll')
elif platform.system() == 'Darwin':
    _lib = cdll.LoadLibrary('libopenslide.0.dylib')
else:
    _lib = cdll.LoadLibrary('libopenslide.so.0')

class OpenSlideError(Exception):
    """An error produced by the OpenSlide library.

    Import this from openslide rather than from openslide.lowlevel.
    """

class _OpenSlide(object):
    """Wrapper class to make sure we correctly pass an OpenSlide handle."""

    def __init__(self, ptr):
        self._as_parameter_ = ptr
        self._valid = True
        # Retain a reference to close() to avoid GC problems during
        # interpreter shutdown
        self._close = close

    def __del__(self):
        if self._valid:
            self._close(self)

    def invalidate(self):
        self._valid = False

    @classmethod
    def from_param(cls, obj):
        if obj.__class__ != cls:
            raise ValueError("Not an OpenSlide reference")
        if not obj._as_parameter_:
            raise ValueError("Passing undefined slide object")
        if not obj._valid:
            raise ValueError("Passing closed slide object")
        return obj

# check for errors opening an image file and wrap the resulting handle
def _check_open(result, _func, _args):
    if result is None:
        raise OpenSlideError("Could not open image file")
    return _OpenSlide(c_void_p(result))

# prevent further operations on slide handle after it is closed
def _check_close(_result, _func, args):
    args[0].invalidate()

# check if the library got into an error state after each library call
def _check_error(result, _func, args):
    err = get_error(args[0])
    if err is not None:
        raise OpenSlideError(err)
    return result

# Convert returned NULL-terminated string array into a list
def _check_name_list(result, func, args):
    _check_error(result, func, args)
    names = []
    for i in count():
        name = result[i]
        if not name:
            break
        names.append(name)
    return names

# resolve and return an OpenSlide function with the specified properties
def _func(name, restype, argtypes, errcheck=_check_error):
    func = getattr(_lib, name)
    func.argtypes = argtypes
    func.restype = restype
    if errcheck is not None:
        func.errcheck = errcheck
    return func

def _load_image(buf, size):
    '''buf can be a string, but should be a ctypes buffer to avoid an extra
    copy in the caller.'''
    # First reorder the bytes in a pixel from native-endian aRGB to
    # big-endian RGBa to work around limitations in RGBa loader
    rawmode = (sys.byteorder == 'little') and 'BGRA' or 'ARGB'
    buf = PIL.Image.frombuffer('RGBA', size, buf, 'raw', rawmode, 0,
            1).tostring()
    # Now load the image as RGBA, undoing premultiplication
    return PIL.Image.frombuffer('RGBA', size, buf, 'raw', 'RGBa', 0, 1)

try:
    get_version = _func('openslide_get_version', c_char_p, [], None)
except AttributeError:
    raise OpenSlideError('OpenSlide >= 3.3.0 required')

can_open = _func('openslide_can_open', c_bool, [c_char_p], None)

open = _func('openslide_open', c_void_p, [c_char_p], _check_open)

close = _func('openslide_close', None, [_OpenSlide], _check_close)

get_level_count = _func('openslide_get_level_count', c_int32, [_OpenSlide])

_get_level_dimensions = _func('openslide_get_level_dimensions', None,
        [_OpenSlide, c_int32, POINTER(c_int64), POINTER(c_int64)])
def get_level_dimensions(slide, level):
    w, h = c_int64(), c_int64()
    _get_level_dimensions(slide, level, byref(w), byref(h))
    return w.value, h.value

get_level_downsample = _func('openslide_get_level_downsample', c_double,
        [_OpenSlide, c_int32])

get_best_level_for_downsample = \
        _func('openslide_get_best_level_for_downsample', c_int32,
        [_OpenSlide, c_double])

_read_region = _func('openslide_read_region', None,
        [_OpenSlide, POINTER(c_uint32), c_int64, c_int64, c_int32, c_int64,
        c_int64])
def read_region(slide, x, y, level, w, h):
    if w < 0 or h < 0:
        # OpenSlide would catch this, but not before we tried to allocate
        # a negative-size buffer
        raise OpenSlideError(
                "negative width (%d) or negative height (%d) not allowed" % (
                w, h))
    if w == 0 or h == 0:
        # PIL.Image.frombuffer() would raise an exception
        return PIL.Image.new('RGBA', (w, h))
    buf = (w * h * c_uint32)()
    _read_region(slide, buf, x, y, level, w, h)
    return _load_image(buf, (w, h))

get_error = _func('openslide_get_error', c_char_p, [_OpenSlide], None)

get_property_names = _func('openslide_get_property_names', POINTER(c_char_p),
        [_OpenSlide], _check_name_list)

get_property_value = _func('openslide_get_property_value', c_char_p,
        [_OpenSlide, c_char_p])

get_associated_image_names = _func('openslide_get_associated_image_names',
        POINTER(c_char_p), [_OpenSlide], _check_name_list)

_get_associated_image_dimensions = \
        _func('openslide_get_associated_image_dimensions', None,
        [_OpenSlide, c_char_p, POINTER(c_int64), POINTER(c_int64)])
def get_associated_image_dimensions(slide, name):
    w, h = c_int64(), c_int64()
    _get_associated_image_dimensions(slide, name, byref(w), byref(h))
    return w.value, h.value

_read_associated_image = _func('openslide_read_associated_image', None,
        [_OpenSlide, c_char_p, POINTER(c_uint32)])
def read_associated_image(slide, name):
    w, h = c_int64(), c_int64()
    _get_associated_image_dimensions(slide, name, byref(w), byref(h))
    buf = (w.value * h.value * c_uint32)()
    _read_associated_image(slide, name, buf)
    return _load_image(buf, (w.value, h.value))
