"""SLAB-018: explicit NeMo/PEFT fixture-only training and fresh reload evaluation."""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import time

ROOT = Path('/work')
DATA = ROOT / 'fixtures'
MODEL = Path('/model')
SEED = 818


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def stop_check():
    if (ROOT / 'STOP').exists():
        raise RuntimeError('STOP file present')
    if time.time() >= 1793440800:  # 2026-10-31T10:00:00Z
        raise RuntimeError('SLAB-018 absolute deadline')


def load_data(name, tokenizer):
    rows = [json.loads(line) for line in (DATA / name).read_text().splitlines()]
    assert len(rows) == (200 if name == 'train.jsonl' else 20)
    assert len({r['row_id'] for r in rows}) == len(rows)
    result = []
    for row in rows:
        assert row['fixture'] is True
        messages = [{'role': 'system', 'content': row['system']},
                    {'role': 'user', 'content': row['instruction']}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,return_dict=False)
        full = tokenizer.apply_chat_template(messages + [{'role': 'assistant', 'content': row['output']}],
                                             tokenize=True, add_generation_prompt=False,return_dict=False)
        assert isinstance(prompt,list) and isinstance(full,list)
        # Direct original-row tokenization. Never let a dataset silently replace
        # an example whose response mask vanished through truncation.
        assert full[:len(prompt)] == prompt, row['row_id']
        assert 0 < len(prompt) < len(full) <= 512, (row['row_id'],len(prompt),len(full))
        labels = [-100] * len(prompt) + full[len(prompt):]
        assert tokenizer.decode(full[len(prompt):]).startswith(row['output'])
        result.append((row, prompt, full, labels))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['validate', 'train', 'evaluate'])
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    stop_check()
    import torch
    from transformers import AutoTokenizer
    torch.manual_seed(SEED)
    random.seed(SEED)
    torch.set_num_threads(8)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True, trust_remote_code=False)
    train = load_data('train.jsonl', tokenizer)
    evaluation = load_data('eval.jsonl', tokenizer)
    manifest = json.loads((DATA / 'DATA-MANIFEST.json').read_text())
    for name, expected in manifest['data_files'].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected
    write_json(out / 'tokenization.json', {
        'train': [{'row_id': r[0]['row_id'], 'tokens': len(r[2]),
                   'answer_tokens': sum(x != -100 for x in r[3])} for r in train],
        'eval': [{'row_id': r[0]['row_id'], 'tokens': len(r[2]),
                  'answer_tokens': sum(x != -100 for x in r[3])} for r in evaluation],
        'truncated': 0, 'substituted': 0, 'empty_answer_masks': 0})
    if args.mode == 'validate':
        from nemo_automodel._transformers.auto_model import NeMoAutoModelForCausalLM
        from peft import PeftModel,get_peft_model,get_peft_model_state_dict
        print(json.dumps({'validated_train_rows':200, 'validated_eval_rows':20,
                         'nemo_import':NeMoAutoModelForCausalLM.__name__,'uid':os.geteuid()}), flush=True)
        return
    assert torch.cuda.is_available()
    from nemo_automodel._transformers.auto_model import NeMoAutoModelForCausalLM
    from peft import LoraConfig, PeftModel, get_peft_model, get_peft_model_state_dict
    started = time.monotonic()
    model = NeMoAutoModelForCausalLM.from_pretrained(
        str(MODEL), force_hf=True, use_liger_kernel=False, use_sdpa_patching=False,
        attn_implementation='sdpa', torch_dtype=torch.bfloat16,
        local_files_only=True, trust_remote_code=False).to('cuda')
    model.config.use_cache = False
    runtime = {'seed':SEED,'torch':torch.__version__,'cuda':torch.version.cuda,
               'gpu':torch.cuda.get_device_name(0),'nemo_automodel':importlib.metadata.version('nemo-automodel'),
               'peft':importlib.metadata.version('peft'),'transformers':importlib.metadata.version('transformers'),
               'model_class':type(model).__name__,'fixture_only':True,'mode':args.mode}
    write_json(out / ('runtime-' + args.mode + '.json'),runtime)
    def tensor(value):
        return torch.tensor([value],dtype=torch.long,device='cuda')
    if args.mode == 'train':
        model = get_peft_model(model,LoraConfig(
            r=8,lora_alpha=32,lora_dropout=0.0,bias='none',task_type='CAUSAL_LM',
            target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj']))
        model.train()
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.enable_input_require_grads()
        params = {name:p for name,p in model.named_parameters() if p.requires_grad}
        assert params and all('lora_' in name for name in params)
        before = {name:p.detach().float().cpu().clone() for name,p in params.items()}
        optimizer = torch.optim.AdamW(list(params.values()),lr=2e-4,weight_decay=0.0)
        order = list(range(200))
        random.Random(SEED).shuffle(order)
        steps = []
        for step in range(20):
            stop_check()
            optimizer.zero_grad(set_to_none=True)
            losses = []
            for idx in order[step*10:(step+1)*10]:
                stop_check()
                row,_,ids,labels = train[idx]
                loss = model(input_ids=tensor(ids),attention_mask=torch.ones_like(tensor(ids)),
                             labels=tensor(labels)).loss
                assert torch.isfinite(loss).item()
                losses.append(float(loss.detach()))
                (loss / 10).backward()
            grad = float(torch.nn.utils.clip_grad_norm_(list(params.values()),1.0))
            assert math.isfinite(grad)
            optimizer.step()
            torch.cuda.synchronize()
            receipt = {'optimizer_step':step+1,'rows':[train[i][0]['row_id'] for i in order[step*10:(step+1)*10]],
                       'mean_loss':sum(losses)/10,'grad_norm':grad,'elapsed_seconds':time.monotonic()-started}
            steps.append(receipt)
            print(json.dumps(receipt),flush=True)
            with (out / 'train-steps.jsonl').open('a') as handle:
                handle.write(json.dumps(receipt)+'\n')
        stop_check()
        delta = {name:float((p.detach().float().cpu()-before[name]).abs().max()) for name,p in params.items()}
        assert all(math.isfinite(value) for value in delta.values())
        assert all(torch.isfinite(p).all().item() for p in params.values())
        assert any(value > 0 for value in delta.values())
        model.save_pretrained(out / 'adapter',safe_serialization=True)
        adapter_files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (out / 'adapter').iterdir() if p.is_file()}
        assert 'adapter_config.json' in adapter_files and 'adapter_model.safetensors' in adapter_files
        write_json(out / 'training-result.json', {'optimizer_steps':20,'examples_consumed':200,
                   'trainable_parameters':sum(p.numel() for p in params.values()),
                   'changed_tensors':sum(v>0 for v in delta.values()),'adapter_files':adapter_files,
                   'elapsed_seconds':time.monotonic()-started,'loss_first':steps[0]['mean_loss'],
                   'loss_last':steps[-1]['mean_loss'],'claim':'Fixture-label adapter plumbing only'})
    else:
        saved = json.loads((out / 'training-result.json').read_text())
        for name, expected in saved['adapter_files'].items():
            assert hashlib.sha256((out/'adapter'/name).read_bytes()).hexdigest() == expected
        def evaluate(current, label):
            current.eval()
            values = []
            for row,prompt,ids,labels in evaluation:
                stop_check()
                with torch.inference_mode():
                    nll = float(current(input_ids=tensor(ids),attention_mask=torch.ones_like(tensor(ids)),
                                        labels=tensor(labels)).loss)
                    generated = current.generate(input_ids=tensor(prompt),attention_mask=torch.ones_like(tensor(prompt)),
                           max_new_tokens=80,do_sample=False,use_cache=True,pad_token_id=tokenizer.eos_token_id)
                text = tokenizer.decode(generated[0,len(prompt):],skip_special_tokens=True)
                try:
                    predicted=json.loads(text)
                except (ValueError,TypeError):
                    predicted=None
                values.append({'row_id':row['row_id'],'output':text,'expected':row['output'],
                               'exact_json_match':predicted == json.loads(row['output']),'target_nll':nll})
                print(json.dumps({'mode':label,**values[-1]}),flush=True)
            return values
        base = evaluate(model,'base')
        model = PeftModel.from_pretrained(model,str(out/'adapter'),is_trainable=False,local_files_only=True)
        from safetensors.torch import load_file
        expected_tensors=load_file(str(out/'adapter/adapter_model.safetensors'))
        actual_tensors=get_peft_model_state_dict(model)
        assert set(expected_tensors)==set(actual_tensors)
        for key,expected in expected_tensors.items():
            actual=actual_tensors[key].detach().cpu()
            assert actual.shape==expected.shape and torch.isfinite(actual).all().item()
            assert torch.equal(actual.to(expected.dtype),expected),key
        write_json(out/'reload-tensors.json',{'equal_keys_shapes_values':True,'tensors':len(expected_tensors)})
        adapted = evaluate(model,'adapter')
        write_json(out / 'evaluation.json', {'base':base,'adapter':adapted,
                   'changed_outputs':sum(a['output']!=b['output'] for a,b in zip(base,adapted)),
                   'base_exact':sum(r['exact_json_match'] for r in base),
                   'adapter_exact':sum(r['exact_json_match'] for r in adapted),
                   'base_mean_target_nll':sum(r['target_nll'] for r in base)/20,
                   'adapter_mean_target_nll':sum(r['target_nll'] for r in adapted)/20,
                   'elapsed_seconds':time.monotonic()-started,
                   'scope':'Same-family fixture plumbing/label evaluation; no scientific generalization claim'})


if __name__ == '__main__':
    try:
        main()
    finally:
        # The pinned NeMo image's /opt/Automodel sources are root-readable only.
        # Restore ownership only for this invocation's owned output subtree.
        if os.geteuid() == 0:
            import sys
            if '--output' in sys.argv:
                destination=Path(sys.argv[sys.argv.index('--output')+1]).resolve()
                if destination.parent==ROOT and (destination.name.startswith('attempt-') or destination.name=='tokenization-preflight'):
                    for path in [destination,*destination.rglob('*')]:
                        if not path.is_symlink():
                            os.chown(path,1000,1000)
