import pytest
from sv2cli.project import new_project, QUARTER
from sv2cli.edit import apply

@pytest.fixture
def project():
    p=new_project("Lead",120)
    return apply(p,[{"op":"notes.replace","tracks":["#1"],"notes":[{"onset":0,"duration":QUARTER,"pitch":60,"lyrics":"la"},{"onset":QUARTER,"duration":QUARTER,"pitch":62,"lyrics":"na"}]}],True)
