"""Archive-only PUT to the exact storage URL returned by Kaggle in memory.

No account credential, cookies, redirects, automatic retries, or signed URL logs.
Call only after provider reconciliation and an authorized upload designation.
"""
import hashlib,os
from urllib.parse import urlsplit
import requests

ARCHIVE_SHA256='79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b'
ARCHIVE_BYTES=57711

def put_designated_archive(provider_url, archive):
    data=archive.read_bytes()
    if len(data)!=ARCHIVE_BYTES or hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA256:
        raise ValueError('Archive designation mismatch')
    u=urlsplit(provider_url)
    if (u.scheme!='https' or u.hostname not in {'storage.googleapis.com','www.googleapis.com'}
            or u.username or u.password or u.port not in (None,443) or u.fragment):
        raise ValueError('Unrecognized provider storage destination')
    # Exact URL and signing scope remain only in this function's memory.
    receipt={'destination_host':u.hostname,'destination_path':u.path,
             'destination_url_sha256':hashlib.sha256(provider_url.encode()).hexdigest(),
             'payload_sha256':ARCHIVE_SHA256,'payload_bytes':len(data),
             'authorization_header_sent':False,'redirects_allowed':False,'automatic_retries':0}
    with requests.Session() as session:
        session.trust_env=False  # Do not inherit netrc credentials or environment auth.
        # Use the runtime's ordinary managed network proxy explicitly, while
        # keeping netrc/environment authentication disabled.
        proxy=os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        if proxy:
            proxy_parts=urlsplit(proxy)
            if proxy_parts.scheme not in {'http','https'} or proxy_parts.username or proxy_parts.password:
                raise ValueError('Unexpected authenticated proxy configuration')
            session.proxies={'https':proxy}
        ca_bundle=os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE')
        if ca_bundle:
            session.verify=ca_bundle  # Use managed trust roots; never disable TLS verification.
        session.auth=None
        session.cookies.clear()
        prepared=session.prepare_request(requests.Request('PUT',provider_url,data=data,
            headers={'Content-Type':'application/octet-stream','Content-Length':str(len(data))}))
        if prepared.url!=provider_url or any(k.lower() in {'authorization','cookie','proxy-authorization'} for k in prepared.headers):
            raise ValueError('Upload request no longer matches unauthenticated exact scope')
        response=session.send(prepared,allow_redirects=False,timeout=(15,45))
        receipt['http_status']=response.status_code
        receipt['response_body_sha256']=hashlib.sha256(response.content).hexdigest()
        return receipt
