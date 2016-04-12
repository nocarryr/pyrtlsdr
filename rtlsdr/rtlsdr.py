#    This file is part of pyrlsdr.
#    Copyright (C) 2013 by Roger <https://github.com/roger-/pyrtlsdr>
#
#    pyrlsdr is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    pyrlsdr is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with pyrlsdr.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import division, print_function
from ctypes import *
try:                from  librtlsdr import librtlsdr, p_rtlsdr_dev, rtlsdr_read_async_cb_t
except ImportError: from .librtlsdr import librtlsdr, p_rtlsdr_dev, rtlsdr_read_async_cb_t
try:                from itertools import izip
except ImportError: izip = zip
import sys

if sys.version_info.major >= 3:
    basestring = str

# see if NumPy is available
has_numpy = True
try:
    import numpy as np
except ImportError:
    has_numpy = False

class RtlSdrError(IOError):
    def __init__(self, msg, error_code=None):
        self.msg = msg
        self.error_code = error_code
    def __str__(self):
        msg = self.msg
        if self.error_code is not None:
            msg = 'Error Code {}: {}'.format(self.error_code, msg)
        return msg


class RtlSdr(object):
    # some default values for various parameters
    DEFAULT_GAIN = 'auto'
    DEFAULT_FC = 80e6
    DEFAULT_RS = 1.024e6
    DEFAULT_READ_SIZE = 1024
    DEFAULT_ASYNC_BUF_NUMBER = 0 # librtlsdr will use the default (15)

    CRYSTAL_FREQ = 28800000

    gain_values = []
    valid_gains_db = []
    buffer = []
    num_bytes_read = c_int32(0)
    device_opened = False
    read_async_canceling = False

    def __init__(self, device_index=0, test_mode_enabled=False):
        self.open(device_index, test_mode_enabled)

    def _call_librtlsdr(self, fn, *args, **kwargs):
        test_result = kwargs.get('test_result', True)
        result = fn(self.dev_p, *args)

        if test_result and result < 0:
            self.close()
            msg = fn.__name__
            if msg.startswith('rtlsdr_'):
                msg = msg.lstrip('rtlsdr_')
            raise RtlSdrError(msg, result)

        return result

    def open(self, device_index=0, test_mode_enabled=False):
        ''' Initialize RtlSdr object.
        The test_mode_enabled parameter can be used to enable a special test mode, which will return the value of an
        internal RTL2832 8-bit counter with calls to read_bytes()
        '''

        # this is the pointer to the device structure used by all librtlsdr
        # functions
        self.dev_p = p_rtlsdr_dev(None)

        # initialize device
        self._call_librtlsdr(librtlsdr.rtlsdr_open, device_index)

        # enable test mode if necessary
        self._call_librtlsdr(librtlsdr.rtlsdr_set_testmode, int(test_mode_enabled))

        # reset buffers
        self._call_librtlsdr(librtlsdr.rtlsdr_reset_buffer)

        self.device_opened = True
        self.init_device_values()

    def init_device_values(self):
        self.gain_values = self.get_gains()
        self.valid_gains_db = [val/10 for val in self.gain_values]

        # set default state
        self.set_sample_rate(self.DEFAULT_RS)
        self.set_center_freq(self.DEFAULT_FC)
        self.set_gain(self.DEFAULT_GAIN)

    def close(self):
        if not self.device_opened:
            return

        librtlsdr.rtlsdr_close(self.dev_p)
        self.device_opened = False

    def __del__(self):
        self.close()

    def set_center_freq(self, freq):
        ''' Set center frequency of tuner (in Hz).
        Use get_center_freq() to see the precise frequency used. '''

        freq = int(freq)

        self._call_librtlsdr(librtlsdr.rtlsdr_set_center_freq, freq)


    def get_center_freq(self):
        ''' Return center frequency of tuner (in Hz). '''

        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_center_freq)

        # FIXME: the E4000 rounds to kHz, this may not be true for other tuners
        reported_center_freq = result
        center_freq = round(reported_center_freq, -3)

        return center_freq

    def set_freq_correction(self, err_ppm):
        ''' Set frequency offset of tuner (in PPM). '''

        freq = int(err_ppm)

        self._call_librtlsdr(librtlsdr.rtlsdr_set_freq_correction, err_ppm)

    def get_freq_correction(self):
        ''' Get frequency offset of tuner (in PPM). '''

        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_freq_correction)
        return result

    def set_sample_rate(self, rate):
        ''' Set sample rate of tuner (in Hz).
        Use get_sample_rate() to see the precise sample rate used. '''

        rate = int(rate)

        self._call_librtlsdr(librtlsdr.rtlsdr_set_sample_rate, rate)

    def get_sample_rate(self):
        ''' Get sample rate of tuner (in Hz) '''

        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_sample_rate)

        # figure out actual sample rate, taken directly from librtlsdr
        reported_sample_rate = result
        rsamp_ratio = (self.CRYSTAL_FREQ * pow(2, 22)) // reported_sample_rate
        rsamp_ratio &= ~3
        real_rate = (self.CRYSTAL_FREQ * pow(2, 22)) / rsamp_ratio;

        return real_rate

    def set_gain(self, gain):
        ''' Set gain of tuner.
        If gain is 'auto', AGC mode is enabled; otherwise gain is in dB. The actual
        gain used is rounded to the nearest value supported by the device (see the
        values in RtlSdr.valid_gains_db).
        '''
        if isinstance(gain, basestring) and gain == 'auto':
            # disable manual gain -> enable AGC
            self.set_manual_gain_enabled(False)

            return

        # find supported gain nearest to one requested
        errors = [abs(10*gain - g) for g in self.gain_values]
        nearest_gain_ind = errors.index(min(errors))

        # disable AGC
        self.set_manual_gain_enabled(True)

        self._call_librtlsdr(librtlsdr.rtlsdr_set_tuner_gain,
                             self.gain_values[nearest_gain_ind])

    def get_gain(self):
        ''' Get gain of tuner (in dB). '''

        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_tuner_gain,
                                      test_result=False)
        if 0 and result == 0:
            self.close()
            raise RtlSdrError('Error when getting gain', result)

        return result/10

    def get_gains(self):
        ''' Get list of supported gains from driver
        All gains are in tenths of a dB
        '''
        buffer = (c_int *50)()
        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_tuner_gains, buffer)

        gains = []
        for i in range(result):
            gains.append(buffer[i])

        return gains

    def set_manual_gain_enabled(self, enabled):
        ''' Enable manual gain control of tuner.
        If enabled is False, then AGC is used. Use set_gain() instead of calling
        this directly.
        '''
        self._call_librtlsdr(librtlsdr.rtlsdr_set_tuner_gain_mode, int(enabled))

    def set_agc_mode(self, enabled):
        ''' Enable RTL2832 AGC
        '''
        result = self._call_librtlsdr(librtlsdr.rtlsdr_set_agc_mode, int(enabled))

        return result

    def set_direct_sampling(self, direct):
        ''' Enable direct sampling.
        direct -- sampling mode
        If direct is False or 0, disable direct sampling
        If direct is 'i' or 1, use ADC I input
        If direct is 'q' or 2, use ADC Q input
        '''

        # convert parameter
        if isinstance(direct, basestring):
            if direct.lower() == 'i':
                direct = 1
            elif direct.lower() == 'q':
                direct = 2
            else:
                raise SyntaxError('invalid value "%s"' % direct)

        # make sure False works as an option
        if not direct:
            direct = 0

        result = self._call_librtlsdr(librtlsdr.rtlsdr_set_direct_sampling,
                                      direct)

        return result

    def get_tuner_type(self):
        ''' Get the tuner type.
        '''
        result = self._call_librtlsdr(librtlsdr.rtlsdr_get_tuner_type)

        return result

    def read_bytes(self, num_bytes=DEFAULT_READ_SIZE):
        ''' Read specified number of bytes from tuner. Does not attempt to unpack
        complex samples (see read_samples()), and data may be unsafe as buffer is
        reused.
        '''
        # FIXME: libsdrrtl may not be able to read an arbitrary number of bytes

        num_bytes = int(num_bytes)

        # create buffer, as necessary
        if len(self.buffer) != num_bytes:
            array_type = (c_ubyte*num_bytes)
            self.buffer = array_type()

        self._call_librtlsdr(librtlsdr.rtlsdr_read_sync, self.buffer, num_bytes,
                             byref(self.num_bytes_read))

        if self.num_bytes_read.value != num_bytes:
            self.close()
            raise RtlSdrError('Short read, requested %d bytes, received %d'
                              % (num_bytes, self.num_bytes_read.value))

        return self.buffer

    def read_samples(self, num_samples=DEFAULT_READ_SIZE):
        ''' Read specified number of complex samples from tuner. Real and imaginary
        parts are normalized to be in the range [-1, 1]. Data is safe after
        this call (will not get overwritten by another one).
        '''
        num_bytes = 2*num_samples

        raw_data = self.read_bytes(num_bytes)
        iq = self.packed_bytes_to_iq(raw_data)

        return iq

    def packed_bytes_to_iq(self, bytes):
        ''' Convenience function to unpack array of bytes to Python list/array
        of complex numbers and normalize range. Called automatically by read_samples()
        '''
        if has_numpy:
            # use NumPy array
            iq = np.empty(len(bytes)//2, 'complex')
            iq.real, iq.imag = bytes[::2], bytes[1::2]
            iq /= (255/2)
            iq -= (1 + 1j)
        else:
            # use normal list
            iq = [complex(i/(255/2) - 1, q/(255/2) - 1) for i, q in izip(bytes[::2], bytes[1::2])]

        return iq

    def read_bytes_async(self, callback, num_bytes=DEFAULT_READ_SIZE, context=None):
        ''' Continuously read "num_bytes" bytes from tuner and call Python function
        "callback" with the result. "context" is any Python object that will be
        make available to callback function (default supplies this RtlSdr object).
        Data may be overwritten (see read_bytes()).
        '''
        num_bytes = int(num_bytes)

        # we don't call the provided callback directly, but add a layer inbetween
        # to convert the raw buffer to a safer type

        # save requested callback
        self._callback_bytes = callback

        # convert Python callback function to a librtlsdr callback
        rtlsdr_callback = rtlsdr_read_async_cb_t(self._bytes_converter_callback)

        # use this object as context if none provided
        if not context:
            context = self

        self.read_async_canceling = False
        self._call_librtlsdr(librtlsdr.rtlsdr_read_async, rtlsdr_callback,
                             context, self.DEFAULT_ASYNC_BUF_NUMBER, num_bytes)

        self.read_async_canceling = False

        return

    def _bytes_converter_callback(self, raw_buffer, num_bytes, context):
        # convert buffer to safer type
        array_type = (c_ubyte*num_bytes)
        values = cast(raw_buffer, POINTER(array_type)).contents

        # skip callback if cancel_read_async() called
        if self.read_async_canceling:
            return

        self._callback_bytes(values, context)

    def read_samples_async(self, callback, num_samples=DEFAULT_READ_SIZE, context=None):
        ''' Combination of read_samples() and read_bytes_async() '''

        num_bytes = 2*num_samples

        self._callback_samples = callback
        self.read_bytes_async(self._samples_converter_callback, num_bytes, context)

        return

    def _samples_converter_callback(self, buffer, context):
        iq = self.packed_bytes_to_iq(buffer)

        self._callback_samples(iq, context)

    def cancel_read_async(self):
        ''' Cancel async read. This should be called eventually when using async
        reads, or callbacks will never stop. See also decorators limit_time()
        and limit_calls() in helpers.py.
        '''

        result = self._call_librtlsdr(librtlsdr.rtlsdr_cancel_async,
                                      test_result=False)
        # sometimes we get additional callbacks after canceling an async read,
        # in this case we don't raise exceptions
        if result < 0 and not self.read_async_canceling:
            self.close()
            raise RtlSdrError('async_read', result)

        self.read_async_canceling = True

    center_freq = fc = property(get_center_freq, set_center_freq)
    sample_rate = rs = property(get_sample_rate, set_sample_rate)
    gain = property(get_gain, set_gain)
    freq_correction = property(get_freq_correction, set_freq_correction)
