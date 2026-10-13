from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from revenue.procurement_qa_answer_delta.compiler import compile_delta, verify
from revenue.procurement_qa_answer_delta.schema import BOUNDARY, Error, canon, digest, load
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'synthetic_pack.json'

def false_authority():
    return {'proposal_authorized': False, 'submission_authorized': False, 'buyer_contact_authorized': False, 'prime_contact_authorized': False, 'portal_action_authorized': False, 'signature_authorized': False, 'certification_authorized': False, 'price_commitment_authorized': False, 'payment_authorized': False, 'award_or_revenue_recognized': False}

def active_set():
    return {'schema': 'procurement-solicitation-ingest/active-set/v1', 'truth_boundary': BOUNDARY, 'pack_id': 'rfp-demo-17', 'evaluated_at': '2026-09-16T20:00:00-04:00', 'current_source': {'source_id': 'amend-02', 'identity': 'buyer://demo/amendment-2', 'ref': 'https://buyer.example/amendment-2.pdf', 'sha256': '2' * 64, 'captured_at': '2026-09-16T19:00:00-04:00', 'sequence': 2}, 'deadline': {'value': '2026-09-30T16:00:00-04:00', 'utc': '2026-09-30T20:00:00Z', 'source_id': 'amend-02', 'identity': 'buyer://demo/amendment-2', 'ref': 'https://buyer.example/amendment-2.pdf', 'sha256': '2' * 64}, 'requirements': [{'lineage_id': 'req-security', 'section_id': 'sec-3.2', 'kind': 'MANDATORY', 'family': 'security', 'tags': ['soc2', 'encryption'], 'text': 'Provide current security control evidence.', 'source_id': 'amend-02', 'source_identity': 'buyer://demo/amendment-2', 'source_ref': 'https://buyer.example/amendment-2.pdf', 'source_sha256': '2' * 64, 'source_captured_at': '2026-09-16T19:00:00-04:00', 'sequence': 2}, {'lineage_id': 'req-hosting', 'section_id': 'sec-4.1', 'kind': 'SCORED', 'family': 'technical', 'tags': ['hosting'], 'text': 'Describe hosting architecture and recovery controls.', 'source_id': 'amend-02', 'source_identity': 'buyer://demo/amendment-2', 'source_ref': 'https://buyer.example/amendment-2.pdf', 'source_sha256': '2' * 64, 'source_captured_at': '2026-09-16T19:00:00-04:00', 'sequence': 2}], 'attachments': [], 'killed_sources': ['solicitation-01'], 'authority': false_authority()}

def gaps_obj():
    return {'schema': 'procurement-solicitation-ingest/gaps/v1', 'truth_boundary': BOUNDARY, 'pack_id': 'rfp-demo-17', 'status': 'OWNER_REVIEW_READY', 'hold_reasons': [], 'gaps': [{'gap_id': 'human-evidence:req-security', 'severity': 'HOLD', 'blocking': True, 'reason': 'BLOCKING_REQUIREMENT_NEEDS_OWNER_EVIDENCE', 'detail': 'Provide current security control evidence.', 'source_id': 'amend-02', 'source_ref': 'https://buyer.example/amendment-2.pdf', 'source_sha256': '2' * 64, 'lineage_id': 'req-security', 'kind': 'MANDATORY', 'family': 'security', 'section_id': 'sec-3.2'}, {'gap_id': 'human-evidence:req-hosting', 'severity': 'SCORED', 'blocking': True, 'reason': 'BLOCKING_REQUIREMENT_NEEDS_OWNER_EVIDENCE', 'detail': 'Describe hosting architecture and recovery controls.', 'source_id': 'amend-02', 'source_ref': 'https://buyer.example/amendment-2.pdf', 'source_sha256': '2' * 64, 'lineage_id': 'req-hosting', 'kind': 'SCORED', 'family': 'technical', 'section_id': 'sec-4.1'}], 'authority': false_authority()}

def receipt_obj(active, gaps):
    return {'schema': 'procurement-solicitation-ingest/receipt/v1', 'truth_boundary': BOUNDARY, 'status': 'OWNER_REVIEW_READY', 'pack_id': 'rfp-demo-17', 'pack_sha256': '3' * 64, 'selector_sha256': '4' * 64, 'active_set_sha256': digest(canon(active)), 'gaps_sha256': digest(canon(gaps)), 'markdown_sha256': '5' * 64, 'readiness_sha256': '6' * 64, 'authority': false_authority()}

def question(qid='q-security', *, lineage='req-security', gap='human-evidence:req-security', section='sec-3.2', qclass='MANDATORY_AMBIGUITY', modules=None):
    return {'question_id': qid, 'intent_id': 'intent-' + qid, 'question_class': qclass, 'gap_id': gap, 'lineage_id': lineage, 'section_id': section, 'source_id': 'amend-02', 'source_sha256': '2' * 64, 'affected_module_ids': modules or ['module-security']}

def answer(aid='a-security-1', *, qid='q-security', lineage='req-security', effect='CLOSE_GAP', supersedes=None, section='qa-7', req_after=None, deadline_after=None, modules=None, text='Buyer confirms the existing evidence package satisfies this item.'):
    return {'answer_id': aid, 'supersedes_answer_id': supersedes, 'question_id': qid, 'lineage_id': lineage, 'section_id': section, 'effect': effect, 'answer_text': text, 'requirement_after': req_after, 'deadline_after': deadline_after, 'affected_module_ids': modules or []}

def source(sid='qa-01', *, seq=10, captured='2026-09-16T19:30:00-04:00', source_class='BUYER_OFFICIAL', answers=None):
    return {'source_id': sid, 'identity': f'buyer://demo/{sid}', 'ref': f'https://buyer.example/{sid}.pdf', 'sha256': hashlib.sha256(sid.encode()).hexdigest(), 'captured_at': captured, 'sequence': seq, 'source_class': source_class, 'answers': answers or [answer()]}

def document():
    active = active_set()
    gaps = gaps_obj()
    rec = receipt_obj(active, gaps)
    return {'schema': 'procurement-qa-answer-delta/input/v1', 'truth_boundary': BOUNDARY, 'packet_id': 'qa-delta-demo-17', 'evaluated_at': '2026-09-16T20:00:00-04:00', 'source_max_age_seconds': 86400, 'upstream': {'active_set': active, 'active_set_sha256': digest(canon(active)), 'gaps': gaps, 'gaps_sha256': digest(canon(gaps)), 'receipt': rec, 'receipt_sha256': digest(canon(rec))}, 'questions': [question(), question('q-hosting', lineage='req-hosting', gap='human-evidence:req-hosting', section='sec-4.1', qclass='SCORED_AMBIGUITY', modules=['module-hosting']), question('q-deadline', lineage=None, gap=None, section='sec-admin', qclass='COMMERCIAL_ASSUMPTION', modules=['module-schedule'])], 'qa_sources': [source()]}

def compile_obj(doc):
    out = compile_delta(canon(doc))
    return (out, load(out.delta, 'delta'))
