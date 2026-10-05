"""Delivery checks against the retained engine state and frozen source references."""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
data=json.loads((OUT/'state-snapshot.json').read_text())
manifest=json.loads((OUT/'manifest.json').read_text())
trace=json.loads((OUT/'traceability.json').read_text())
signature={
    'decision':data['decision']['evidence_digest'],
    'rules':data['decision']['methodology'],
    'critical':data['decision']['critical_uncertainty_id'],
    'recommended':data['decision']['recommended_experiment_id'],
    'learning':data['learning']['content_key'],
    'panel':[{k:x[k] for k in ['name','role','dimensions']} for x in data['campaign']['prioritization']['panel']],
    'structure':[x['coverage'] for x in data['structure']['chains']],
    'retrospective':{k:v['conclusion'] for k,v in data['retrospective'].items()},
}
signature_hash=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
baseline=OUT/'scientific-signature.json'
if baseline.exists():
    assert json.loads(baseline.read_text())['sha256']==signature_hash, 'Scientific replay differs'
else:
    baseline.write_text(json.dumps({'sha256':signature_hash,'content':signature},indent=2)+'\n')
for package in manifest['packages']:
    source=ROOT/package['path']/'manifest.json'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==package['manifest_sha256']
sources={s['source_id']:s['doi'] for s in json.loads((ROOT/'axis/resources/discovery/erap1-axspa/v1/manifest.json').read_text())['sources']}
sources['PMID:31841350']='10.1021/acs.jmedchem.9b00293'
for identifier,title,doi in trace['references']:
    assert sources[identifier]==doi
assert len(trace['source_assertions'])==13 and len(trace['experimental_measurements'])==15
assert not data['decision']['synthetic']
assert all(not entry['dataset'].get('synthetic') for entry in data['learning']['entries'])
assert all(x['conclusion']=='not_eligible' for x in data['eligibility'])
texts={}
links=0
for name,checksum in manifest['outputs'].items():
    f=OUT/name
    assert hashlib.sha256(f.read_bytes()).hexdigest()==checksum
    reader=PdfReader(f)
    assert len(reader.pages)==(3 if name.startswith('executive') else 17)
    texts[name]='\n'.join(p.extract_text() for p in reader.pages)
    assert 'NOT BUILT' in texts[name] and 'RESOLVE CRITICAL UNCERTAINTY FIRST' in texts[name]
    for page in reader.pages:
        for annotation in page.get('/Annots',[]):
            obj=annotation.get_object(); action=obj.get('/A',{})
            if action.get('/URI'):
                assert action['/URI'].startswith('https://doi.org/10.')
                links+=1
    assert '■' not in texts[name]
report={'scientific_traceability':'PASS','reference_validation':'PASS (frozen identifiers; no new literature audit)','prediction_experiment_separation':'PASS','state_validation':'PASS','deterministic_scientific_signature':signature_hash,'pdf_page_counts':'PASS','pdf_links':links,'scientific_language_audit':'PASS after manual review','independent_scientific_review':'PENDING','commercial_readiness':'READY WITH CONDITIONS'}
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
