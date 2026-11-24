"""Explicit build/setup downloads. Inference never downloads model code or weights."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--minilm',action='store_true')
    p.add_argument('--repository')
    p.add_argument('--revision',help='Exact Hugging Face commit hash, required with --repository')
    p.add_argument('--destination')
    args=p.parse_args()
    if args.minilm:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        if os.environ.get('MINILM_CACHE_PATH'):
            ONNXMiniLM_L6_V2.DOWNLOAD_PATH=Path(os.environ['MINILM_CACHE_PATH'])
        # Chroma validates the model archive against its packaged SHA-256.
        ONNXMiniLM_L6_V2()._download_model_if_not_exists()
        print('Prepared MiniLM cache.')
    if args.repository:
        if not args.destination or not args.revision or not re.fullmatch('[0-9a-fA-F]{40}',args.revision):
            p.error('--repository requires --destination and an exact 40-character --revision')
        from huggingface_hub import snapshot_download
        root=Path(args.destination)
        snapshot_download(args.repository,revision=args.revision,local_dir=root,allow_patterns=['*.json','*.safetensors','*.txt','*.model'])
        files={f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file() and '.cache' not in f.parts and f.name!='jobpilot-model.json'}
        (root/'jobpilot-model.json').write_text(json.dumps({'repository':args.repository,'revision':args.revision,'files':files},sort_keys=True),encoding='utf-8')
        print('Prepared model and digest manifest. Evaluate quality/resources before enabling.')


if __name__=='__main__':main()
