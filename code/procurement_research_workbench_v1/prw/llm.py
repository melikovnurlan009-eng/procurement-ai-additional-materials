"""Opt-in JSON model transport with persistent request budget and no bundled credentials.
Supports a configured Chat-Completions-compatible endpoint. Does not assume a model exists.
"""
from __future__ import annotations
import json
import os
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from .io import digest, now, read_json, write_json, append_event

_JOURNAL_LOCK = threading.Lock()

class FatalModelError(RuntimeError):
    """Configuration/budget failure: stop and resume, never score fallback as a valid run."""

class BudgetExhausted(FatalModelError):
    pass

class Budget:
    def __init__(self, path: str | Path, max_requests: int):
        self.path=Path(path); self.max_requests=max_requests; self.lock=threading.Lock()
        self.count=read_json(self.path).get('requests_reserved',0) if self.path.exists() else 0
    def reserve(self):
        with self.lock:
            if self.count>=self.max_requests: raise BudgetExhausted('Model request budget exhausted; checkpoint retained')
            self.count+=1
            write_json(self.path,{'requests_reserved':self.count,'max_requests':self.max_requests,'updated':now()})

class HTTPJsonModel:
    def __init__(self, config: dict, budget: Budget, journal: str | Path, allow_network: bool=False):
        self.config=config; self.budget=budget; self.journal=Path(journal); self.allow_network=allow_network
        self.model=config.get('model') or os.getenv(config.get('model_env','PRW_MODEL'),'')
        self.endpoint=config.get('endpoint') or os.getenv(config.get('endpoint_env','PRW_ENDPOINT'),'https://api.openai.com/v1/chat/completions')
        self.key_env=config.get('api_key_env','OPENAI_API_KEY')
        if not self.model: raise ValueError(f"Set {config.get('model_env','PRW_MODEL')} to an accessible API model identifier")
        if not self.endpoint.startswith('https://') and not self.endpoint.startswith(('http://localhost:','http://127.0.0.1:')):
            raise ValueError('Endpoint must use HTTPS except for an explicitly local service')
        self.identity={'model':self.model,'endpoint':self.endpoint,'parameters':config.get('parameters',{})}
        self._lock=_JOURNAL_LOCK
    def preflight(self):
        if not self.allow_network: raise FatalModelError('Network/model execution is opt-in; use --allow-network after cost review')
        if not os.getenv(self.key_env, '') and not self.endpoint.startswith(('http://localhost:', 'http://127.0.0.1:')):
            raise FatalModelError(f'Missing API credential environment variable {self.key_env}')

    def complete(self, system: str, payload: dict) -> dict:
        self.preflight()
        text=json.dumps(payload,ensure_ascii=False)
        if len(system)+len(text)>self.config.get('max_input_chars',100000):
            raise ValueError('Input exceeds configured size; segment explicitly, never silently truncate evidence')
        key=os.getenv(self.key_env,'')
        if not key and not self.endpoint.startswith(('http://localhost:','http://127.0.0.1:')):
            raise ValueError(f'Missing API credential environment variable {self.key_env}')
        body={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':text}],
              'response_format':{'type':'json_object'},**self.config.get('parameters',{})}
        # Explicit opt-out supports endpoints without response_format. Local JSON validation remains mandatory.
        if self.config.get('omit_response_format'): body.pop('response_format',None)
        request_hash=digest(body)
        max_attempts=1+self.config.get('retries',1)
        last=None
        for attempt in range(max_attempts):
            self.budget.reserve(); start=time.monotonic()
            req=urllib.request.Request(self.endpoint, json.dumps(body).encode(), {'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
            try:
                with urllib.request.urlopen(req,timeout=self.config.get('timeout_seconds',60)) as response:
                    result=json.loads(response.read())
                choice=result['choices'][0]
                if choice.get('finish_reason') in ('length','content_filter'): raise ValueError('Model output incomplete or filtered')
                message=choice['message']
                if message.get('refusal'): raise ValueError('Model refused request')
                content=message.get('content')
                parsed=json.loads(content)
                if not isinstance(parsed,dict): raise ValueError('Expected JSON object')
                with self._lock:
                    append_event(self.journal,{'request_hash':request_hash,'model_identity':self.identity,
                      'duration_seconds':time.monotonic()-start,'usage':result.get('usage'),
                      'response_id':result.get('id'),'returned_model':result.get('model'),
                      'status':'success','response':parsed})
                return parsed
            except urllib.error.HTTPError as exc:
                last=exc
                with self._lock: append_event(self.journal,{'request_hash':request_hash,'status':'http_error','code':exc.code,'attempt':attempt})
                if exc.code in (401,403,404): raise FatalModelError(f'Model endpoint/access failure: HTTP {exc.code}') from exc
                if exc.code not in (429,500,502,503,504) or attempt+1>=max_attempts:
                    raise FatalModelError(f'Model transport failed after bounded attempts: HTTP {exc.code}') from exc
                time.sleep(min(8,2**attempt))
            except (urllib.error.URLError, TimeoutError) as exc:
                with self._lock: append_event(self.journal,{'request_hash':request_hash,'status':'transport_error','error_type':type(exc).__name__})
                raise FatalModelError('Model service unreachable; resume when the configured service is available') from exc
            except Exception as exc:
                with self._lock: append_event(self.journal,{'request_hash':request_hash,'status':'error','error_type':type(exc).__name__})
                raise
        raise RuntimeError('Model call failed') from last
