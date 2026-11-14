const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
  checked=false;disabled=false;value='';textContent='';listeners={};
  classList={toggle(name,on){this[name]=on}};
  replaceChildren(...children){this.options=children}
  addEventListener(type,callback){this.listeners[type]=callback}
}
const elements={};const $=id=>elements[id]??=new Element();
const calls=[],messages=[];
const context={$,
  selectedAdapterId:'no-oled',
  statusData:{capabilities:{touch_mouse:true,ds4_gyro:true},output_mode:1,multi_controller:false,
    touch_mouse:{enabled:true,active:true,available:true},ds4_aim:{enabled:0,sensitivity:100,activation:1,flags:0,pause_button:10}},
  Option:class{constructor(label,value){this.label=label;this.value=value}},
  guardAdapterAction:f=>f,setTimeout:()=>{},refresh:()=>{},toast:(...x)=>messages.push(x),
  post:async(path,payload)=>{calls.push({path,payload});return {mouse:{restart_required:true}}}
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../assets/companion_remote.sh'),'utf8').split('// BLUEBRIDGE_TOUCH_MOUSE')[1].split('</script>')[0],context);
const run=s=>vm.runInContext(s,context);
(async()=>{
  run('renderTouchMouse()');assert(!$('ds4GyroEnabled').checked);assert.equal($('ds4GyroSensitivity').value,'100');
  assert(!$('ds4GyroPanel').disabled&&!$('touchMouseSave').disabled);
  $('ds4GyroEnabled').checked=true;$('ds4GyroSensitivity').value='150';$('ds4GyroInvertX').checked=true;
  $('ds4GyroPanel').listeners.change();run('renderTouchMouse()');assert($('ds4GyroEnabled').checked);assert.equal($('ds4GyroSensitivity').value,'150');
  await run('saveTouchMouse()');assert.equal(calls.length,1);assert.equal(calls[0].payload.ds4_aim.sensitivity,150);
  assert.equal(calls[0].payload.ds4_aim.flags,1);assert.equal(context.statusData.ds4_aim.enabled,true);
  $('ds4GyroSensitivity').value='201';run('touchMouseDirty=true');await run('saveTouchMouse()');assert.equal(calls.length,1);assert(messages.some(x=>/1 to 200/.test(x[0])));
  context.selectedAdapterId='oled';context.statusData.ds4_aim={enabled:0,sensitivity:100,activation:1,flags:0,pause_button:10};
  run('renderTouchMouse()');assert(!$('ds4GyroEnabled').checked);assert.equal($('ds4GyroSensitivity').value,'100');
  context.statusData.capabilities.ds4_gyro=false;run('renderTouchMouse()');assert($('ds4GyroPanel').classList.hidden);
  const data=run('pointerPayload()');assert(!data.ds4_aim,'older firmware gets mouse-only payload');
  context.statusData.capabilities.ds4_gyro=true;delete context.statusData.ds4_aim;run('renderTouchMouse()');assert($('touchMouseSave').disabled);
  console.log('companion UI: DS4 defaults, dirty edits during refresh, save/validation, adapter switch and firmware fallback passed');
})().catch(e=>{console.error(e);process.exitCode=1});
