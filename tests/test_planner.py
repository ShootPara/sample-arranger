"""No network/credentials: model/broker outputs are deliberately untrusted fixtures."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from planner import propose_sections


class PlannerBoundaryTests(unittest.TestCase):
    def test_valid_compact_response_and_utf8_reserve(self):
        calls=[]
        def send(prompt,context,output):
            calls.append(prompt)
            self.assertLessEqual(len(prompt.encode("utf-8"))+256+12+output,context)
            return {"structured":[{"sample":"safe.wav","seconds":8}]}
        self.assertEqual(propose_sections("8 seconds upbeat",["safe.wav"],send)[0]["seconds"],8)
        with self.assertRaisesRegex(ValueError,"UTF-8 budget"):
            propose_sections("🎵"*1000,["safe.wav"],send)
        self.assertEqual(len(calls),1,"oversized requests must never reach transport")

    def test_failed_poll_truncation_injection_and_invalid_music(self):
        cases=[None,{"state":"failed","structured":[{"sample":"safe.wav","seconds":4}]},
               {"limited":True,"structured":[{"sample":"safe.wav","seconds":4}]},
               {"structured":[{"sample":"../../escape.wav","seconds":4}]},
               {"structured":[{"sample":"safe.wav","seconds":True}]},
               {"structured":[{"sample":"safe.wav","seconds":float("nan")}]},
               {"structured":[{"sample":"safe.wav","seconds":200}]*2},
               {"structured":[{"sample":"safe.wav","seconds":4,"shell":"run me"}]}]
        for response in cases:
            with self.subTest(response=response),self.assertRaises(ValueError):
                propose_sections("music",["safe.wav"],lambda *args:response)
        for error in (TimeoutError("deadline"),ConnectionError("503 unavailable"),ConnectionError("429 full")):
            calls=[]
            def failing(*args):calls.append(1);raise error
            with self.assertRaises(type(error)):
                propose_sections("music",["safe.wav"],failing)
            self.assertEqual(len(calls),1,"no retry or raw/cloud fallback")
