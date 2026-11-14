const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
class Element {
  checked=false;disabled=false;value='';textContent='';
  classList={toggle(name,on){this[name]=on},add(name){this[name]=true}};
}
const elements={};const $=id=>elements[id]??=new Element();
let controller={index:0,id:123,kind:4,name:'DualShock 4',connected:true,slot:0};
let data={theme:2,players:[[64,0,0],[0,64,0],[11,22,33],[44,55,66]],controllers:[{index:0,id:123,player:0,custom_enabled:false,rgb:[64,0,0]}]};
const calls=[],messages=[];
const context={$,
  selectedAdapterId:'no-oled',selectedController:()=>controller,
  statusData:{capabilities:{ds4_lightbar:true},lightbar:structuredClone(data)},
  guardAdapterAction:f=>f,toast:(...m)=>messages.push(m),
  post:async(url,payload)=>{calls.push({url,payload});if(url.endsWith('/palette')){data={...data,...payload};}else{data.controllers=[{...data.controllers[0],...payload}];}return {lightbar:structuredClone(data)}}
};
vm.createContext(context);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'../assets/companion_remote.sh'),'utf8').split('// BLUEBRIDGE_DS4_LIGHTBAR')[1].split('</script>')[0],context);
const run=s=>vm.runInContext(s,context);
(async()=>{
  run('renderLightbar()');assert.equal($('lightbarTheme').value,'2');assert.equal($('lightbarP1').value,'#400000');
  assert.equal($('lightbarP2').value,'#004000');assert(!$('lightbarController').disabled);
  $('lightbarTheme').value='1';run('lightbarThemeChanged();renderLightbar()');
  assert.equal($('lightbarP1').value,'#000040');assert.equal($('lightbarP2').value,'#402000');
  assert.equal($('lightbarP3').value,'#0b1621');assert.equal($('lightbarP4').value,'#2c3742');
  await run('saveLightbarPalette()');assert.equal(calls[0].payload.theme,1);assert.equal(context.statusData.lightbar.theme,1);
  $('lightbarP3').value='#010203';run('lightbarColourChanged(2);renderLightbar()');assert.equal($('lightbarTheme').value,'1');
  $('lightbarP1').value='#aabbcc';run('lightbarColourChanged(0);renderLightbar()');assert.equal($('lightbarTheme').value,'0');assert.equal($('lightbarP1').value,'#aabbcc');
  $('lightbarCustom').checked=true;$('lightbarCustomColour').value='#090807';run('lightbarControllerDirty=true;renderLightbar()');
  assert($('lightbarPlayer').disabled);assert(!$('lightbarCustomColour').disabled);
  await run('saveLightbarController()');assert.equal(calls[1].payload.id,123);assert.deepEqual(Array.from(calls[1].payload.rgb),[9,8,7]);
  context.selectedAdapterId='oled';context.statusData.lightbar=structuredClone(data);run('renderLightbar()');
  assert.equal($('lightbarP1').value,'#000040','switching adapters discards unsaved palette edits');
  controller={...controller,kind:2};run('renderLightbar()');assert($('lightbarController').classList.hidden);
  context.statusData.capabilities={};run('renderLightbar()');assert($('lightbarPanel').classList.hidden);
  context.statusData.capabilities={ds4_lightbar:true};delete context.statusData.lightbar;run('renderLightbar()');assert($('lightbarDefaults').disabled);
  console.log('lightbar UI: Nintendo default, Sega/custom edits, P3/P4 retention, refresh, identity-bound override, adapter switch and capability/read failure passed');
})().catch(e=>{console.error(e);process.exitCode=1});
