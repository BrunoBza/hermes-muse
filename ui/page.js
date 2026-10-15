function makeMusePage(React, useScope, request, draft, profileAdmin) {
  const h = React.createElement;
  return function MusePage() {
    const hostScope = useScope();
    const [profiles, setProfiles] = React.useState([]);
    const [selected, setSelected] = React.useState(null);
    const [managementBusy, setManagementBusy] = React.useState(false);
    const [managementMessage, setManagementMessage] = React.useState('');
    const [managementVersion, setManagementVersion] = React.useState(0);
    const selectionRef = React.useRef(selected);
    selectionRef.current = selected;
    const pendingChange = React.useRef(null);
    const selectedRow = profiles.find(row=>row.name===selected);
    const scope = profileAdmin ? {...hostScope, profile:selected, key:hostScope.key+':'+selected+':'+managementVersion,
      label:selected ? hostScope.label+' · '+selected : 'Select a profile on this Hermes host',
      current:()=>hostScope.current() && selectionRef.current===selected} : hostScope;
    React.useEffect(()=>{
      if (!profileAdmin) return;
      let active=true;setSelected(null);setProfiles([]);setManagementMessage('');
      profileAdmin.list().then(value=>{if(active)setProfiles(value.profiles);}).catch(e=>{if(active)setManagementMessage(String(e.message||e));});
      return ()=>{active=false;};
    },[hostScope.key]);
    async function changeProfile(operation) {
      if (!selectedRow || selectedRow.read_only) return;
      const target=selected;
      setManagementBusy(true);setManagementMessage('');
      if (!pendingChange.current || pendingChange.current.name!==target || pendingChange.current.data.operation!==operation) {
        pendingChange.current={name:target,data:{operation,expected_revision:selectedRow.revision,request_id:crypto.randomUUID()}};
      }
      try {
        const value=await profileAdmin.change(target,pendingChange.current.data);
        const list=await profileAdmin.list();
        if (!hostScope.current()) return;
        setProfiles(list.profiles);setManagementVersion(n=>n+1);
        if (selectionRef.current===target) setManagementMessage(value.partial ? 'Preparation is incomplete. Retry to continue the same operation.' : value.restart_required || value.activation?.restart_required ? 'Selection saved. Runtime activation needs attention; existing sessions may retain their previous tools.' : 'Profile updated. Existing conversations keep their current tools until a new session.');
        if (!value.partial) pendingChange.current=null;
      } catch(e) { if(hostScope.current())setManagementMessage(String(e.message||e)); }
      finally {setManagementBusy(false);}
    }
    const [tab, setTab] = React.useState('feed');
    const [query, setQuery] = React.useState('');
    const [topic, setTopic] = React.useState('');
    const [page, setPage] = React.useState(null);
    const [article, setArticle] = React.useState(null);
    const [error, setError] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const generation = React.useRef(0);
    const identity = scope.key + ':' + tab + ':' + query + ':' + topic;
    const active = React.useRef(identity);
    active.current = identity;
    async function load(cursor) {
      if (profileAdmin && (!selectedRow || !selectedRow.enabled)) {setBusy(false);return;}
      const token = ++generation.current, captured = identity;
      setBusy(true); setError('');
      try {
        const params = new URLSearchParams({limit: '25'});
        if (cursor) params.set('cursor', cursor);
        if (tab === 'feed') { if (query) params.set('query', query); if (topic) params.set('topic', topic); }
        const value = await request('/' + tab + '?' + params, scope);
        if (generation.current !== token || active.current !== captured || !scope.current()) return;
        setPage({ ...value, identity: captured, items: cursor ? [...(page?.items || []), ...value.items] : value.items });
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (generation.current === token) setBusy(false); }
    }
    React.useEffect(() => { setPage(null); setArticle(null); load(); return () => { generation.current++; }; }, [identity]);
    async function open(item, continuation) {
      const captured = identity, token = ++generation.current;
      setBusy(true); setError('');
      try {
        const params = new URLSearchParams();
        if (continuation) { params.set('offset', article.next_offset); params.set('revision', article.revision); }
        const value = await request('/' + tab + '/' + encodeURIComponent(item.id) + '?' + params, scope);
        if (generation.current !== token || active.current !== captured || !scope.current()) return;
        setArticle({...value, identity: captured, body: continuation ? article.body + value.body : value.body});
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (active.current === captured) setBusy(false); }
    }
    const currentPage = page?.identity === identity ? page : null;
    const currentArticle = article?.identity === identity ? article : null;
    const button = (label, onClick, disabled=false) => h('button', {type:'button', onClick, disabled, style:{padding:'10px 14px',border:'1px solid currentColor',borderRadius:8,background:'transparent',color:'inherit',cursor:disabled?'default':'pointer'}}, label);
    return h('main', {style:{maxWidth:960,margin:'0 auto',padding:'clamp(16px,4vw,32px)',fontFamily:'inherit',lineHeight:1.6,overflowWrap:'anywhere'}},
      h('h1', null, 'Muse'), h('p', null, scope.label),
      profileAdmin && h('section',{'aria-label':'Muse profiles',style:{padding:'16px 0'}},
        h('label',null,'Profile ',h('select',{value:selected||'',disabled:managementBusy,onChange:e=>{setSelected(e.target.value||null);setQuery('');setTopic('');setManagementMessage('');},style:{padding:10,background:'transparent',color:'inherit',border:'1px solid #8888',borderRadius:8}},
          h('option',{value:''},'Choose a profile…'),
          ...profiles.map(row=>h('option',{key:row.name,value:row.name},row.name+' · '+(row.installed?(row.enabled?'enabled':'disabled'):'not installed')+(row.read_only?' · managed by Hermes':''))))),
        selectedRow && h('p',null,(selectedRow.version?'Muse '+selectedRow.version+' · ':'')+(selectedRow.enabled?'Enabled':selectedRow.installed?'Disabled — data retained':'Not installed')),
        selectedRow?.read_only && h('p',null,'Default is read-only here. Manage its installation with Hermes.'),
        selectedRow && !selectedRow.read_only && button(selectedRow.enabled?'Disable Muse':'Install / enable Muse',()=>changeProfile(selectedRow.enabled?'disable':'enable'),managementBusy),
        selectedRow && !selectedRow.read_only && h('p',null,'Disable retains data and pauses only owned Muse tasks. Enable resumes only tasks paused by this page that are still eligible; user pauses and schedules are preserved.'),
        managementBusy && h('p',{role:'status'},'Applying the selected profile change…'),
        managementMessage && h('p',{role:'status'},managementMessage)),
      h('nav', {'aria-label':'Muse sections',style:{display:'flex',gap:8,flexWrap:'wrap'}},
        ...['feed','ideas','goals'].map(name => button(name === 'feed' ? 'Feed' : name === 'ideas' ? 'Ideas' : 'Goals', () => setTab(name), tab === name))),
      tab === 'feed' && h('form', {onSubmit:e=>{e.preventDefault(); setArticle(null); load();},style:{display:'flex',gap:8,flexWrap:'wrap',margin:'20px 0'}},
        h('label', {style:{display:'grid',gap:6,flex:'1 1 220px'}}, 'Search articles',h('input', {value:query,placeholder:'Title or keyword',onChange:e=>setQuery(e.target.value),style:{padding:10,width:'100%',border:'1px solid #8888',borderRadius:8,background:'transparent',color:'inherit'}})),
        topic && h('p', null, 'Showing the selected topic'),
        button('All articles',()=>{setQuery('');setTopic('');})),
      error && h('p', {role:'alert'},error), busy && h('p', {role:'status'},'Loading…'),
      currentArticle ? h('article', null, button('Back to list',()=>setArticle(null)),
        h('h2',null,currentArticle.metadata?.title || currentArticle.id),
        currentArticle?.kind==='goal' && h('p',null,'Status: '+currentArticle.metadata.status+' · Owner: '+(currentArticle.metadata.owner ? JSON.stringify(currentArticle.metadata.owner) : 'unassigned')),

        h('div',{style:{whiteSpace:'pre-wrap'}},currentArticle.body),
        currentArticle.next_offset != null && button('Continue article',()=>open(currentArticle,true),busy),
        draft && button(tab==='goals'?'Discuss or change this goal':'Give feedback in chat',()=>draft(currentArticle,scope),busy),
        draft && tab==='goals' && button('Cancel goal in chat',()=>draft(currentArticle,scope,'cancel'),busy)) :
      h('section',{'aria-label':'Items'},
        currentPage && h('p',null,currentPage.total + ' items'),
        currentPage?.items.map(item=>h('article',{key:item.id,style:{padding:'20px 0',borderBottom:'1px solid #8885'}},
          h('h2',{style:{fontSize:20}},tab==='ideas'? item.title : button(item.title || item.id,()=>open(item))),
          h('p',null,item.why || item.rationale || item.status || ''),
          (item.goal_id || item.interest_id) && button('Explore topic',()=>{setTab('feed');setTopic(item.goal_id || item.interest_id);}),
          draft && tab==='ideas' && button('Discuss idea in chat',()=>draft(item,scope)),
          draft && tab==='ideas' && button('Accept idea in chat',()=>draft(item,scope,'accept')))),
        currentPage?.items.length===0 && h('p',null,'No items in this scope.'),
        currentPage?.next_cursor && button('Load more',()=>load(currentPage.next_cursor),busy)));
  };
}
