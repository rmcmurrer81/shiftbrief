"""Lazy optional Strands provider. Startup performs no credential lookup or network call."""
import os
import re
from urllib.parse import urlparse

def runtime_settings(provider=None):
    provider = provider or os.environ.get('SHIFTBRIEF_AGENT_PROVIDER', 'ollama')
    if provider == 'bedrock':
        region = os.environ.get('SHIFTBRIEF_BEDROCK_REGION', '').strip()
        model = os.environ.get('SHIFTBRIEF_BEDROCK_MODEL', '').strip()
        if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d+', region):
            raise ValueError('Set SHIFTBRIEF_BEDROCK_REGION to your enabled AWS region before choosing cloud AI.')
        if not model or len(model)>300 or not re.fullmatch(r'[A-Za-z0-9._:/-]+',model):
            raise ValueError('Set SHIFTBRIEF_BEDROCK_MODEL to your enabled small, tool-capable Bedrock model or inference-profile ID.')
        if not all(os.environ.get(k) for k in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY')):
            raise ValueError('Configure temporary AWS credentials in this launch environment before choosing cloud AI. Credentials are not saved in team files.')
        return {'provider':provider,'model':model,'region':region,'url':'AWS Bedrock in '+region}
    if provider != 'ollama':
        raise ValueError('Choose an explicitly configured Ollama or Bedrock provider.')
    url=os.environ.get('SHIFTBRIEF_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('SHIFTBRIEF_OLLAMA_URL must name a local Ollama HTTP service.')
    model=os.environ.get('SHIFTBRIEF_MODEL','qwen3.5:9b').strip()
    if not model or len(model)>150:
        raise ValueError('SHIFTBRIEF_MODEL must name an installed model.')
    return {'provider':provider,'url':url,'model':model}

def configured():
    if os.environ.get('SHIFTBRIEF_AGENT_PROVIDER') not in ('ollama','bedrock'):
        return False
    try: runtime_settings()
    except ValueError:return False
    return True

def make_model(settings, *, temperature, max_tokens):
    if settings['provider']=='ollama':
        from strands.models.ollama import OllamaModel
        return OllamaModel(host=settings['url'],model_id=settings['model'],temperature=temperature,
            max_tokens=max_tokens,options={'num_ctx':12288},additional_args={'think':False,'keep_alive':0},
            ollama_client_args={'timeout':120,'trust_env':False})
    from strands.models.bedrock import BedrockModel
    import boto3
    import botocore.session
    from botocore.config import Config
    # Explicit environment credentials only: no profile/EC2 lookup, key file or custom endpoint.
    core=botocore.session.Session()
    core.set_config_variable('config_file',os.devnull)
    core.set_config_variable('credentials_file',os.devnull)
    core.set_config_variable('profile',None)
    session=boto3.Session(botocore_session=core,aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
        aws_session_token=os.environ.get('AWS_SESSION_TOKEN'),
        region_name=settings['region'])
    return BedrockModel(boto_session=session,model_id=settings['model'],temperature=temperature,
        max_tokens=max_tokens,boto_client_config=Config(connect_timeout=10,read_timeout=120,
            retries={'total_max_attempts':1},ignore_configured_endpoint_urls=True))
