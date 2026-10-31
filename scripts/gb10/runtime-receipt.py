import importlib.metadata
import json
import torch
print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,
                  'gpu':torch.cuda.get_device_name(0),
                  'vllm':importlib.metadata.version('vllm'),
                  'transformers':importlib.metadata.version('transformers'),
                  'scope':'Measured inside the actual serving container; no model weights loaded by this probe'}))
