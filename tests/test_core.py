import pytest
from thewire import core

def test_workflow(tmp_path,monkeypatch):
 monkeypatch.setattr(core,'HOME',tmp_path)
 core.create_project('demo','Client A');core.start('demo','Implement API')
 assert len(core.rows('SELECT * FROM sessions WHERE end IS NULL'))==1
 with pytest.raises(Exception):core.start('demo','Overlapping timer')
 core.stop('Done');core.log('demo','insight','Integration test passed')
 assert len(core.report('demo')['sessions'])==1
 assert core.rows('SELECT body FROM worklogs')[0]['body']=='Integration test passed'

def test_plugin_validation(tmp_path,monkeypatch):
 monkeypatch.setattr(core,'MANIFESTS',tmp_path/'plugins')
 p=tmp_path/'plugin.json';p.write_text('{"name":"test-tool","executable":"echo"}')
 core.register(p)
 assert core.manifests()['test-tool']['executable']=='echo'
