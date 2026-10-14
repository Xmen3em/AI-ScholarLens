import httpx
import pytest
from src.commands.evaluate_agent import MODEL_DIGESTS
from src.commands.evaluate_hf_agent import live_snapshot
from src.config import Settings


@pytest.mark.parametrize('valid_models', [True,False])
def test_local_snapshot_avoids_optional_zstd_negotiation_and_preserves_model_checks(monkeypatch,valid_models):
    requests=[]
    def handler(request):
        requests.append(request)
        if 'zstd' in request.headers.get('accept-encoding',''):
            raise httpx.ReadTimeout('synthetic incompatible compression')
        if request.url.path.endswith('/papers/'):
            result={'papers':[]}
        elif request.url.path.endswith('/_search'):
            result={'hits':{'hits':[]}}
        elif request.url.path.endswith('/_count'):
            result={'count':1221}
        elif request.url.path.endswith('/api/tags'):
            result={'models':[{'name':name,'digest':digest if valid_models else 'changed'} for name,digest in MODEL_DIGESTS.items()]}
        else:
            result={'paper-chunks-v2':{'aliases':{'paper-chunks':{}}}}
        return httpx.Response(200,json=result)
    original=httpx.Client.__init__
    def replaced(self,*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        original(self,*args,**kwargs)
    monkeypatch.setattr(httpx.Client,'__init__',replaced)
    config=Settings(_env_file=None)
    if valid_models:
        state,papers,chunks=live_snapshot(config)
        assert state['paper_count']==state['chunk_count']==0 and papers==chunks==[]
    else:
        with pytest.raises(ValueError,match='model digests differ'):
            live_snapshot(config)
    assert len(requests)==5 and all(request.url.host in {'127.0.0.1','localhost'} for request in requests)
