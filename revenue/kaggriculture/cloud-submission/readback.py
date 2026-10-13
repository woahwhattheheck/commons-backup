"""Read owner submission state with the configured official Kaggle client."""
import contextlib,datetime,hashlib,io,json,os
from pathlib import Path

OPERATION_ID='titan-kaggriculture-frontier-20260907-01'
COMPETITION='kaggriculture'
KERNEL='tokenjunkielabs/tokenjunkielabs-farm-manager'
OUT=Path(os.environ.get('KAG_SUBMISSION_READBACK_DIR','submission-readback'))


def safe_call(name, fn):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            value=fn()
        return {'status':'SUCCESS','value':value}
    except Exception as exc:
        response=getattr(exc,'response',None)
        return {'status':'FAILED','exception_type':type(exc).__name__,
                'http_status':getattr(response,'status_code',None)}


def serial(value):
    if hasattr(value,'to_dict'):return value.to_dict()
    if isinstance(value,list):return [serial(v) for v in value]
    return value


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        from kaggle.api.kaggle_api_extended import KaggleApi
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
        api=KaggleApi();api.authenticate()
    report={'operation_id':OPERATION_ID,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'competition':COMPETITION,'kaggle_cli_version':'2.2.4','kagglesdk_version':'0.1.37'}
    report['limits']=safe_call('limits',lambda:serial(api.competition_get_submission_limits(COMPETITION)))
    report['submissions']=safe_call('submissions',lambda:serial(api.competition_submissions(COMPETITION,page_size=100)))
    report['competition']=safe_call('competition',lambda:serial(api.competitions_list(search=COMPETITION,page_size=20)))
    report['kernel_status']=safe_call('kernel_status',lambda:serial(api.kernels_status(KERNEL)))
    def kernel_metadata():
        with api.build_kaggle_client() as client:
            req=ApiGetKernelRequest();req.user_name='tokenjunkielabs';req.kernel_slug='tokenjunkielabs-farm-manager'
            response=client.kernels.kernels_api_client.get_kernel(req)
            blob=serial(response.blob)
            (OUT/'owner-kernel-source.json').write_text(json.dumps(blob,default=str))
            return {'metadata':serial(response.metadata),'source_blob_sha256':hashlib.sha256(json.dumps(blob,sort_keys=True,default=str).encode()).hexdigest()}
    report['owner_kernel']=safe_call('owner_kernel',kernel_metadata)
    def pages():
        rows=api.competition_list_pages(COMPETITION)
        public=[]
        for p in rows:
            content=p.content
            (OUT/('page-'+p.name+'.txt')).write_text(content)
            public.append({'name':p.name,'is_published':p.is_published,'bytes':len(content.encode()),'sha256':hashlib.sha256(content.encode()).hexdigest()})
        return public
    report['pages']=safe_call('pages',pages)
    (OUT/'readback.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps(report,default=str))

if __name__=='__main__':main()
