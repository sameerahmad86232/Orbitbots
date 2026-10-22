from playwright.sync_api import sync_playwright
MOCK = r'''(() => {
const saved=JSON.parse(sessionStorage.getItem('test-saved')||'null');
window.testActions=[];window.testTask=null;window.testCalls=[];window.testSaved='';
window.Orbit={
 load:()=>JSON.stringify({state:saved||{},hasKey:false,native:true,provider:JSON.parse(sessionStorage.getItem('test-provider')||'null')||{type:'xai',base:'https://api.x.ai/v1'}}),
 save:value=>{window.testSaved=value;sessionStorage.setItem('test-saved',value);return '{"ok":true}';},
 computerConfig:()=>'{"base":"https://computer.example"}',configureComputer:()=>'{"ok":true,"message":"Saved"}',setComputerNotifications:()=>'{"ok":true,"message":"Scheduled"}',notificationSettings:()=>window.testCalls.push(['notifications']),
 importBots:()=>window.nativeEvent({type:'botImport',data:JSON.stringify({name:'Imported helper',instructions:'Help with my notes.',api_key:'must-not-be-imported',messages:[{role:'user',content:'<img src=x onerror=alert(1)>'}]})}),
 computerRequest:(path,method,body)=>{window.testCalls.push(['computer',path,method,body]);if(path==='/screen'){window.nativeEvent({type:'computerScreen',data:{path,data:'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'}});return;}if(path==='/actions'&&method==='POST'){window.testActions.push({id:'a'.repeat(32),status:'pending',payload:JSON.parse(body)});window.nativeEvent({type:'computer',data:{path,data:{id:'a'.repeat(32),status:'pending'}}});}else if(path.includes('/review')){window.testActions=[];window.nativeEvent({type:'computer',data:{path,data:{status:'done'}}});}else window.nativeEvent({type:'computer',data:{path,data:{actions:window.testActions}}});},
 configure:value=>{const cfg=JSON.parse(value);sessionStorage.setItem('test-provider',value);window.testCalls.push(['configure',cfg]);return JSON.stringify({ok:true,hasKey:cfg.type==='ollama',message:'Connection saved'});},
 setKey:key=>{window.testCalls.push(['key-length',key.length]);return '{"ok":true,"message":"Saved encrypted"}';},
 forgetKey:()=>{},models:()=>window.nativeEvent({type:'models',data:{data:[{id:'test-model'},{id:'grok-4.7'}]}}),
 start:(id,payload)=>{window.testCalls.push(['start',id,JSON.parse(payload)]);window.testTask={id,status:'completed',text:'Fixture result only — not a live API response.\n```csv\nsku,stock\nA,2\n```',events:[{time:Date.now(),text:'Fixture tool: save_file'}],artifacts:['fixture.csv'],drafts:[{to:'recipient@example.com',subject:'Fixture draft',body:'Review me'}],citations:[{url:'https://example.com/source',title:'Fixture source'}],inputTokens:12,outputTokens:8};return '{"ok":true}';},
 task:()=>JSON.stringify(window.testTask||{status:'queued'}),cancel:()=>{},files:()=>JSON.stringify((window.testTask||window.testCalls.some(c=>c[0]==='knowledge'))?['fixture.csv']:[]),memory:()=>'',setMemory:()=>'{"ok":true}',
 download:(bot,name)=>window.testCalls.push(['download',bot,name]),exportText:(name,mime,text)=>window.testCalls.push(['export',name,mime,text]),
 attach:()=>window.nativeEvent({type:'attachment',data:{name:'fixture.csv',mime:'text/csv',type:'input_text',text:'sku,stock\nA,2'}}),dictate:()=>window.nativeEvent({type:'dictation',data:'Please test this task.'}),
 setSpeechRate:value=>window.testCalls.push(['speed',value]),stopSpeech:()=>{},importKnowledge:(bot,name,text)=>{window.testCalls.push(['knowledge',bot,name,text]);return '{"ok":true,"message":"Knowledge saved"}';},readFile:()=>JSON.stringify({ok:true,text:'Fixture file content'}),
 speak:text=>window.testCalls.push(['speak',text]),link:url=>window.testCalls.push(['link',url]),email:(to,subject,body)=>window.testCalls.push(['email',to,subject,body]),erase:()=>'{"ok":true}',deleteBot:()=>'{"ok":true}'
};
})();'''
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 context=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
 context.add_init_script(MOCK);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
 page.goto('http://127.0.0.1:8015/')
 assert page.locator('.card').count()==3
 page.locator('[data-tab=settings]').click();page.locator('#key').fill('fixture-key-not-real')
 page.get_by_role('button',name='Save key',exact=True).click()
 assert page.locator('#key').input_value()==''
 assert page.evaluate("!window.testSaved.includes('fixture-key-not-real')")
 page.get_by_role('button',name='Load models from my key').click();assert page.locator('#model-list option').count()==2
 page.locator('#model').fill('test-model');page.get_by_role('button',name='Save task settings').click()
 page.locator('[data-tab=bots]').click();page.locator('.card').first.click()
 page.get_by_role('button',name='＋',exact=True).click();page.locator('#prompt').fill('Create a CSV and draft a reply.')
 page.get_by_role('button',name='Run task ↗').click();page.wait_for_selector('.status.completed')
 assert 'Fixture result' in page.locator('.messages').inner_text()
 request=page.evaluate("window.testCalls.find(c=>c[0]==='start')[2]")
 assert request['config']['model']=='test-model'
 assert 'fixture.csv' in request['input'][-1]['content'][-1]['text']
 page.get_by_role('button',name='Review draft').click();page.locator('#draft-subject').fill('Edited fixture')
 page.get_by_role('button',name='Open in email app').click()
 assert page.evaluate("window.testCalls.find(c=>c[0]==='email')[2]")=='Edited fixture'
 page.locator('#close-modal').click();page.get_by_role('button',name='Download fixture.csv').click()
 assert page.evaluate("window.testCalls.some(c=>c[0]==='download')")
 page.locator('#back').click();page.locator('[data-tab=routines]').click();page.get_by_role('button',name='+ New routine').click()
 page.locator('#routine-instruction').fill('Research a topic.');page.get_by_role('button',name='Save routine').click()
 assert not page.locator('.check input').is_checked()
 page.locator('[data-tab=settings]').click();page.get_by_label('Appearance',exact=True).select_option('light');assert page.locator('body').evaluate("e=>e.classList.contains('light')")
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.locator('[data-tab=bots]').click();page.get_by_role('button',name='+ New bot').click();page.locator('#bot-name').fill('<img src=x onerror="window.injected=true">');page.get_by_role('button',name='Save bot').click()
 assert page.locator('.card').count()==4;assert not page.evaluate('!!window.injected')
 page.reload();assert page.locator('.card').count()==4
 search=page.get_by_label('Search bots and chats');search.fill('Scout');assert page.locator('.card:visible').count()==1;search.fill('no such conversation word');assert page.locator('.card:visible').count()==0;search.fill('');assert page.locator('.card:visible').count()==4
 page.locator('[data-tab=settings]').click();page.get_by_label('Read-aloud speed').select_option('0.5');page.reload();page.locator('[data-tab=settings]').click();assert page.get_by_label('Read-aloud speed').input_value()=='0.5'
 page.get_by_label('Provider preset').select_option('ollama');page.locator('#provider-base').fill('http://192.168.1.2:11434/v1');page.get_by_role('button',name='Save connection',exact=True).click();assert page.locator('#connection').inner_text()=='Ollama set';assert page.evaluate('window.testCalls.some(c=>c[0]==="configure"&&c[1].type==="ollama")')
 page.locator('[data-tab=files]').click();page.get_by_role('button',name='Import for Scout',exact=True).click();assert page.evaluate('window.testCalls.some(c=>c[0]==="knowledge")');page.get_by_role('button',name='View',exact=True).first.click();assert 'Fixture file content' in page.locator('#modal').inner_text();page.locator('#close-modal').click()
 page.locator('[data-tab=bots]').click();page.get_by_role('button',name='Templates',exact=True).click();page.get_by_role('button',name='Use Atlas',exact=True).click();assert page.locator('.card').count()==5
 page.get_by_role('button',name='Import bot',exact=True).click();assert 'JSON migration support' in page.locator('#modal').inner_text();page.get_by_role('button',name='Import 1 bot',exact=True).click();assert page.locator('.card').count()==6;assert page.evaluate('!window.testSaved.includes("must-not-be-imported")')
 page.locator('[data-tab=computer]').click();assert 'connected' in page.locator('#desktop-status').inner_text().lower();page.locator('#desktop-text').fill('https://example.com');page.get_by_role('button',name='Queue for approval',exact=True).click();assert 'open_url' in page.locator('#desktop-approvals').inner_text();page.get_by_role('button',name='Approve once',exact=True).click();assert 'No actions waiting' in page.locator('#desktop-approvals').inner_text()
 page.locator('[data-tab=settings]').click();page.get_by_role('button',name='Notification permissions',exact=True).click();assert page.evaluate('window.testCalls.some(c=>c[0]==="notifications")')
 page.locator('[data-tab=settings]').click();page.get_by_role('button',name='Full feature checklist').click();assert 'Not implemented' in page.locator('#modal').inner_text();assert '24/7' in page.locator('#modal').inner_text();page.locator('#close-modal').click()
 page.screenshot(path='/workspace/Orbit-Bots-preview.png',full_page=True)
 assert not errors, errors
 context.close()
 # Preview cannot make live requests without the native bridge.
 page=b.new_page(viewport={'width':390,'height':844});page.goto('http://127.0.0.1:8015/');page.locator('[data-tab=settings]').click();assert 'Browser preview' in page.locator('#view').inner_text();b.close()
print('PASS: bot creation/persistence, secret exclusion, model selection, attachments, task results, file export, editable email review, routines disabled by default, theme, mobile layout and untrusted-text rendering. Native runtime mocked; no real API call made.')
