"""Safe credential diagnostics against DeepSeek's documented List Models endpoint."""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
MODELS_URL='https://api.deepseek.com/models'
MODELS_DOCUMENTATION='https://api-docs.deepseek.com/api/list-models'


def load_settings():
    """Resolve .env from the project directory, independently of the launching cwd."""
    load_dotenv(ROOT/'.env')


def project_path(value):
    path=Path(value)
    return path if path.is_absolute() else ROOT/path


def check_key(key=None,session=None):
    """Authenticate without saving credentials, response bodies, or model names."""
    key=key if key is not None else os.getenv('DEEPSEEK_API_KEY','')
    if not key or not key.strip():
        return {'status':'missing_key','authenticated':False,'http_status':None,
                'message':'Set DEEPSEEK_API_KEY in the project .env file, then restart Streamlit.'}
    transport=session or requests.Session()
    try:
        response=transport.get(MODELS_URL,headers={'Authorization':'Bearer '+key.strip()},
                               timeout=20,allow_redirects=False)
    except requests.Timeout:
        return {'status':'timeout','authenticated':False,'http_status':None,
                'message':'DeepSeek did not respond within 20 seconds. Retry the connection check.'}
    except requests.RequestException:
        return {'status':'network_error','authenticated':False,'http_status':None,
                'message':'Cannot reach api.deepseek.com. Check this machine\'s network policy and connection.'}
    code=response.status_code
    if code==200:
        try:
            data=response.json()
            valid=isinstance(data,dict) and isinstance(data.get('data'),list)
        except ValueError:
            valid=False
        if valid:
            return {'status':'authenticated','authenticated':True,'http_status':200,
                    'message':'DeepSeek accepted your key. Search and Fetch access must be tested separately.'}
        return {'status':'unexpected_response','authenticated':False,'http_status':code,
                'message':'The models endpoint returned an unexpected schema; authentication is not confirmed.'}
    messages={401:'DeepSeek rejected the key. Check the value in .env and restart Streamlit.',
              402:'DeepSeek reports insufficient balance. Check billing on your DeepSeek account.',
              403:'DeepSeek or the network gateway denied access; inspect account permissions and network policy.',
              429:'DeepSeek is rate limiting this account. Wait before retrying.'}
    return {'status':'http_error','authenticated':False,'http_status':code,
            'message':messages.get(code,f'DeepSeek models check returned HTTP {code}. Retry later or check service status.')}
