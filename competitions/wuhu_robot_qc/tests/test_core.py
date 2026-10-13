from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
import pandas as pd

from wuhu_qc.core import analyze_episode, fit_reference, inspect_video, ReferenceProfile, score_findings


def good_df(n=60, fps=30.0):
    t=np.arange(n)/fps
    state=np.stack([np.sin(t),np.cos(t),t,t*0+1],axis=1)
    action=np.stack([np.sin(t+.02),np.cos(t+.02),t+.01,t*0+.5],axis=1)
    return pd.DataFrame({"timestamp":t,"frame_index":np.arange(n),"episode_index":np.zeros(n,dtype=int),"task_index":np.zeros(n,dtype=int),"observation.state":list(state),"action":list(action)})


def write_video(path: Path, frames: list[np.ndarray], fps=30.0):
    h,w=frames[0].shape[:2]
    writer=cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w,h))
    assert writer.isOpened()
    for f in frames: writer.write(f)
    writer.release()


class CoreTests(unittest.TestCase):
    def test_clean_episode_scores_high(self):
        r=analyze_episode(good_df(),0,30,expected_shapes={"observation.state":[4],"action":[4]},numeric_keys=["observation.state","action"])
        self.assertEqual(r.findings,[])
        self.assertEqual(r.quality_score,100)
        self.assertEqual(r.value_score,100)

    def test_frame_gap_and_timestamp_regression(self):
        d=good_df(); d.loc[20:,"frame_index"]+=2; d.loc[35,"timestamp"]=d.loc[34,"timestamp"]-.1
        r=analyze_episode(d,0,30,numeric_keys=[])
        codes={f.code for f in r.findings}
        self.assertIn("FRAME_GAP",codes); self.assertIn("TIMESTAMP_REGRESSION",codes)
        self.assertLess(r.quality_score,100)

    def test_nonfinite_state_is_high_severity(self):
        d=good_df(); x=d.at[10,"observation.state"].copy(); x[1]=np.nan; d.at[10,"observation.state"]=x
        r=analyze_episode(d,0,30,expected_shapes={"observation.state":[4]},numeric_keys=["observation.state"])
        hits=[f for f in r.findings if f.code=="NONFINITE_FEATURE"]
        self.assertEqual(len(hits),1); self.assertEqual(hits[0].severity,"high")

    def test_shape_mismatch_fails_closed(self):
        d=good_df(); d.at[3,"action"]=np.array([1,2])
        r=analyze_episode(d,0,30,expected_shapes={"action":[4]},numeric_keys=["action"])
        codes={f.code for f in r.findings}; self.assertTrue({"INCONSISTENT_VECTOR_SHAPE","NON_NUMERIC_FEATURE"} & codes)

    def test_motion_spike_detected(self):
        d=good_df(); x=d.at[30,"action"].copy(); x[0]=1e6; d.at[30,"action"]=x
        r=analyze_episode(d,0,30,numeric_keys=["action"])
        self.assertIn("MOTION_SPIKE",{f.code for f in r.findings})

    def test_video_black_and_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"cam.mp4"
            frames=[]
            for i in range(20):
                if i<12: frames.append(np.zeros((64,96,3),dtype=np.uint8))
                else:
                    img=np.zeros((64,96,3),dtype=np.uint8); cv2.line(img,(0,i),(95,63-i),(255,255,255),2); frames.append(img)
            write_video(path,frames,30)
            f=inspect_video(path,0,60,30,sample_limit=20)
            codes={x.code for x in f}
            self.assertIn("VIDEO_FRAME_COVERAGE_MISMATCH",codes); self.assertIn("BLACK_FRAME_RATE",codes)

    def test_frozen_video_detected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"frozen.mp4"; img=np.full((64,96,3),120,dtype=np.uint8); cv2.circle(img,(40,30),15,(255,255,255),-1)
            write_video(path,[img.copy() for _ in range(30)],30)
            codes={x.code for x in inspect_video(path,0,30,30,sample_limit=30)}
            self.assertIn("FROZEN_VIDEO_RATE",codes)

    def test_scoring_is_order_invariant(self):
        d=good_df(); d.loc[10:,"frame_index"]+=1
        a=analyze_episode(d,0,30).findings
        x=score_findings(a); y=score_findings(list(reversed(a)))
        self.assertEqual(x,y)

    def test_clean_reference_flags_distribution_shift(self):
        refs=[good_df(80) for _ in range(3)]
        profile=fit_reference(refs,["observation.state","action"])
        shifted=good_df(80); shifted["observation.state"]=[np.asarray(v)+np.array([20.,0,0,0]) for v in shifted["observation.state"]]
        r=analyze_episode(shifted,0,30,numeric_keys=["observation.state","action"],reference=profile)
        self.assertIn("REFERENCE_RANGE_VIOLATION",{f.code for f in r.findings})

    def test_reference_roundtrip_is_deterministic(self):
        profile=fit_reference([good_df(40),good_df(55)],["action"])
        again=ReferenceProfile.from_dict(profile.as_dict())
        self.assertEqual(profile,again)

if __name__=='__main__': unittest.main()
