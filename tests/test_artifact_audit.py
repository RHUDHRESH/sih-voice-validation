"""Tamper checks for the independent serialized-result auditor."""
import csv
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from verify_artifacts import verify


def write_json(path, obj):
    path.write_text(json.dumps(obj))


def build_minimal(root):
    source = struct.pack('<hhhh', 7, 8, 9, 10)
    digest = lambda b: hashlib.sha256(b).hexdigest()
    (root/'fixture.pcm').write_bytes(source)
    write_json(root/'fixture_manifest.json', [{'scenario_id':'tiny','path':'fixture.pcm','samples':4,'sha256':digest(source)}])
    write_json(root/'config_used.json', {'scenarios':[{'scenario_id':'tiny','utterances':[{'utterance_id':'u','command_start':1,'command_end':4}]}]})
    runs=[]
    for policy in ('naive','buffered'):
        directory=root/'runs'/f'tiny__{policy}'
        directory.mkdir(parents=True)
        sid=f'tiny:{policy}:1'
        command={'utterance_id':'u','selected_session_id':sid,'ground_truth_start':1,'ground_truth_end':4,
                 'command_samples':3,'command_samples_received':3,'command_samples_missing':0,
                 'onset_lost_samples':0,'command_integrity_status':'pass'}
        run={'scenario_id':'tiny','policy':policy,'input_sha256':digest(source),
             'command_integrity_status':'pass','commands':[command],
             'sessions':[{'session_id':sid,'utterance_id':'u','accepted_at':3,'state':'COMPLETE','capture_end':4}]}
        runs.append(run)
        write_json(directory/'result.json', run)
        (directory/'events.csv').write_text('at_sample,event,session_id\n3,SEND,'+sid+'\n')
        (directory/'packets.csv').write_text('at_sample,session_id,seq,first_sample_index,sample_count,sha256,disposition\n4,'+sid+',0,1,3,'+digest(source[2:])+',ACCEPTED\n')
        (directory/'receiver_session_1.pcm').write_bytes(source[2:])
        write_json(directory/'receiver_session_1.json', {'session_id':sid,'declared_start':1,'received_end':4,
                   'completed_end':4,'state':'COMPLETE','sample_count':3,'pcm_sha256':digest(source[2:])})
    write_json(root/'summary.json', {'runs':runs})


class ArtifactAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='voice-audit-')
        self.root=Path(self.directory.name)
        build_minimal(self.root)
    def tearDown(self):
        self.directory.cleanup()
    def test_independent_golden_audit(self):
        self.assertEqual(verify(self.root)['replays_audited'],2)
    def test_summary_cannot_redefine_ground_truth(self):
        summary=json.loads((self.root/'summary.json').read_text())
        row=summary['runs'][0]
        row['commands'][0].update(ground_truth_start=2,command_samples=2,command_samples_received=2)
        write_json(self.root/'summary.json',summary)
        write_json(self.root/'runs/tiny__naive/result.json',row)
        with self.assertRaises(AssertionError):
            verify(self.root)
    def test_per_run_result_must_match_summary(self):
        path=self.root/'runs/tiny__naive/result.json'
        row=json.loads(path.read_text());row['command_integrity_status']='fail';write_json(path,row)
        with self.assertRaises(AssertionError):
            verify(self.root)
    def test_duplicate_scenario_policy_key_rejected(self):
        path=self.root/'summary.json';summary=json.loads(path.read_text());summary['runs'].append(summary['runs'][0]);write_json(path,summary)
        with self.assertRaises(AssertionError):
            verify(self.root)
    def test_corrupt_serialized_pcm_rejected(self):
        (self.root/'runs/tiny__naive/receiver_session_1.pcm').write_bytes(b'\0'*6)
        with self.assertRaises(AssertionError):
            verify(self.root)
