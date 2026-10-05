"""Replay frozen ERAP1 evidence offline; no synthetic experiment results imported."""
import json
import socket
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from axis.storage import EvidenceStore
from axis.discovery.curation import import_curated_erap1
from axis.targets.identity import TargetIdentityService
from axis.structures.service import StructureIdentityService
from axis.pharmacology.service import PharmacologyService
from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.computational.service import CampaignService
from axis.learning.service import LearningService
from axis.learning import eligibility
from axis.validation.service import BenchmarkService

def deny(*args, **kwargs):
    raise RuntimeError('Live network is forbidden in brief replay')

socket.socket.connect = deny
P = 'AXIS-DD-ERAP1-CURATED-001'
out = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
    with EvidenceStore(Path(tmp) / 'brief.duckdb') as store:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(P)
        st = StructureIdentityService(store)
        sid = st.import_package(P, protein)
        PharmacologyService(store).import_package(P, protein)
        CellularPharmacologyService(store).import_package(P, protein)
        decision = DecisionService(store)
        decision.import_package(P, protein)
        state = decision.build(P, protein, created_at=datetime(2026, 10, 5, tzinfo=UTC))
        campaign = CampaignService(store)
        cid = campaign.register('erap1')
        campaign.prepare(cid)
        campaign.run(cid)
        learning = LearningService(store)
        ids = learning.build_datasets(P, learning.indexed_records(P))
        elig = [learning.assess_eligibility(i) for i in ids]
        sar = [learning.derive_sar(i) for i in ids]
        data = {'decision': state, 'campaign': campaign.view(cid),
                'learning': learning.learning_state(P), 'eligibility': elig,
                'sar': sar, 'comparability': learning.comparability_matrix(P),
                'structure': st.projection(P, protein, sid),
                'model_policy': eligibility.POLICY,
                'model_policy_fingerprint': eligibility.policy_fingerprint()}
        data['selectivity'] = store.pharmacology.collection(P, protein, 'selectivity', 100, 0)
        data['cellular'] = CellularPharmacologyService(store).chain(P, protein)
        benchmark = BenchmarkService(store)
        data['retrospective'] = {}
        for case in ['erap1-axspa-t2011', 'erap1-axspa-t2014', 'erap1-axspa-t2016']:
            benchmark.snapshot(case)
            benchmark.run(case)
            benchmark.leakage_audit(case)
            benchmark.reveal(case)
            data['retrospective'][case] = benchmark.view(case)['assessment']
        (out / 'state-snapshot.json').write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + '\n')
        print('decision', state['id'], 'campaign', cid, 'datasets', len(ids))
