/* Behaviour checks for progressive text submission without browser dependencies. */
var assert = require('node:assert/strict');
var vm = require('node:vm');
var fs = require('node:fs');
function setup(enhanced, microphone) {
  var elements = {}, requests = [];
  ['learn-form','status','connection','voice-tools','audio-option','submit','record','send-file','lang','subject','level','mode','question','spoken','answer','playback','transcript','reply','audio-file','voice-help'].forEach(function (id) {
    elements[id] = {hidden:true, disabled:false, value:'', textContent:'', checked:true, handlers:{},
      addEventListener:function (key, fn) { this.handlers[key]=fn; }, querySelectorAll:function () { return []; },
      pause:function () {}, removeAttribute:function () {}, focus:function () {this.focused=true;}};
  });
  elements.lang.value='hausa'; elements.subject.value='maths'; elements.level.value='primary'; elements.mode.value='explain';
  function Data() { this.values={}; } Data.prototype.append=function (k,v) {this.values[k]=v;};
  function XHR() { requests.push(this); }
  XHR.prototype.open=function (method,url) {this.url=url;}; XHR.prototype.send=function (d) {this.data=d;};
  var window={addEventListener:function(){}};
  if(enhanced) {window.FormData=Data; window.XMLHttpRequest=XHR;}
  var navigator={onLine:true};
  if (microphone) {
    navigator.mediaDevices={getUserMedia:function(){return Promise.resolve({getTracks:function(){return [{stop:function(){}}];}});}};
    function Recorder() {this.mimeType='audio/webm'; this.state='inactive';}
    Recorder.prototype.start=function(){this.state='recording';};
    Recorder.prototype.stop=function(){this.state='inactive'; this.ondataavailable({data:new Blob(['audio'])}); if(this.onstop){this.onstop();}};
    window.MediaRecorder=Recorder;
  }
  vm.runInNewContext(fs.readFileSync('server/web/app.js','utf8'), {document:{getElementById:function(id){return elements[id];}},window:window,navigator:navigator,FormData:Data,XMLHttpRequest:XHR,MediaRecorder:window.MediaRecorder,Blob:Blob,setTimeout:setTimeout,clearTimeout:clearTimeout});
  return {e:elements, requests:requests, navigator:navigator};
}
var basic=setup(false);
assert.equal(basic.e['learn-form'].handlers.submit, undefined, 'basic form keeps native submission');
var app=setup(true), e=app.e;
assert.equal(e.record.disabled,true,'unsupported recorder disabled');
e.question.value='Explain halves';
e['learn-form'].handlers.submit({preventDefault:function(){}});
assert.equal(app.requests[0].url,'/learn');
assert.equal(app.requests[0].data.values.lang,'hausa');
assert.equal(e.submit.disabled,true);
app.requests[0].status=200; app.requests[0].responseText=JSON.stringify({transcript:'Explain halves',reply:'A half is one of two equal parts.'}); app.requests[0].onload();
assert.equal(e.reply.textContent,'A half is one of two equal parts.');
assert.equal(e.answer.hidden,false); assert.equal(e.record.disabled,true,'text reply must not enable unsupported recording');
assert.equal(e.playback.hidden,true);
e['learn-form'].handlers.submit({preventDefault:function(){}}); app.requests[1].onerror();
assert.equal(e.question.value,'Explain halves'); assert.equal(e.submit.disabled,false);
app.navigator.onLine=false;
e['learn-form'].handlers.submit({preventDefault:function(){}});
assert.equal(app.requests.length,2,'offline questions are not sent');
console.log('Web behaviour checks passed: basic form, text request, rendering, recorder fallback, retry and offline handling.');

(async function () {
  var voice = setup(true, true);
  voice.e.record.handlers.click();
  await Promise.resolve(); await Promise.resolve();
  assert.equal(voice.e.record.textContent, 'Stop and send question');
  assert.equal(voice.e.submit.disabled, true);
  voice.e.record.handlers.click();
  assert.equal(voice.requests[0].url, '/talk');
  assert.equal(voice.requests[0].data.values.audio.size, 5);
  voice.requests[0].status = 200;
  voice.requests[0].responseText = JSON.stringify({transcript:'Voice question', reply:'Answer', audio_b64:'AA=='});
  voice.requests[0].onload();
  assert.equal(voice.e.playback.hidden, false);
  assert.equal(voice.e.record.disabled, false);
  console.log('Recording behaviour checks passed: start, stop, upload and spoken reply.');
}()).catch(function (error) { console.error(error); process.exitCode = 1; });
