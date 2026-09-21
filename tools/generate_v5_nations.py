"""Serial private nation generation. No automatic retries or simulation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from homeostasis_v5.nation_generation import generate_next,review_last


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['generate-next','review'])
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--key-file',type=Path)
    p.add_argument('--review-file',type=Path)
    a=p.parse_args()
    if a.action=='generate-next':
        if a.key_file is None or a.key_file.is_symlink() or not a.key_file.is_file() or a.key_file.stat().st_mode & 0o077:
            raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
        result=generate_next(a.directory,credential=a.key_file.read_text().strip(),transport=httpx.HTTPTransport(retries=0))
    else:
        if a.review_file is None:raise ValueError('REVIEW_FILE_REQUIRED')
        review=json.loads(a.review_file.read_text())
        result=review_last(a.directory,accepted=review['accepted'],review_notes=review['notes'],
                           balance_review_notes=review.get('balance_review_notes'))
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result.get('status') in ('failure','interrupted','blocked') else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__}))
        raise SystemExit(1)
