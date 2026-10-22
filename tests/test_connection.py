from unittest.mock import Mock
import requests
from grenade.connection import check_key, MODELS_URL


def test_missing_key_does_not_request(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    session=Mock()
    assert check_key(session=session)['status']=='missing_key'
    session.get.assert_not_called()


def test_valid_key_is_not_search_access_or_persisted():
    session=Mock();session.get.return_value=Mock(status_code=200)
    session.get.return_value.json.return_value={'data':[{'id':'test-model'}]}
    result=check_key('private-test-credential',session)
    assert result['authenticated'] and result['http_status']==200
    assert 'separately' in result['message']
    assert 'private-test-credential' not in str(result)
    session.get.assert_called_once_with(MODELS_URL,headers={'Authorization':'Bearer private-test-credential'},timeout=20,allow_redirects=False)


def test_models_200_requires_valid_schema():
    for data in [{'unexpected':'HTML from a gateway'},[],None]:
        session=Mock();session.get.return_value=Mock(status_code=200)
        session.get.return_value.json.return_value=data
        assert check_key('test',session)['status']=='unexpected_response'


def test_network_failures_never_echo_exception_secrets():
    for exception in [requests.Timeout('private-test-credential'),requests.ConnectionError('private-test-credential')]:
        session=Mock();session.get.side_effect=exception
        result=check_key('private-test-credential',session)
        assert not result['authenticated'] and 'private-test-credential' not in str(result)


def test_status_errors_do_not_expose_response_body():
    for status in [301,401,402,403,429,500]:
        session=Mock();session.get.return_value=Mock(status_code=status,text='private-test-credential')
        result=check_key('test',session)
        assert result['http_status']==status and not result['authenticated']
        assert 'private-test-credential' not in str(result)


def test_settings_reads_project_env_from_other_directory(tmp_path,monkeypatch):
    import grenade.connection as connection
    project=tmp_path/'project';project.mkdir()
    (project/'.env').write_text('DEEPSEEK_API_KEY=temporary-test-key\n')
    monkeypatch.setattr(connection,'ROOT',project)
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    monkeypatch.chdir(tmp_path)
    connection.load_settings()
    import os
    assert os.environ['DEEPSEEK_API_KEY']=='temporary-test-key'
    monkeypatch.delenv('DEEPSEEK_API_KEY')


def test_settings_does_not_override_environment(tmp_path,monkeypatch):
    import grenade.connection as connection
    (tmp_path/'.env').write_text('DEEPSEEK_API_KEY=file-test-value\n')
    monkeypatch.setattr(connection,'ROOT',tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY','environment-test-value')
    connection.load_settings()
    import os
    assert os.environ['DEEPSEEK_API_KEY']=='environment-test-value'


def test_cli_connection_check_creates_no_audit_database(tmp_path,monkeypatch,capsys):
    import pytest
    import grenade.runner as runner
    monkeypatch.setenv('AUDIT_DB',str(tmp_path/'must-not-exist.sqlite'))
    monkeypatch.setattr(runner,'load_settings',lambda:None)
    monkeypatch.setattr(runner,'check_key',lambda:{'authenticated':True,'http_status':200})
    monkeypatch.setattr('sys.argv',['runner','check'])
    with pytest.raises(SystemExit) as exit:
        runner.main()
    assert exit.value.code==0
    assert '200' in capsys.readouterr().out
    assert not (tmp_path/'must-not-exist.sqlite').exists()
