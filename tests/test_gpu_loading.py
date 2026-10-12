"""Check actual Pipeline loading methods with fake models; no CUDA/weights needed."""
import ast
from contextlib import nullcontext
import gc
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np


class Model:
    def __init__(self):
        self.device = None
    def to(self, device, *args):
        self.device = device
        return self
    def eval(self):
        return self


def pipeline_class(vram=16):
    source = ast.parse((Path(__file__).resolve().parents[1] / 'server/pipeline.py').read_text())
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'Pipeline')
    cuda = SimpleNamespace(is_available=lambda: True, get_device_properties=lambda device: SimpleNamespace(total_memory=vram*1e9),
                           device=lambda device: nullcontext(), empty_cache=Mock())
    torch = SimpleNamespace(cuda=cuda, device=lambda device: device, inference_mode=lambda: lambda fn: fn)
    proc_loader = SimpleNamespace(from_pretrained=Mock(side_effect=lambda name: object()))
    model_loader = SimpleNamespace(from_pretrained=Mock(side_effect=lambda *args, **kwargs: Model()))
    ns = {'torch': torch, 'os': os, 'gc': gc, 'time': __import__('time'), 'np': np, 'Result': object,
          'DEVICE': 'cuda:0', 'ASR_DEVICE': 'cuda:1', 'TTS_DEVICE': 'cuda:1', 'DTYPE': 'float16',
          'LANGS': ['english', 'yoruba', 'hausa', 'igbo'], 'ASR_MODELS': {x:x for x in ['english','yoruba','hausa','igbo']},
          'WhisperProcessor': proc_loader, 'WhisperForConditionalGeneration': model_loader,
          'TTS_MODEL': 'tts', 'WAVTOKENIZER_CKPT': 'checkpoint', 'WAVTOKENIZER_CONFIG': 'config',
          'AutoModelForCausalLM': model_loader,
          'AudioTokenizerV2': lambda *args: SimpleNamespace(device='cuda:0', wavtokenizer=Model())}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'pipeline-loading', 'exec'), ns)
    return ns['Pipeline'], ns


class GPULoadingTests(unittest.TestCase):
    def make(self, vram):
        cls, ns = pipeline_class(vram)
        with patch.dict(os.environ, {'LOW_VRAM':'auto'}), patch.object(cls, '_load_llm'), patch.object(cls, '_load_tts'), patch.object(cls, '_load_lid') as lid:
            p = cls()
        return p, ns, lid

    def test_free_gpu_uses_lazy_single_recogniser_cache(self):
        p, ns, lid = self.make(16)
        self.assertTrue(p.low_vram)
        self.assertEqual(p.asr, {})
        lid.assert_not_called()
        first = p._get_asr('english')
        self.assertEqual(first[1].device, 'cuda:1')
        self.assertIs(p._get_asr('english'), first)
        p._get_asr('hausa')
        self.assertEqual(list(p.asr), ['hausa'])
        self.assertEqual(ns['WhisperProcessor'].from_pretrained.call_count, 2)
        ns['torch'].cuda.empty_cache.assert_called_once()

    def test_larger_gpu_keeps_existing_four_language_loading(self):
        p, ns, lid = self.make(24)
        self.assertFalse(p.low_vram)
        self.assertEqual(len(p.asr), 4)
        lid.assert_called_once()

    def test_t4_synthesis_uses_fp16_on_speech_gpu(self):
        cls, ns = pipeline_class()
        p = cls.__new__(cls)
        p._load_tts()
        ns['AutoModelForCausalLM'].from_pretrained.assert_called_once_with('tts', torch_dtype='float16')
        self.assertEqual(p.tts.device, 'cuda:1')
        self.assertEqual(p.tts_tok.device, 'cuda:1')
        self.assertEqual(p.tts_tok.wavtokenizer.device, 'cuda:1')

    def test_cpu_runtime_fails_with_clear_error(self):
        cls, ns = pipeline_class()
        ns['torch'].cuda.is_available = lambda: False
        with self.assertRaisesRegex(RuntimeError, 'CUDA GPU'):
            cls()


if __name__ == '__main__':
    unittest.main()
