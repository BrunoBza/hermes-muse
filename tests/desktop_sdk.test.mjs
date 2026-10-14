import {describe,it,expect} from 'vitest';
import {render,screen,fireEvent,waitFor,act,cleanup} from '@testing-library/react';
import {$activeGatewayProfile} from '@host/store/profile.ts';
import {$connection,$activeSessionId,$selectedStoredSessionId,$sessions} from '@host/store/session.ts';
import {onComposerInsertRequest,ackComposerInsert,onComposerSubmitRequest} from '@host/app/chat/composer/focus.ts';
import {createPluginContext} from '@host/contrib/plugin.ts';
import {registry} from '@host/contrib/registry.ts';
import {setApiRequestProfile,setApiRequestConnection} from '@host/api/client.ts';
import plugin from '@muse/desktop/plugin.js';
import {ROUTES_AREA,SIDEBAR_NAV_AREA} from '@hermes/plugin-sdk';

describe('Muse in the installed Desktop SDK',()=>{
 it('registers real scoped contributions and performs authenticated profile REST',async()=>{
  const calls=[],disposers=[];
  window.hermesDesktop={...(window.hermesDesktop||{}),api:async request=>{
   calls.push(request);
   const url=new URL(request.path,process.env.MUSE_TEST_URL);
   if(request.profile)url.searchParams.set('profile',request.profile);
   const response=await fetch(url,{headers:{Authorization:'Bearer muse-isolated-browser-fixture'}});
   if(!response.ok)throw new Error('HTTP '+response.status);
   return response.json();
  }};
  const ctx=createPluginContext('hermes-muse',fn=>disposers.push(fn));
  plugin.register(ctx);
  expect(registry.getArea(ROUTES_AREA).some(x=>x.id==='hermes-muse:page')).toBe(true);
  expect(registry.getArea(SIDEBAR_NAV_AREA).some(x=>x.id==='hermes-muse:nav')).toBe(true);
  setApiRequestConnection('fixture-connection');setApiRequestProfile('cedar');
  const cedar=await ctx.rest('/goals/research');
  expect(cedar.metadata.title).toBe('Cedar research');
  expect(calls.at(-1).connectionId).toBe('fixture-connection');
  setApiRequestProfile('default');
  const orchid=await ctx.rest('/goals/research');
  expect(orchid.metadata.title).toBe('Orchid research');
  expect(orchid.scope_token).not.toBe(cedar.scope_token);
  expect(calls.every(x=>x.path.startsWith('/api/plugins/hermes-muse/'))).toBe(true);
  disposers.forEach(fn=>fn());
  expect(registry.getArea(ROUTES_AREA).some(x=>x.id==='hermes-muse:page')).toBe(false);
 });
 it('renders the shipped page, routes only a draft to the selected real chat, and discards stale scope responses',async()=>{
  const disposers=[],requests=[],inserts=[],submits=[];
  window.hermesDesktop.api=async request=>{
   requests.push(request);
   const url=new URL(request.path,process.env.MUSE_TEST_URL);
   if(request.profile)url.searchParams.set('profile',request.profile);
   const response=await fetch(url,{headers:{Authorization:'Bearer muse-isolated-browser-fixture'}});
   if(!response.ok)throw new Error('HTTP '+response.status);
   return response.json();
  };
  await act(async()=>{
   $connection.set({connectionId:'fixture-connection',mode:'remote',baseUrl:process.env.MUSE_TEST_URL});
   $activeGatewayProfile.set('cedar');setApiRequestProfile('cedar');setApiRequestConnection('fixture-connection');
   $activeSessionId.set('fixture-chat');$selectedStoredSessionId.set('fixture-chat');
   $sessions.set([{id:'fixture-chat',profile:'cedar',connection_id:'fixture-connection',source:'cli'}]);
  });
  const offInsert=onComposerInsertRequest(detail=>{inserts.push(detail);ackComposerInsert(detail.token,true);});
  const offSubmit=onComposerSubmitRequest(detail=>submits.push(detail));
  const ctx=createPluginContext('hermes-muse',fn=>disposers.push(fn));plugin.register(ctx);
  render(registry.getArea(ROUTES_AREA).find(x=>x.id==='hermes-muse:page').render());
  await screen.findByRole('button',{name:'Cedar article 106'});
  fireEvent.click(screen.getByRole('button',{name:'Goals'}));
  fireEvent.click(await screen.findByRole('button',{name:'Cedar research'}));
  fireEvent.click(await screen.findByRole('button',{name:'Discuss or change this goal'}));
  await waitFor(()=>expect(inserts).toHaveLength(1));
  expect(inserts[0].target).toBe('main');expect(inserts[0].text).toContain('research');expect(submits).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:'Cancel goal in chat'}));
  await waitFor(()=>expect(inserts).toHaveLength(2));
  expect(inserts[1].text).toContain('Please cancel');expect(submits).toHaveLength(0);
  const before=requests.length;
  await act(async()=>{$selectedStoredSessionId.set('wrong-chat');$activeSessionId.set('wrong-chat');});
  fireEvent.click(screen.getByRole('button',{name:'Discuss or change this goal'}));
  expect(inserts).toHaveLength(2);expect(requests.length).toBe(before);
  cleanup();disposers.forEach(fn=>fn());offInsert();offSubmit();

  let release;const hold=new Promise(resolve=>{release=resolve;});
  window.hermesDesktop.api=async request=>{
   const url=new URL(request.path,process.env.MUSE_TEST_URL);
   if(request.profile)url.searchParams.set('profile',request.profile);
   const response=await fetch(url,{headers:{Authorization:'Bearer muse-isolated-browser-fixture'}});
   const data=await response.json();if(request.profile==='default')await hold;return data;
  };
  await act(async()=>{$activeGatewayProfile.set('default');setApiRequestProfile('default');});
  const cleanupFns=[];plugin.register(createPluginContext('hermes-muse',fn=>cleanupFns.push(fn)));
  render(registry.getArea(ROUTES_AREA).find(x=>x.id==='hermes-muse:page').render());
  await act(async()=>{$activeGatewayProfile.set('cedar');setApiRequestProfile('cedar');});
  await screen.findByRole('button',{name:'Cedar article 106'});
  await act(async()=>{release();});
  expect(screen.queryByRole('button',{name:'Orchid article 106'})).toBeNull();
  cleanup();cleanupFns.forEach(fn=>fn());
 });

});
