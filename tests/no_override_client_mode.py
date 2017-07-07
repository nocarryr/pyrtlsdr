import pytest

no_overrides = pytest.mark.skipif(
    not pytest.config.getoption('--no-overrides'),
    reason='need --no-overrides to run'
)

@pytest.fixture
def client_mode(monkeypatch):
    monkeypatch.setenv('RTLSDR_CLIENT_MODE', 'true')

@no_overrides
def test_client_mode(client_mode):
    with pytest.warns(None) as record:
        import rtlsdr
    if len(record) > 1:
        if len(record) > 2:
            for w in record:
                print(str(w))
        w_classes = set([w.message.__class__ for w in record])
        assert len(w_classes) == 2
        assert ImportWarning in w_classes
        assert rtlsdr.ClientModeWarning in w_classes
    else:
        assert len(record) == 1
        assert isinstance(record[0].message, rtlsdr.ClientModeWarning)
    assert rtlsdr.RtlSdr is None
    assert rtlsdr.RtlSdrTcpClient is not None
