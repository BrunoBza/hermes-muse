"""Deterministic stdlib packaging; both SDKs use the same read-only component."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = (root / "ui/page.js").read_text()
(root / "dashboard/dist/index.js").write_text(
    """(function () {
const SDK = window.__HERMES_PLUGIN_SDK__;
if (!SDK?.React || typeof SDK.fetchJSON !== 'function') return;
const React = SDK.React;
function key() { return location.origin + ':' + (new URLSearchParams(location.search).get('profile') || ''); }
function useScope() {
  const [value, setValue] = React.useState(key());
  React.useEffect(() => { const check=()=>setValue(key()); const timer=setInterval(check,100); window.addEventListener('popstate',check); return ()=>{clearInterval(timer);window.removeEventListener('popstate',check);}; }, []);
  const profile = new URLSearchParams(location.search).get('profile');
  return {key:value, profile, label:location.host + ' · ' + (profile || 'Serving profile'), current:()=>key()===value};
}
function request(path,scope) { return SDK.fetchJSON('/api/plugins/hermes-muse'+path+(path.includes('?')?'&':'?')+'profile='+encodeURIComponent(scope.profile || '')); }
"""
    + page
    + "\nwindow.__HERMES_PLUGINS__.register('hermes-muse',makeMusePage(React,useScope,request,null));\n})();\n"
)
(root / "desktop/plugin.js").write_text(
    """import React from 'react';
import {host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA} from '@hermes/plugin-sdk';
"""
    + page
    + """
export default {
 id:'hermes-muse',name:'Muse',
 register(ctx) {
  if (!ctx.rest || !host.state.profile || !host.state.connectionId) {
   ctx.register({id:'page',area:ROUTES_AREA,data:{path:'/muse'},render:()=>React.createElement('p',null,'Update Hermes Desktop to a build with scoped plugin REST and connection identity to view Muse safely.')});
   return;
  }
  function useScope() {
   const profile=useValue(host.state.profile), connection=useValue(host.state.connectionId);
   return {key:connection+':'+profile,profile,connection,label:(connection || 'Local')+' · '+profile,
    current:()=>host.state.profile.get()===profile && host.state.connectionId.get()===connection};
  }
  async function request(path,scope) {
   if (!scope.current()) throw new Error('Connection changed; refresh Muse');
   return ctx.rest(path+(path.includes('?')?'&':'?')+'profile='+encodeURIComponent(scope.profile));
  }
  async function draft(item,scope,intent="discuss") {
   if (!scope.current()) return;
   if (!host.state.focusedSessionOwner || !host.composer?.insertText) { host.notify({kind:'info',message:'This Desktop build does not support safely addressed chat drafts. Update Desktop first.'}); return; }
   const sid=host.state.focusedSessionId.get(),stored=host.state.focusedStoredSessionId.get(),owner=host.state.focusedSessionOwner.get();
   const original=item.metadata?.session_id;
   if (!sid || !stored || !owner || owner.profile!==scope.profile || owner.connectionId!==scope.connection || (original && stored!==original)) {
    host.notify({kind:'info',message:'Select the original chat in this connection and profile, then try again.'}); return;
   }
   const ok=await host.composer.insertText(sid,'Please '+intent+' this Muse '+(item.kind || 'item')+' '+item.id+' (scope '+item.scope_token+'). Read its current state before changing anything.');
   if (!ok) host.notify({kind:'info',message:'Open the selected chat composer and try again.'});
  }
  const Page=makeMusePage(React,useScope,request,draft);
  ctx.register({id:'page',area:ROUTES_AREA,data:{path:'/muse'},render:()=>React.createElement(Page)});
  ctx.register({id:'nav',area:SIDEBAR_NAV_AREA,data:{path:'/muse',label:'Muse',codicon:'sparkle'}});
 }
};
"""
)
