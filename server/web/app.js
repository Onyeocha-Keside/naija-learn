/* The text form remains usable when these browser APIs are absent. */
(function () {
  'use strict';
  var form = document.getElementById('learn-form');
  var status = document.getElementById('status');
  var recorder = null, stream = null, timer = null, pollTimer = null, busy = false, recording = false;
  var canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  function el(id) { return document.getElementById(id); }
  function connection() { el('connection').hidden = navigator.onLine !== false; }
  connection(); window.addEventListener('online', connection); window.addEventListener('offline', connection);
  if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(function () {}); }
  if (!window.FormData || !window.XMLHttpRequest) { return; }
  el('voice-tools').hidden = false; el('audio-option').hidden = false;
  function lock(value) {
    busy = value;
    el('submit').disabled = value; el('record').disabled = value || !canRecord; el('send-file').disabled = value;
    var controls = form.querySelectorAll('select, textarea, input');
    for (var i = 0; i < controls.length; i++) { controls[i].disabled = value; }
  }
  function data() {
    var d = new FormData();
    ['lang', 'subject', 'level', 'mode'].forEach(function (key) { d.append(key, el(key).value); });
    d.append('queued', 'true');
    d.append('with_audio', el('spoken').checked ? 'true' : 'false');
    return d;
  }
  function showAnswer(r) {
    lock(false);
    el('transcript').textContent = 'Your question: ' + r.transcript;
    el('reply').textContent = r.reply;
    if (r.audio_b64) { el('playback').src = 'data:audio/wav;base64,' + r.audio_b64; el('playback').hidden = false; }
    el('answer').hidden = false;
    status.textContent = r.audio_b64 ? 'Your answer is ready. Press Play below to hear it.' : 'Your text answer is ready.';
    el('answer').focus();
  }
  function unreadable(xhr) {
    lock(false);
    status.textContent = 'The connection returned a webpage instead of an answer (HTTP ' + xhr.status + '). The tunnel may have timed out or your login expired. Refresh this page and check the Kaggle server log.';
  }
  function poll(id, started) {
    if (Date.now() - started > 900000) { lock(false); status.textContent = 'The tutor is taking too long. Check the Kaggle server log before trying again.'; return; }
    var xhr = new XMLHttpRequest(); xhr.open('GET', '/jobs/' + encodeURIComponent(id) + '?format=json', true); xhr.timeout = 30000;
    xhr.onload = function () {
      var r;
      try { r = JSON.parse(xhr.responseText); } catch (e) { unreadable(xhr); return; }
      if (xhr.status !== 200 || r.state === 'failed') { lock(false); status.textContent = typeof r.detail === 'string' ? r.detail : 'Could not retrieve this answer. Check the server log.'; return; }
      if (r.state === 'done') { showAnswer(r.result); return; }
      if (r.state !== 'pending') { unreadable(xhr); return; }
      status.textContent = 'Your question is queued or processing. The first voice request may download its speech model. Please wait; you do not need to record again.';
      pollTimer = setTimeout(function () { poll(id, started); }, 4000);
    };
    xhr.onerror = xhr.ontimeout = function () {
      status.textContent = 'Connection interrupted. Checking your existing question again…';
      pollTimer = setTimeout(function () { poll(id, started); }, 4000);
    };
    xhr.send();
  }
  function send(url, d) {
    if (busy) { return; }
    if (navigator.onLine === false) { status.textContent = 'Connect to the internet to ask the tutor. Your question is still here.'; return; }
    lock(true); status.textContent = 'Sending your question…';
    el('answer').hidden = true; el('playback').pause(); el('playback').removeAttribute('src'); el('playback').hidden = true;
    var xhr = new XMLHttpRequest(); xhr.open('POST', url, true); xhr.timeout = 300000;
    xhr.onload = function () {
      var r;
      try { r = JSON.parse(xhr.responseText); } catch (e) { unreadable(xhr); return; }
      if (xhr.status === 202 && r.id) { poll(r.id, Date.now()); return; }
      if (xhr.status !== 200) { lock(false); status.textContent = typeof r.detail === 'string' ? r.detail : 'Could not send this question. Please check your input and try again.'; return; }
      showAnswer(r);
    };
    xhr.onerror = xhr.ontimeout = function () { lock(false); status.textContent = 'The connection failed or took too long. Your question is still here; please try again.'; };
    xhr.send(d);
  }
  form.addEventListener('submit', function (event) {
    event.preventDefault(); if (busy || recording) { return; }
    var question = el('question').value.replace(/^\s+|\s+$/g, '');
    if (!question) { status.textContent = 'Type a question first.'; return; }
    var d = data(); d.append('question', question); send('/learn', d);
  });
  function sendAudio(blob, name) {
    if (!blob || !blob.size || blob.size > 4194304) { status.textContent = 'Choose a recording under 4 MB.'; return; }
    var d = data(); d.append('audio', blob, name || 'recording.webm'); send('/talk', d);
  }
  el('send-file').addEventListener('click', function () {
    if (recording) { return; }
    var files = el('audio-file').files; if (!files || !files.length) { status.textContent = 'Choose a recording first.'; return; }
    sendAudio(files[0], files[0].name);
  });
  function cleanup() {
    clearTimeout(timer); if (stream) { stream.getTracks().forEach(function (track) { track.stop(); }); stream = null; }
    recording = false; el('record').textContent = 'Record a question'; el('submit').disabled = false; el('send-file').disabled = false;
  }
  if (!canRecord) {
    el('record').disabled = true;
    el('voice-help').textContent = 'This browser cannot record here. Upload a recording or type your question. Microphone access needs HTTPS or localhost.';
  } else {
    el('record').addEventListener('click', function () {
      if (busy) { return; }
      if (recording) { if (recorder && recorder.state === 'recording') { recorder.stop(); } return; }
      el('record').disabled = true; status.textContent = 'Allow microphone access to record.';
      navigator.mediaDevices.getUserMedia({audio: true}).then(function (s) {
        stream = s;
        try { recorder = new MediaRecorder(s, {audioBitsPerSecond: 16000}); } catch (e) { cleanup(); el('record').disabled = false; status.textContent = 'Recording is unavailable. Upload audio or type instead.'; return; }
        var chunks = [], size = 0, tooLarge = false;
        recorder.ondataavailable = function (event) {
          if (event.data.size) { chunks.push(event.data); size += event.data.size; }
          if (size > 4194304 && recorder.state === 'recording') { tooLarge = true; recorder.stop(); }
        };
        recorder.onerror = function () { tooLarge = true; cleanup(); status.textContent = 'Recording failed. Please try again or type.'; };
        recorder.onstop = function () {
          var type = recorder.mimeType; cleanup();
          if (tooLarge) { status.textContent = 'Recording could not be sent. Try a shorter recording or type.'; return; }
          sendAudio(new Blob(chunks, {type: type}));
        };
        try { recorder.start(1000); } catch (e) { cleanup(); el('record').disabled = false; status.textContent = 'Could not start recording. Please type or upload audio.'; return; }
        recording = true; el('record').disabled = false; el('record').textContent = 'Stop and send question';
        el('submit').disabled = true; el('send-file').disabled = true; status.textContent = 'Listening… press Stop when you finish.';
        timer = setTimeout(function () { if (recorder.state === 'recording') { recorder.stop(); } }, 59000);
      }).catch(function () { el('record').disabled = false; status.textContent = 'Microphone access was unavailable. You can upload audio or type your question.'; });
    });
  }
  window.addEventListener('pagehide', function () { clearTimeout(pollTimer); if (recorder && recorder.state === 'recording') { recorder.onstop = null; recorder.stop(); } cleanup(); });
}());
