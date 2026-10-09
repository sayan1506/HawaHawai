import test from 'node:test';import assert from 'node:assert/strict';
import {whatsappLink,nativeShare,copyNotice} from '../src/noticeSharing.ts';
const n={title:'HawaHawai · स्कूल',text:'अभिभावक सूचना\nUS AQI & GRAP UNKNOWN + 2026-10-09\nhttps://example.com/?a=1&b=2',validUntil:'2026-10-09T10:00:00Z'};
test('WhatsApp URL encodes Unicode, line breaks and reserved characters exactly once',()=>{const u=new URL(whatsappLink(n));assert.equal(u.origin,'https://wa.me');assert.equal(u.searchParams.get('text'),n.text);assert.equal([...u.searchParams].length,1);assert.doesNotMatch(u.href,/अभिभावक|\n/);});
test('native sharing passes only the selected public notice, not private records',async()=>{let data;assert.equal(await nativeShare(n,{share:async value=>{data=value;}}),'shared');assert.deepEqual(data,{title:n.title,text:n.text});});
test('unsupported native browsers and canShare refusal have explicit fallback',async()=>{assert.equal(await nativeShare(n,{}),'unsupported');assert.equal(await nativeShare(n,{canShare:()=>false,share:async()=>assert.fail()}),'unsupported');});
test('canceled native sharing is distinct from failure',async()=>{assert.equal(await nativeShare(n,{share:async()=>{throw Object.assign(new Error('cancel'),{name:'AbortError'});}}),'canceled');assert.equal(await nativeShare(n,{share:async()=>{throw new Error('failed');}}),'failed');});
test('copy writes exact selected Hindi notice and reports success only after resolution',async()=>{let text;assert.equal(await copyNotice(n,{writeText:async value=>{text=value;}}),true);assert.equal(text,n.text);});
test('clipboard absent or denied requires manual copying',async()=>{assert.equal(await copyNotice(n),false);assert.equal(await copyNotice(n,{writeText:async()=>{throw new Error('Denied');}}),false);});
