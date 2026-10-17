import pytest
from conftest import warnings


@pytest.mark.xfail(reason='type parameters and package names are references')
@pytest.mark.sphinx('html', testroot='basic', confoverrides={'nitpicky': True})
def test_basic(app):
    app.build()
    assert warnings(app) == []
