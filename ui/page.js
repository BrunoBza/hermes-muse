const MUSE_CSS = `
.muse-root{--muse-fg:var(--color-foreground,var(--dt-foreground,inherit));--muse-card:var(--color-card,var(--dt-card,transparent));--muse-muted:var(--color-muted-foreground,var(--dt-muted-foreground,color-mix(in srgb,currentColor 62%,transparent)));--muse-border:var(--color-border,var(--dt-border,color-mix(in srgb,currentColor 18%,transparent)));--muse-accent:var(--color-primary,var(--dt-primary,currentColor));--muse-accent-fg:var(--color-primary-foreground,var(--dt-primary-foreground,Canvas));--muse-ring:var(--color-ring,var(--dt-ring,currentColor));--muse-danger:var(--color-destructive,var(--dt-destructive,currentColor));--muse-warn:var(--color-warning,var(--dt-warning,currentColor));--muse-ok:var(--color-success,var(--dt-success,currentColor));--muse-hover:color-mix(in srgb,currentColor 7%,transparent);--muse-radius:var(--radius-lg,var(--theme-radius,8px));--muse-ctl:36px;box-sizing:border-box;width:100%;max-width:880px;margin:0 auto;padding:clamp(16px,4vw,24px);font:inherit;line-height:1.55;color:var(--muse-fg);overflow-wrap:anywhere;word-break:break-word}
.muse-root *,.muse-root *::before,.muse-root *::after{box-sizing:border-box}
.muse-root :where(button,input,select){font:inherit;color:inherit}
.muse-root :focus-visible{outline:2px solid var(--muse-ring);outline-offset:2px}
.muse-header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px}
.muse-title{margin:0;font-size:1.5rem;line-height:1.3;font-weight:700}
.muse-sub{margin:4px 0 0;color:var(--muse-muted);font-size:.85rem}
.muse-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;color:var(--muse-muted);font-size:.85rem}
.muse-profile{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.muse-select,.muse-input{height:var(--muse-ctl);padding:0 12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);max-width:100%}
.muse-input{width:100%;flex:1 1 220px;min-width:0}
.muse-tabs{display:flex;flex-wrap:wrap;gap:4px;margin:16px 0;padding:4px;border:1px solid var(--muse-border);border-radius:calc(var(--muse-radius) + 4px);background:var(--muse-card);width:fit-content;max-width:100%}
.muse-tab,.muse-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:var(--muse-ctl);padding:0 14px;border:1px solid transparent;border-radius:var(--muse-radius);background:transparent;cursor:pointer}
.muse-tab:hover:not(:disabled),.muse-btn:hover:not(:disabled){background:var(--muse-hover)}
.muse-tab[aria-pressed=true]{background:var(--muse-accent);color:var(--muse-accent-fg);font-weight:600}
.muse-tab[aria-pressed=true]:hover{background:var(--muse-accent)}
.muse-count{font-size:.8rem;opacity:.75;font-variant-numeric:tabular-nums}
.muse-btn.primary{background:var(--muse-accent);color:var(--muse-accent-fg)}
.muse-btn.primary:hover:not(:disabled){background:var(--muse-accent);filter:brightness(1.1)}
.muse-btn.secondary{border-color:var(--muse-border)}
.muse-btn.text{padding:0 8px;color:var(--muse-muted)}
.muse-btn.text:hover:not(:disabled){color:var(--muse-fg)}
.muse-btn:disabled{opacity:.5;cursor:default}
.muse-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 16px}
.muse-chip{display:inline-flex;align-items:center;gap:4px;height:var(--muse-ctl);padding:0 4px 0 12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card)}
.muse-list{margin:0;padding:0;list-style:none;border-top:1px solid var(--muse-border)}
.muse-list>li{border-bottom:1px solid var(--muse-border)}
.muse-row{display:block;width:100%;padding:16px 8px;border:0;background:transparent;text-align:left;cursor:pointer;border-radius:var(--muse-radius)}
.muse-row:hover{background:var(--muse-hover)}
.muse-row-static{padding:16px 8px}
.muse-row-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px}
.muse-row-title{font-weight:600;font-size:1rem;display:block}
.muse-row-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:4px;color:var(--muse-muted);font-size:.9rem}
.muse-row-meta{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:6px;color:var(--muse-muted);font-size:.8rem}
.muse-row-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.muse-badge{display:inline-flex;align-items:center;height:22px;padding:0 10px;border:1px solid currentColor;border-radius:999px;font-size:.75rem;font-weight:600;white-space:nowrap;color:var(--muse-muted)}
.muse-badge.warn{color:var(--muse-warn)}.muse-badge.danger{color:var(--muse-danger)}.muse-badge.ok{color:var(--muse-ok)}.muse-badge.accent{color:var(--muse-accent)}
.muse-group{margin:24px 0 8px;font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muse-muted)}
.muse-fold{display:flex;align-items:center;gap:8px;width:100%;height:var(--muse-ctl);margin-top:24px;padding:0 8px;border:0;background:transparent;cursor:pointer;color:var(--muse-muted);font-weight:600;border-radius:var(--muse-radius)}
.muse-fold:hover{background:var(--muse-hover);color:var(--muse-fg)}
.muse-empty{margin:24px 0;padding:24px;border:1px dashed var(--muse-border);border-radius:var(--muse-radius);text-align:center;color:var(--muse-muted)}
.muse-empty strong{display:block;margin-bottom:4px;color:var(--muse-fg)}
.muse-empty .muse-btn{margin-top:12px}
.muse-alert{border-style:solid;border-color:var(--muse-danger);color:var(--muse-fg)}
.muse-detail-title{margin:16px 0 8px;font-size:1.5rem;line-height:1.3}
.muse-detail-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px;padding-top:16px;border-top:1px solid var(--muse-border)}
.muse-section{margin:24px 0 0}
.muse-sh{margin:0 0 8px;font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muse-muted)}
.muse-plain{margin:0;padding-left:20px}
.muse-md>:first-child{margin-top:0}.muse-md>:last-child{margin-bottom:0}
.muse-md h1,.muse-md h2,.muse-md h3,.muse-md h4,.muse-md h5,.muse-md h6{margin:24px 0 8px;line-height:1.3;font-weight:700;text-transform:none;letter-spacing:normal}
.muse-md h1{font-size:1.4rem}.muse-md h2{font-size:1.2rem}.muse-md h3{font-size:1.05rem}.muse-md h4,.muse-md h5,.muse-md h6{font-size:1rem}
.muse-md p,.muse-md ul,.muse-md ol,.muse-md blockquote,.muse-md pre,.muse-md table{margin:0 0 12px}
.muse-md ul,.muse-md ol{padding-left:24px}
.muse-md ul{list-style:disc}.muse-md ol{list-style:decimal}.muse-md ul ul{list-style:circle}.muse-md li::marker{color:var(--muse-muted)}
.muse-plain{list-style:disc}
.muse-md li>ul,.muse-md li>ol{margin:4px 0 0}
.muse-md blockquote{padding:4px 12px;border-left:3px solid var(--muse-border);color:var(--muse-muted)}
.muse-md a{color:var(--muse-accent);text-decoration:underline}
.muse-md code{color:var(--muse-fg);padding:1px 5px;border-radius:4px;background:var(--muse-hover);font-family:var(--theme-font-mono,var(--dt-font-mono,ui-monospace,monospace));font-size:.875em}
.muse-md pre{padding:12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);overflow-x:auto;max-width:100%}
.muse-md pre code{padding:0;background:none;white-space:pre;color:var(--muse-fg)}
.muse-md hr{border:0;border-top:1px solid var(--muse-border);margin:16px 0}
.muse-tablewrap{overflow-x:auto;max-width:100%;margin:0 0 12px}
.muse-md table{border-collapse:collapse;margin:0}
.muse-md th,.muse-md td{padding:6px 10px;border:1px solid var(--muse-border);text-align:left}
.muse-md th{background:var(--muse-hover)}
.muse-admin{margin:16px 0;padding:12px 16px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);font-size:.9rem}
.muse-admin p{margin:8px 0 0}
`;

function museTime(value, withTime) {
  if (typeof value !== 'number' || !isFinite(value)) return '';
  const opts = withTime ? {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'} : {month:'short',day:'numeric'};
  return new Date(value * 1000).toLocaleString('en-US', opts);
}

function museSafeUrl(url) { return /^(https?:|mailto:)/i.test(url) ? url : null; }

// Inline Markdown to React nodes. Raw HTML is never interpreted: React escapes every string.
function museInline(h, text, key) {
  const re = /(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)|!?\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([\s\S]+?)\*\*|~~([\s\S]+?)~~|\*([^*\s][^*]*?)\*|(https?:\/\/[^\s<>)\]]+)/g;
  const out = [];
  let last = 0, m, n = 0;
  const link = (label, url, k) => {
    const safe = museSafeUrl(url);
    return safe ? h('a', {key:k, href:safe, target:'_blank', rel:'noopener noreferrer'}, label) : label;
  };
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = key + ':' + n++;
    if (m[2] !== undefined) out.push(h('code', {key:k}, m[2].trim()));
    else if (m[4] !== undefined) out.push(link(museInline(h, m[3] || m[4], k), m[4], k));
    else if (m[5] !== undefined) out.push(h('strong', {key:k}, museInline(h, m[5], k)));
    else if (m[6] !== undefined) out.push(h('del', {key:k}, museInline(h, m[6], k)));
    else if (m[7] !== undefined) out.push(h('em', {key:k}, museInline(h, m[7], k)));
    else out.push(link(m[8], m[8], k));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// Goal and Feed files start with "# title"; Feed files also end with a "## Sources" list. The page shows both separately.
function museBody(body, title, feed) {
  let text = String(body || '');
  if (title && text.startsWith('# ' + title + '\n\n')) text = text.slice(title.length + 4);
  if (!feed) return text;
  const marker = '\n\n## Sources\n', at = text.lastIndexOf(marker);
  if (at >= 0 && text.slice(at + marker.length).split('\n').every(line => !line || line.startsWith('- '))) text = text.slice(0, at);
  return text;
}

function museMarkdown(h, source) {
  const lines = String(source || '').replace(/\r\n?/g, '\n').split('\n');
  const item = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const cells = line => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  let key = 0;
  function list(i, indent) {
    const ordered = /\d/.test(item.exec(lines[i])[2]);
    const items = [];
    while (i < lines.length) {
      const m = item.exec(lines[i]);
      if (!m || m[1].length < indent || (m[1].length > indent)) break;
      if (/\d/.test(m[2]) !== ordered) break;
      const children = [museInline(h, m[3], 'li' + key++)];
      i++;
      while (i < lines.length) {
        const next = item.exec(lines[i]);
        if (next && next[1].length > indent) { const sub = list(i, next[1].length); children.push(sub.node); i = sub.next; }
        else if (lines[i].trim() && !next && /^\s{2,}\S/.test(lines[i])) { children.push(' ', museInline(h, lines[i].trim(), 'lc' + key++)); i++; }
        else break;
      }
      items.push(h('li', {key:'i' + key++}, ...children));
    }
    return {node:h(ordered ? 'ol' : 'ul', {key:'l' + key++}, ...items), next:i};
  }
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if (!line.trim()) { i++; continue; }
    if ((m = /^\s*(`{3,}|~{3,})/.exec(line))) {
      const body = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith(m[1]); i++) body.push(lines[i]);
      i++;
      blocks.push(h('pre', {key:'b' + key++}, h('code', null, body.join('\n'))));
    } else if ((m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line))) {
      blocks.push(h('h' + m[1].length, {key:'b' + key++}, museInline(h, m[2], 'h' + key)));
      i++;
    } else if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { blocks.push(h('hr', {key:'b' + key++})); i++; }
    else if (/^\s*>/.test(line)) {
      const quote = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) quote.push(lines[i].replace(/^\s*> ?/, ''));
      blocks.push(h('blockquote', {key:'b' + key++}, museMarkdown(h, quote.join('\n'))));
    } else if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      const head = cells(line), rows = [];
      for (i += 2; i < lines.length && lines[i].trim() && lines[i].includes('|'); i++) rows.push(cells(lines[i]));
      blocks.push(h('div', {key:'b' + key++, className:'muse-tablewrap'}, h('table', null,
        h('thead', null, h('tr', null, ...head.map((c, j) => h('th', {key:j}, museInline(h, c, 'th' + j))))),
        h('tbody', null, ...rows.map((r, j) => h('tr', {key:j}, ...head.map((_, k) => h('td', {key:k}, museInline(h, r[k] || '', 'td' + j + k)))))))));
    } else if (item.test(line)) {
      const sub = list(i, item.exec(line)[1].length);
      blocks.push(sub.node); i = sub.next;
    } else {
      const para = [];
      for (; i < lines.length && lines[i].trim() && !/^\s*(#{1,6}\s|>|`{3,}|~{3,})/.test(lines[i]) && !item.test(lines[i]); i++) para.push(lines[i].trim());
      blocks.push(h('p', {key:'b' + key++}, museInline(h, para.join(' '), 'p' + key)));
    }
  }
  return blocks;
}

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
    const [draftQuery, setDraftQuery] = React.useState('');
    const [query, setQuery] = React.useState('');
    const [topic, setTopic] = React.useState('');
    const [topicLabel, setTopicLabel] = React.useState('');
    const [page, setPage] = React.useState(null);
    const [closed, setClosed] = React.useState(null);
    const [closedOpen, setClosedOpen] = React.useState(false);
    const [titles, setTitles] = React.useState({});
    const [counts, setCounts] = React.useState({});
    const [article, setArticle] = React.useState(null);
    const [error, setError] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const generation = React.useRef(0);
    const identity = scope.key + ':' + tab + ':' + query + ':' + topic;
    const active = React.useRef(identity);
    active.current = identity;
    const ready = !profileAdmin || (selectedRow && selectedRow.enabled);
    React.useEffect(()=>{const timer=setTimeout(()=>setQuery(draftQuery.trim()),250);return ()=>clearTimeout(timer);},[draftQuery]);
    async function fetchList(path, extra, cursor) {
      const params = new URLSearchParams({limit: '25', ...extra});
      if (cursor) params.set('cursor', cursor);
      return request(path + '?' + params, scope);
    }
    async function load(cursor) {
      if (!ready) {setBusy(false);return;}
      const token = ++generation.current, captured = identity;
      setBusy(true); setError('');
      try {
        const extra = {};
        if (tab === 'feed') { if (query) extra.query = query; if (topic) extra.topic = topic; }
        if (tab === 'goals') extra.status = 'open';
        const value = await fetchList('/' + tab, extra, cursor);
        if (tab === 'ideas') {
          // Titles only label the groups; a failure here must not hide the ideas.
          try {const goals = await fetchList('/goals', {status:'open'}); setTitles(Object.fromEntries(goals.items.map(g=>[g.id,g.title])));} catch (e) {}
        }
        if (generation.current !== token || active.current !== captured || !scope.current()) return;
        setPage({ ...value, identity: captured, items: cursor ? [...(page?.items || []), ...value.items] : value.items });
        if (!cursor && !(tab === 'feed' && (query || topic))) setCounts(c=>({...c,[tab]:value.total}));
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (generation.current === token) setBusy(false); }
    }
    async function loadClosed(cursor) {
      const captured = identity;
      setBusy(true); setError('');
      try {
        const value = await fetchList('/goals', {status:'closed'}, cursor);
        if (active.current !== captured || !scope.current()) return;
        setClosed(prev=>({...value, identity: captured, items: cursor ? [...(prev?.items || []), ...value.items] : value.items}));
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (active.current === captured) setBusy(false); }
    }
    React.useEffect(() => { setPage(null); setClosed(null); setClosedOpen(false); setArticle(null); load(); return () => { generation.current++; }; }, [identity, ready]);
    React.useEffect(() => {
      if (!ready) return;
      let live = true;
      setCounts({});
      Promise.all([['feed',{}],['ideas',{}],['goals',{status:'open'}],['closed',{status:'closed'}]].map(([name,extra])=>
        request('/'+(name==='closed'?'goals':name)+'?'+new URLSearchParams({limit:'1',...extra}), scope).then(v=>live&&scope.current()&&setCounts(c=>({...c,[name]:v.total}))).catch(()=>{})));
      return ()=>{live=false;};
    }, [scope.key, ready]);
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
    const currentClosed = closed?.identity === identity ? closed : null;
    const currentArticle = article?.identity === identity ? article : null;
    const button = (label, onClick, disabled=false, variant='secondary', extra) => h('button', {type:'button', className:'muse-btn '+variant, onClick, disabled, ...extra}, label);
    const badge = (label, tone) => h('span', {className:'muse-badge'+(tone ? ' '+tone : '')}, label);
    const empty = (title, text, action, alert) => h('div', {className:'muse-empty'+(alert ? ' muse-alert' : ''), role:alert ? 'alert' : undefined}, h('strong', null, title), text, action);
    const goalState = g => g.status === 'done' ? ['Done','ok'] : g.status === 'cancelled' ? ['Cancelled',''] : g.waiting_user ? ['Needs you','warn'] : g.blocked ? ['Blocked','danger'] : ['In progress','accent'];
    const row = (item, index, head, text, meta, onOpen, actions) => {
      const id = 'muse-' + tab + '-' + index;
      return h('li', {key:item.id}, onOpen ?
        h('button', {type:'button', className:'muse-row', onClick:onOpen, 'aria-labelledby':id+'-t', 'aria-describedby':id+'-d'},
          h('span', {className:'muse-row-head'}, h('span', {id:id+'-t', className:'muse-row-title'}, item.title || item.id), head),
          text && h('span', {id:id+'-d', className:'muse-row-text'}, text),
          meta.length > 0 && h('span', {className:'muse-row-meta'}, ...meta.map((m,i)=>h('span',{key:i},m)))) :
        h('div', {className:'muse-row-static'},
          h('div', {className:'muse-row-head'}, h('span', {className:'muse-row-title'}, item.title || item.id), head),
          text && h('div', {className:'muse-row-text'}, text),
          meta.length > 0 && h('div', {className:'muse-row-meta'}, ...meta.map((m,i)=>h('span',{key:i},m))),
          actions));
    };
    const goalRow = (g, i) => {
      const [label, tone] = goalState(g), open_ = g.status === 'active';
      const when = open_ ? (g.deadline ? 'Due ' + museTime(g.deadline) : g.next_check_at ? 'Next check ' + museTime(g.next_check_at, true) : '') : (g.status === 'done' ? 'Completed ' : 'Cancelled ') + museTime(g.updated);
      return row(g, i, badge(label, tone), g.blocked || (g.latest_progress ? 'Latest: ' + g.latest_progress.text : ''), [when, g.deadline && g.next_check_at && open_ ? 'Next check ' + museTime(g.next_check_at, true) : ''].filter(Boolean), ()=>open(g));
    };

    let content;
    if (currentArticle) {
      const md = currentArticle.metadata || {};
      const goal = currentArticle.kind === 'goal';
      const [label, tone] = goalState(md);
      const sources = (md.sources || []).filter(s => typeof s === 'string');
      content = h('article', null,
        button('← Back to list', ()=>setArticle(null), false, 'text'),
        h('h2', {className:'muse-detail-title'}, md.title || currentArticle.id),
        h('div', {className:'muse-meta'}, ...(goal ?
          [badge(label, tone), md.owner && badge('Owner: ' + md.owner.kind), md.deadline && h('span',null,'Due ' + museTime(md.deadline)), md.next_check_at && md.status === 'active' && h('span',null,'Next check ' + museTime(md.next_check_at, true))] :
          [md.created && h('span',null,museTime(md.created)), sources.length > 0 && h('span',null,sources.length + (sources.length === 1 ? ' source' : ' sources'))])),
        goal && md.blocked && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Blocked'), h('div', {className:'muse-md'}, museMarkdown(h, md.blocked))),
        h('div', {className:'muse-md muse-section'}, museMarkdown(h, museBody(currentArticle.body, md.title, !goal))),
        currentArticle.next_offset != null && h('div', {className:'muse-detail-actions'}, button('Continue article',()=>open(currentArticle,true),busy)),
        goal && md.owner && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Owner'), h('div', null, md.owner.kind + ' · ' + md.owner.id)),
        goal && Array.isArray(md.progress) && md.progress.length > 0 && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Progress'),
          h('ul', {className:'muse-plain'}, ...[...md.progress].reverse().map((p,i)=>h('li',{key:i},h('span',{className:'muse-sub'},museTime(p.at,true)+' — '),p.text)))),
        sources.length > 0 && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Sources'),
          h('ul', {className:'muse-plain'}, ...sources.map((s,i)=>h('li',{key:i}, museSafeUrl(s) ? h('a',{href:museSafeUrl(s),target:'_blank',rel:'noopener noreferrer'},s) : s)))),
        draft && h('div', {className:'muse-detail-actions'},
          button(tab==='goals'?'Discuss or change this goal':'Give feedback in chat',()=>draft(currentArticle,scope),busy),
          tab==='goals' && button('Cancel goal in chat',()=>draft(currentArticle,scope,'cancel'),busy)));
    } else if (!currentPage) {
      content = error ? null : busy ? h('p', {role:'status', className:'muse-sub'}, 'Loading…') : null;
    } else if (tab === 'feed') {
      content = currentPage.items.length === 0 ?
        empty(query || topic ? 'No matching articles' : 'No articles yet', query || topic ? 'Try a different search or clear the filters.' : 'New Feed articles will appear here.') :
        h('ul', {className:'muse-list', 'aria-label':'Items'}, ...currentPage.items.map((item,i)=>row(item, i, museTime(item.created) && h('span',{className:'muse-row-meta'},museTime(item.created)), item.why, [item.source_count ? item.source_count + (item.source_count === 1 ? ' source' : ' sources') : ''].filter(Boolean), ()=>open(item))));
    } else if (tab === 'ideas') {
      const groups = [];
      for (const item of currentPage.items) {
        const name = item.goal_id ? (titles[item.goal_id] || 'Related goal') : 'Independent ideas';
        const group = groups.find(g=>g.name === name) || (groups.push({name, items:[]}), groups.at(-1));
        group.items.push(item);
      }
      content = currentPage.items.length === 0 ?
        empty('No ideas yet', 'Ideas are suggested by the nightly review from your active goals. New suggestions will appear here.' + (currentPage.last_review_at ? ' Last review: ' + museTime(currentPage.last_review_at, true) + '.' : ' The nightly review has not run yet.')) :
        groups.map(group=>h('section', {key:group.name}, h('h3', {className:'muse-group'}, group.name),
          h('ul', {className:'muse-list', 'aria-label':group.name}, ...group.items.map((item,i)=>row(item, i, item.status && item.status !== 'candidate' ? badge(item.status) : null, item.rationale || item.why,
            [item.source_count ? item.source_count + (item.source_count === 1 ? ' source' : ' sources') : ''].filter(Boolean), null,
            h('div', {className:'muse-row-actions'},
              (item.goal_id || item.interest_id) && button('Explore topic',()=>{setTab('feed');setTopic(item.goal_id || item.interest_id);setTopicLabel(group.name);}),
              draft && button('Discuss idea in chat',()=>draft(item,scope)),
              draft && button('Accept idea in chat',()=>draft(item,scope,'accept'),false,'primary')))))));
    } else {
      content = h(React.Fragment, null,
        currentPage.items.length === 0 ? empty('No open goals', 'Goals you agree on with Muse appear here while they are in progress.') :
          h('ul', {className:'muse-list', 'aria-label':'Open goals'}, ...currentPage.items.map(goalRow)),
        h('button', {type:'button', className:'muse-fold', 'aria-expanded':closedOpen, onClick:()=>{const next=!closedOpen;setClosedOpen(next);if(next&&!closed)loadClosed();}},
          h('span',{'aria-hidden':'true'},closedOpen ? '▾' : '▸'),h('span',null,'Done and cancelled'), counts.closed !== undefined ? h('span',{className:'muse-count'},counts.closed) : null),
        closedOpen && currentClosed && (currentClosed.items.length === 0 ? empty('Nothing here yet', 'Completed and cancelled goals will be listed here.') :
          h('ul', {className:'muse-list', 'aria-label':'Closed goals'}, ...currentClosed.items.map(goalRow))),
        closedOpen && currentClosed?.next_cursor && button('Load more closed goals',()=>loadClosed(currentClosed.next_cursor),busy,'text'));
    }
    const label = {feed:'Feed', ideas:'Ideas', goals:'Goals'};
    return h('main', {className:'muse-root'},
      h('style', null, MUSE_CSS),
      h('header', {className:'muse-header'},
        h('div', null, h('h1', {className:'muse-title'}, 'Muse'), h('p', {className:'muse-sub'}, scope.label)),
        profileAdmin && h('div', {className:'muse-profile'},
          h('label',{className:'muse-meta'},'Profile ',h('select',{className:'muse-select',value:selected||'',disabled:managementBusy,onChange:e=>{setSelected(e.target.value||null);setDraftQuery('');setQuery('');setTopic('');setManagementMessage('');}},
            h('option',{value:''},'Choose a profile…'),
            ...profiles.map(row=>h('option',{key:row.name,value:row.name},row.name+' · '+(row.installed?(row.enabled?'Enabled':'Disabled'):'Not installed')+(row.read_only?' · Managed by Hermes':'')))))),
        ),
      profileAdmin && (selectedRow || managementMessage || managementBusy) && h('section',{'aria-label':'Muse profiles',className:'muse-admin'},
        selectedRow && h('div',{className:'muse-meta'},(selectedRow.version?'Muse '+selectedRow.version+' · ':'')+(selectedRow.enabled?'Enabled':selectedRow.installed?'Disabled — data retained':'Not installed'),selectedRow.read_only&&' · Read-only: default is managed by Hermes'),
        selectedRow?.read_only && h('p',{className:'muse-sub'},'Manage its installation with Hermes.'),
        selectedRow && !selectedRow.read_only && h('p',null,button(selectedRow.enabled?'Disable Muse':'Install / enable Muse',()=>changeProfile(selectedRow.enabled?'disable':'enable'),managementBusy,selectedRow.enabled?'secondary':'primary')),
        selectedRow && !selectedRow.read_only && h('p',{className:'muse-sub'},'Disable retains data and pauses only owned Muse tasks. Enable resumes only tasks paused by this page that are still eligible; user pauses and schedules are preserved.'),
        managementBusy && h('p',{role:'status'},'Applying the selected profile change…'),
        managementMessage && h('p',{role:'status'},managementMessage)),
      profileAdmin && !ready && empty(selectedRow ? 'Muse is not enabled for this profile' : 'No profile selected', selectedRow ? 'Enable Muse above to browse its Feed, Ideas and Goals.' : 'Choose a profile to browse its Feed, Ideas and Goals.'),
      ready && h('nav', {'aria-label':'Muse sections', className:'muse-tabs'},
        ...['feed','ideas','goals'].map(name => h('button', {key:name, type:'button', className:'muse-tab', 'aria-pressed':tab===name, 'aria-label':label[name], onClick:()=>setTab(name)}, label[name], counts[name] !== undefined && h('span', {className:'muse-count'}, counts[name])))),
      ready && tab === 'feed' && !currentArticle && h('form', {className:'muse-toolbar', onSubmit:e=>{e.preventDefault(); setQuery(draftQuery.trim());}},
        h('input', {className:'muse-input', type:'search', 'aria-label':'Search articles', value:draftQuery, placeholder:'Search title or keyword', onChange:e=>setDraftQuery(e.target.value)}),
        topic && h('span', {className:'muse-chip'}, 'Topic: ' + (topicLabel || 'selected'), button('✕',()=>{setTopic('');setTopicLabel('');},false,'text',{'aria-label':'Clear topic filter'})),
        (draftQuery || topic) && button('Clear',()=>{setDraftQuery('');setQuery('');setTopic('');setTopicLabel('');},false,'text')),
      ready && error && empty('Something went wrong', error, button('Retry',()=>currentArticle?open(currentArticle):load(),busy), true),
      ready && (currentPage || currentArticle) && busy && h('p', {role:'status', className:'muse-sub'}, 'Loading…'),
      ready && content,
      ready && !currentArticle && currentPage?.next_cursor && h('div', {className:'muse-toolbar'}, button('Load more',()=>load(currentPage.next_cursor),busy)));
  };
}
