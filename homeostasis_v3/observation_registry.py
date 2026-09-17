"""Pending V3 evidence contract. Never modifies the current experiment registry.

The current registry only admits reviewed V1/V2/shared artifacts. This produces
an explicit proposal for future V3 review, not a registration or publication.
"""
import re
from pathlib import PurePosixPath
from .choices import ensure
from .contracts import canonical, digest
from .observation import verify_observation
from tools.secret_scan import has_secret


def pending_evidence(record, sources, *, path):
    verify_observation(record, sources)
    ensure(type(path) is str and bool(re.fullmatch(r'[A-Za-z0-9_./-]+',path)), 'UNSAFE_OBSERVATION_PATH')
    p=PurePosixPath(path)
    ensure(not p.is_absolute() and path==str(p) and not any(x in ('.','..') or x.startswith('.') for x in p.parts), 'UNSAFE_OBSERVATION_PATH')
    ensure(not re.search(r'secret|credential|api[_-]?key|private|password',path,re.I) and p.suffix=='.json', 'UNSAFE_OBSERVATION_PATH')
    ensure(not has_secret(canonical(record)), 'OBSERVATION_SECRET_REJECTED')
    return {'contract_version':'v3-observation-evidence-1','version':'v3','artifact_type':'observation',
            'artifact_class':record['artifact_class'],'reference':{'path':path,'pointer':''},
            'canonical_sha256':digest(record),'observation_digest':record['observation_digest'],
            'checkpoint_digest':record['checkpoint_digest'],'metric_definitions_digest':record['metric_definitions_digest'],
            'source_eligible':False,'registration_status':'not_registered','publication_status':'withheld',
            'required_review':['V3 registry schema support','tracked existing non-symlink file',
                               'exact file-byte SHA256 allowlist approval','source provenance and classification','independent publication approval']}
