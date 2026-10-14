import copy
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import src.commands.reproduce_hf_groq as command
from src.commands.hf_qualification import load_revision
from src.commands.hf_reproduction import load_array_prompt, load_experiment, load_reproduction, reproduce

from tests.unit.test_hf_client import envelope, settings

ARM="minimal-array-prompt-256"


def test_frozen_array_changes_only_the_public_user_prompt():
    profile=load_array_prompt()
    arm=profile['arms'][ARM]
    case=copy.deepcopy(load_revision()['cases'][1])
    case['prompt']=arm['case']['prompt']
    assert arm['case']==case
    wire=copy.deepcopy(load_reproduction()['arms']['exact-relevance-512']['payload'])
    wire['max_tokens']=256
    wire['messages'][-1]['content']=case['prompt']
    assert wire==arm['payload'] and wire['response_format']['json_schema']['strict'] is True
    assert wire['response_format']['json_schema']['schema']['properties']['relevant_markers']['maxItems']==30


def test_array_freeze_rejects_modified_input(tmp_path):
    for path in Path('evaluation/week7_hf/array-prompt-v1').iterdir():
        (tmp_path/path.name).write_bytes(path.read_bytes())
    (tmp_path/'requests.json').write_text('{}')
    with pytest.raises(ValueError):
        load_array_prompt(tmp_path)
    with pytest.raises(ValueError):
        load_experiment('arbitrary')


@pytest.mark.anyio
@pytest.mark.parametrize('kind,category', [('pass','passed'),('mismatch','expected_mismatch'),('over-cap','schema_invalid'),('error','provider_json_validation')])
async def test_array_single_call_keeps_original_guards_and_content_privacy(stub_httpx,tmp_path,kind,category):
    config=settings().model_copy(update={'api_rate_limit_path':str(tmp_path/'quotas.db')})
    def handler(request):
        if kind=='error':
            return httpx.Response(400,json={'error':{'code':'json_validate_failed','message':'private-provider-text','failed_generation':'private-provider-text'}})
        content={'relevant_markers':['[1.1]'] if kind=='pass' else ['[1.1]']*31 if kind=='over-cap' else []}
        return httpx.Response(200,json=envelope(json.dumps(content)))
    calls=stub_httpx(handler)
    result=await reproduce(config,ARM,memory=lambda:4096,experiment='array-prompt-v1')
    assert len(calls)==1 and json.loads(calls[0].content)==load_array_prompt()['arms'][ARM]['payload']
    assert result['category']==category and result['qualification_accepted'] is False
    assert 'private-provider-text' not in json.dumps(result)


def test_array_offline_plan_never_reads_credentials_or_allowance(tmp_path,monkeypatch):
    output=tmp_path/'offline'
    monkeypatch.setattr('sys.argv',['reproduce','--snapshot','tests/test_output/week7-source-review-20261013-01',
        '--output',str(output),'--arm',ARM,'--experiment','array-prompt-v1'])
    for name in ('Settings','PilotAllowance','live_snapshot','provider_available','reproduce'):
        monkeypatch.setattr(command,name,Mock(side_effect=AssertionError('execution during plan')))
    command.main()
    metadata=json.loads((output/'metadata.json').read_text())
    assert metadata['experiment']=='array-prompt-v1' and metadata['outbound_budget']==1
    assert metadata['qualification_accepted'] is False and not metadata['inference_started']


@pytest.mark.parametrize('experiment,arm', [('reproduction-v1',ARM),('array-prompt-v1','exact-relevance-512'),('unknown',ARM)])
def test_array_arm_requires_its_explicit_frozen_experiment(tmp_path,monkeypatch,experiment,arm):
    output=tmp_path/'rejected'
    monkeypatch.setattr('sys.argv',['reproduce','--snapshot','tests/test_output/week7-source-review-20261013-01',
        '--output',str(output),'--arm',arm,'--experiment',experiment,'--execute'])
    monkeypatch.setattr(command,'Settings',Mock(side_effect=AssertionError('private settings read')))
    with pytest.raises(SystemExit):
        command.main()
    assert not output.exists()


def test_experiment_probe_preserves_complete_command_help(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['reproduce','--experiment','array-prompt-v1','--help'])
    with pytest.raises(SystemExit) as exc:
        command.main()
    assert exc.value.code==0
    help_text=capsys.readouterr().out
    assert '--snapshot' in help_text and '--execute' in help_text and ARM in help_text
