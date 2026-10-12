"""API integration tests with a fake tutor; real ffmpeg decoding where installed."""
import io
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app as backend
from fastapi.testclient import TestClient
from learning import tutor_prompt


class Tutor:
    def respond(self, question, lang, subject, level, mode):
        return 'Two equal parts make a whole.'

    def run(self, samples, lang, subject, level, mode, with_audio):
        return SimpleNamespace(language=lang or 'yoruba', lid_scores={}, transcript='Explain halves',
                               reply='Two equal parts make a whole.', timings={'total': 0.1}, audio=[])


def wav(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(struct.pack('<h', 1000) * int(16000 * seconds))
    return buf.getvalue()


class ImmediateExecutor:
    def submit(self, fn, *args):
        fn(*args)


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.fake = patch.object(backend, 'pipeline', Tutor())
        self.fake.start()
        self.executor = patch.object(backend, 'executor', ImmediateExecutor())
        self.executor.start()
        self.env = patch.dict('os.environ', {'SAVE_TURNS': '0', 'TUTOR_ENABLED': '1'})
        self.env.start()
        self.client = TestClient(backend.app)

    def tearDown(self):
        self.fake.stop(); self.executor.stop(); self.env.stop(); self.client.close()

    def test_shell_and_manifest(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        manifest = self.client.get('/static/manifest.json').json()
        for icon in manifest['icons']:
            self.assertEqual(self.client.get(icon['src']).status_code, 200)
        self.assertIn('application/javascript', self.client.get('/sw.js').headers['content-type'])

    def test_text_only_does_not_synthesise(self):
        with patch.object(Tutor, 'speak', create=True, side_effect=AssertionError('TTS must not run')):
            r = self.client.post('/learn', data={'question': 'Explain halves', 'lang': 'hausa', 'subject': 'maths'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['language'], 'hausa')
        self.assertNotIn('audio_b64', r.json())

    def test_basic_form_escapes_output(self):
        r = self.client.post('/learn', data={'question': '<script>alert(1)</script>', 'format': 'html'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('&lt;script&gt;', r.text)
        self.assertNotIn('<script>alert', r.text)

    def test_input_validation(self):
        for data in [{'question': ' '}, {'question': 'x'*1001}, {'question': 'hi', 'lang': 'invalid'},
                     {'question': 'hi', 'subject': 'invalid'}, {'question': 'hi', 'mode': 'invalid'}]:
            self.assertEqual(self.client.post('/learn', data=data).status_code, 400)
        self.assertEqual(self.client.post('/talk', files={'audio': ('x.wav', b'x'*(backend.MAX_UPLOAD+1))}).status_code, 413)

    def test_busy_and_model_failure(self):
        backend.inference_lock.acquire()
        try:
            self.assertEqual(self.client.post('/learn', data={'question': 'Hi'}).status_code, 503)
        finally:
            backend.inference_lock.release()
        with patch.object(Tutor, 'respond', side_effect=RuntimeError('private error')):
            r = self.client.post('/learn', data={'question': 'Hi'})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('private error', r.text)
        self.assertFalse(backend.inference_lock.locked())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_voice_wav_and_browser_webm(self):
        for raw in [wav(), self.webm()]:
            r = self.client.post('/talk', files={'audio': ('recording', raw)}, data={'with_audio': 'false'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['language'], 'yoruba')
        self.assertEqual(self.client.post('/talk', files={'audio': ('bad', b'bad')}).status_code, 400)
        self.assertEqual(self.client.post('/talk', files={'audio': ('short.wav', wav(.1))}).status_code, 400)
        self.assertEqual(self.client.post('/talk', files={'audio': ('long.wav', wav(61))}).status_code, 400)

    def webm(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'input.wav'; target = Path(d)/'output.webm'
            source.write_bytes(wav())
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-c:a', 'libopus', str(target)], check=True)
            return target.read_bytes()

    def test_lessons_and_feedback_without_inference(self):
        with patch.object(backend, 'get_pipeline', side_effect=AssertionError('Lessons do not need GPU')):
            self.assertEqual(self.client.get('/lessons').status_code, 200)
            self.assertEqual(self.client.get('/lessons/fractions').status_code, 200)
            correct = self.client.post('/lessons/fractions/check', data={'choice': 2})
            wrong = self.client.post('/lessons/fractions/check', data={'choice': 1})
            self.assertIn('That is correct!', correct.text)
            self.assertIn('Have another look', wrong.text)
            self.assertEqual(self.client.post('/lessons/fractions/check', data={'choice': 9}).status_code, 400)
            self.assertEqual(self.client.get('/lessons/missing').status_code, 404)

    def test_async_basic_browser_job(self):
        r = self.client.post('/learn', data={'question': 'Explain halves', 'format': 'html'}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        result = self.client.get(r.headers['location'])
        self.assertEqual(result.status_code, 200)
        self.assertIn('Two equal parts', result.text)
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/jobs/missing').status_code, 404)
        with patch.object(backend.executor, 'submit'):
            pending = self.client.post('/learn', data={'question': 'Explain halves', 'format': 'html'}, follow_redirects=False)
        try:
            page = self.client.get(pending.headers['location'])
            self.assertIn('http-equiv="refresh"', page.text)
            self.assertIn('Check again', page.text)
        finally:
            backend.job_slots.release()
            backend.jobs.pop(pending.headers['location'].split('/')[-1])

    def test_tutor_disabled_keeps_lessons_available(self):
        with patch.dict('os.environ', {'TUTOR_ENABLED': '0'}), patch.object(backend, 'get_pipeline', side_effect=AssertionError('Disabled tutor must not load')):
            response = self.client.post('/learn', data={'question': 'Explain halves'})
            self.assertEqual(response.status_code, 503)
            self.assertIn('not enabled', response.json()['detail'])
            self.assertEqual(self.client.get('/lessons').status_code, 200)

    def test_learning_prompt(self):
        prompt = tutor_prompt('Igbo', 'maths', 'junior', 'practice')
        self.assertIn('Reply only in Igbo', prompt)
        self.assertIn('Mathematics', prompt)
        self.assertIn('without revealing', prompt)


if __name__ == '__main__':
    unittest.main()
