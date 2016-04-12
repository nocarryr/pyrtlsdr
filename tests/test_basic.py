import pytest

def test(sdr_cls, use_numpy):
    from utils import generic_test
    sdr = sdr_cls()
    generic_test(sdr, use_numpy=use_numpy)
    sdr.close()

def test_exceptions(sdr_cls):
    from rtlsdr.rtlsdr import RtlSdrError, librtlsdr

    librtlsdr.RETURN_VALUE = -1

    try:
        with pytest.raises(RtlSdrError):
            sdr = sdr_cls()

        librtlsdr.RETURN_VALUE = 0
        sdr = sdr_cls()
        librtlsdr.RETURN_VALUE = -1

        with pytest.raises(RtlSdrError):
            v = sdr.fc
        with pytest.raises(RtlSdrError):
            sdr.fc = 3e6
        with pytest.raises(RtlSdrError):
            v = sdr.rs
        with pytest.raises(RtlSdrError):
            sdr.rs = 1e6
        with pytest.raises(RtlSdrError):
            sdr.gain = 10
        with pytest.raises(RtlSdrError):
            v = sdr.read_bytes()
        with pytest.raises(RtlSdrError):
            v = sdr.read_samples()
        with pytest.raises(RtlSdrError):
            sdr.set_direct_sampling('i')
    finally:
        librtlsdr.RETURN_VALUE = 0
