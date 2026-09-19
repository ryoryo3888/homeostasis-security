"""Real SDK serialization with an exclusively in-memory HTTP transport.

No live client factory, secret loading, or paid execution entry point exists.
The journal is a conservative POSIX/SQLite attempt ledger: an interrupted or
failed attempt blocks later requests until an explicit new protocol is chosen.
"""
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .agent_adapter import RESPONSE, _object
from .autonomous import INITIATIVE_RESPONSE
from .choices import ensure, check, TechnicalFailure
from .contracts import canonical, digest, ID

SYSTEM_INSTRUCTION = '''あなたは合成世界の独立した一国家です。requestのstate_idだけについて判断します。
観測、在庫、需要、生産、資源依存、輸送制約を踏まえ、自国の必須機能と意思決定の余地、他国と世界への影響を検討してください。
協力、拒否、条件付き取引、不作為のいずれも予定されていません。強硬・慎重・協力・自立をあらかじめ善悪に分類しません。
initiativeでは自国が所有するopportunityを選び、数量、最低成立量、部分履行、成立条件を自ら提案できます。
他国の提案を予想して成立したと扱わず、他国の同意を作らないでください。空のinitiativesも有効です。
未実装の行動や新しい法則の提案はextension_requestsに記録できますが、そのTURNに実行されたとは扱いません。
consentでは提示された実際の取引だけについて受諾・拒否を判断します。ここで新しい取引や条件を密かに書き加えてはいけません。
経路や画像の装飾を実流量と解釈せず、回復・危機・協力の結末を予定しません。世界の状態を直接書き換えてはいけません。
指定されたJSONだけを返し、request_digestとstate_idを正確に返してください。理由は公開用の簡潔な説明とし、内部推論は出力しないでください。
'''


class AttemptJournal:
    """Reserve attempts and retain SDK replies separately from public summaries.

    Reply payloads exclude transport headers and are never sent to another Agent.
    They are SDK-decoded evidence, not original HTTP bytes or research results.
    """
    def __init__(self, path, *, configuration):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.configuration=json.loads(canonical(configuration))
        self.configuration_hash=digest(self.configuration)
        with closing(self._connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS configuration (id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (request_digest TEXT PRIMARY KEY, state TEXT NOT NULL, phase TEXT NOT NULL, status TEXT NOT NULL, usage TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS responses (request_digest TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO configuration VALUES (1,?)',(self.configuration_hash,))
            ensure(db.execute('SELECT digest FROM configuration').fetchone()[0]==self.configuration_hash,'JOURNAL_CONFIGURATION_MISMATCH')

    def _connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def reserve(self,request):
        ensure(digest(self.configuration)==self.configuration_hash,'JOURNAL_CONFIGURATION_CHANGED')
        db=self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            ensure(db.execute('SELECT digest FROM configuration').fetchone()[0]==self.configuration_hash,'JOURNAL_CONFIGURATION_MISMATCH')
            ensure(not db.execute("SELECT 1 FROM attempts WHERE status!='response_validated' LIMIT 1").fetchone(),
                   'UNRESOLVED_ATTEMPT_REQUIRES_REVIEW')
            ensure(not db.execute('SELECT 1 FROM attempts WHERE request_digest=?',(request['request_digest'],)).fetchone(),
                   'DUPLICATE_DISPATCH_FORBIDDEN')
            ensure(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]<self.configuration['max_calls'],'CALL_LIMIT_EXCEEDED')
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,NULL)',
                       (request['request_digest'],request['state_id'],request['phase'],'reserved'))
            db.commit()
        finally:
            db.close()

    def record_response(self,key,response):
        """Commit once before text/schema validation; never backfill old attempts."""
        payload=response.model_dump_json(exclude={'sdk_http_response'},exclude_none=True)
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM attempts WHERE request_digest=?',(key,)).fetchone()
            ensure(row is not None and row[0]=='reserved','ATTEMPT_NOT_RESERVED')
            ensure(not db.execute('SELECT 1 FROM responses WHERE request_digest=?',(key,)).fetchone(),
                   'RESPONSE_ALREADY_RECORDED')
            db.execute('INSERT INTO responses VALUES (?,?)',(key,payload))

    def response_records(self):
        """Explicit local audit access; absent receipts remain absent."""
        with closing(self._connect()) as db, db:
            return [{'request_digest':key,'sdk_response':json.loads(payload)}
                    for key,payload in db.execute('SELECT request_digest,payload FROM responses ORDER BY rowid')]

    def finish(self,key,status,usage):
        ensure(status in ('response_validated','failed'),'INVALID_ATTEMPT_STATUS')
        with closing(self._connect()) as db, db:
            if status=='response_validated':
                ensure(db.execute('SELECT 1 FROM responses WHERE request_digest=?',(key,)).fetchone(),
                       'RESPONSE_NOT_RECORDED')
            result=db.execute("UPDATE attempts SET status=?,usage=? WHERE request_digest=? AND status='reserved'",
                              (status,canonical(usage),key))
            ensure(result.rowcount==1,'ATTEMPT_NOT_RESERVED')

    def records(self):
        with closing(self._connect()) as db, db:
            return [{'request_digest':r[0],'state_id':r[1],'phase':r[2],'status':r[3],
                     'usage':None if r[4] is None else json.loads(r[4])}
                    for r in db.execute('SELECT * FROM attempts ORDER BY rowid')]


class OfflineGeminiExchange:
    """Uses google-genai and httpx.MockTransport; all replies are synthetic.

    Passing a handler cannot enable network dispatch in this class. The host
    handler is trusted test code, not executable model output. Model name and
    remote schema support are not verified by an offline serialization check.
    """
    def __init__(self, *, handler, journal_path, model, max_calls,
                 max_input_bytes=500000, max_output_tokens=4096):
        from google import genai
        from google.genai import types
        import httpx
        import importlib.metadata
        ensure(type(model) is str and model and '/' not in model,'INVALID_MODEL_ID')
        for value in (max_calls,max_input_bytes,max_output_tokens):
            ensure(type(value) is int and value>0,'INVALID_BUDGET_LIMIT')
        self.configuration={'mode':'offline_mock_transport','model':model,'max_calls':max_calls,
                            'max_input_bytes':max_input_bytes,'max_output_tokens':max_output_tokens,
                            'sdk_version':importlib.metadata.version('google-genai'),
                            'prompt_digest':digest(SYSTEM_INSTRUCTION),
                            'schema_digest':digest([RESPONSE,INITIATIVE_RESPONSE]),'retry_attempts':1}
        self.journal=AttemptJournal(journal_path,configuration=self.configuration)
        self.wire_requests=[]
        def intercept(request):
            ensure(request.url.host=='v3-offline.invalid','UNEXPECTED_OFFLINE_ENDPOINT')
            body=json.loads(request.content)
            # Deliberately retain body only in test memory, never HTTP headers.
            self.wire_requests.append(deepcopy(body))
            return handler(request)
        self.http=httpx.Client(transport=httpx.MockTransport(intercept),trust_env=False)
        # Short, visibly fictional dummy value; no real credential is loaded.
        self.client=genai.Client(vertexai=False,api_key='offline-dummy',
            http_options=types.HttpOptions(base_url='https://v3-offline.invalid',api_version='v1beta',
                httpx_client=self.http,retry_options=types.HttpRetryOptions(attempts=1),timeout=30000))

    def close(self):
        self.client.close(); self.http.close()

    def __call__(self,raw):
        from google.genai import types
        ensure(digest(self.configuration)==self.journal.configuration_hash,'TRANSPORT_CONFIGURATION_CHANGED')
        ensure(digest(SYSTEM_INSTRUCTION)==self.configuration['prompt_digest'] and
               digest([RESPONSE,INITIATIVE_RESPONSE])==self.configuration['schema_digest'],'PROMPT_OR_SCHEMA_CHANGED')
        ensure(type(raw) is str and len(raw.encode('utf-8'))<=self.configuration['max_input_bytes'],'INPUT_LIMIT_EXCEEDED')
        request=json.loads(raw,object_pairs_hook=_object)
        ensure(set(request)=={'version','phase','state_id','observation_digest','observation','payload','request_digest'},'INVALID_REQUEST')
        check(ID,request['state_id'])
        ensure(request['version']=='v3' and request['phase'] in ('initiative','choice','consent'),'INVALID_PHASE')
        ensure(request['observation_digest']==digest(request['observation']),'REQUEST_OBSERVATION_MISMATCH')
        ensure(request['request_digest']==digest({k:v for k,v in request.items() if k!='request_digest'}),'REQUEST_DIGEST_MISMATCH')
        schema=INITIATIVE_RESPONSE if request['phase']=='initiative' else RESPONSE
        config=types.GenerateContentConfig(response_mime_type='application/json',response_json_schema=schema,
            system_instruction=SYSTEM_INSTRUCTION,temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=self.configuration['max_output_tokens'])
        self.journal.reserve(request)
        usage={'input_tokens':None,'output_tokens':None,'thought_tokens':None,'total_tokens':None}
        try:
            response=self.client.models.generate_content(model=self.configuration['model'],contents=raw,config=config)
            self.journal.record_response(request['request_digest'],response)
            metadata=response.usage_metadata
            if metadata is not None:
                for key,attribute in [('input_tokens','prompt_token_count'),('output_tokens','candidates_token_count'),
                                      ('thought_tokens','thoughts_token_count'),('total_tokens','total_token_count')]:
                    value=getattr(metadata,attribute,None)
                    usage[key]=value if type(value) is int and value>=0 else None
            ensure(response.candidates and len(response.candidates)==1,'MISSING_OR_AMBIGUOUS_CANDIDATE')
            ensure(response.candidates[0].finish_reason=='STOP','INCOMPLETE_PROVIDER_RESPONSE')
            text=response.text
            ensure(type(text) is str and len(text.encode('utf-8'))<=65536,'INVALID_RESPONSE_SIZE')
            answer=json.loads(text,object_pairs_hook=_object); check(schema,answer)
            ensure(answer['state_id']==request['state_id'] and answer['request_digest']==request['request_digest'],
                   'PROVIDER_BINDING_MISMATCH')
        except Exception:
            self.journal.finish(request['request_digest'],'failed',usage)
            raise TechnicalFailure('SDK_OR_RESPONSE_FAILURE_NO_RETRY') from None
        self.journal.finish(request['request_digest'],'response_validated',usage)
        return text
