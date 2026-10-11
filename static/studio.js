(function(){
  var API = '';
  var template = 'Mobile App';
  var lang = 'en';
  var prdMd = '';
  var lastProjectId = null;
  var $ = function(id){ return document.getElementById(id); };

  document.querySelectorAll('#templates .tpl').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#templates .tpl').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on'); template = b.dataset.t;
    });
  });
  document.querySelectorAll('#langs .tpl').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#langs .tpl').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on'); lang = b.dataset.l;
    });
  });
  document.querySelectorAll('.tab').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on');
      $('viewPrd').hidden = b.dataset.v !== 'prd';
      $('viewArch').hidden = b.dataset.v !== 'arch';
      $('viewErd').hidden = b.dataset.v !== 'erd';
    });
  });

  function setStatus(msg, err){ var s=$('status'); if(!s) return; s.className='status'+(err?' err':''); s.innerHTML=msg; }

  // ---- wizard steps ----
  var step = 1;
  var TOTAL = 3;
  function showStep(n){
    step = Math.max(1, Math.min(TOTAL, n));
    document.querySelectorAll('.wz-page').forEach(function(p){ p.classList.toggle('on', +p.dataset.p === step); });
    document.querySelectorAll('.wz-dot').forEach(function(d){
      var s = +d.dataset.s;
      d.classList.toggle('on', s === step);
      d.classList.toggle('done', s < step);
    });
    $('backBtn').hidden = step === 1;
    $('nextBtn').hidden = step === TOTAL;
    $('genBtn').hidden = step !== TOTAL;
    if($('genMultiBtn')) $('genMultiBtn').hidden = step !== TOTAL;
    setStatus('');
  }
  if($('nextBtn')) $('nextBtn').addEventListener('click', function(){
    if(step === 1 && !$('name').value.trim()){ setStatus('Enter an app name first.', true); return; }
    showStep(step + 1);
  });
  if($('backBtn')) $('backBtn').addEventListener('click', function(){ showStep(step - 1); });

  $('suggestBtn').addEventListener('click', function(){
    var title = $('name').value.trim();
    if(!title){ setStatus('Enter an app name first.', true); return; }
    $('suggestBtn').disabled = true; setStatus('<span class="spin"></span>Thinking of suggestions...');
    fetch(API+'/api/suggest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title,template:template})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){
        $('suggestBtn').disabled=false;
        if(!res.ok){ setStatus((res.j&&res.j.detail)||'Failed.',true); return; }
        var d=res.j, box=$('suggestBox');
        var fields=[['description','Description','desc'],['features','Features','feat'],['users','Target users','users'],['tech_stack','Tech stack','tech']];
        box.innerHTML='';
        fields.forEach(function(p){
          var items=d[p[0]]; if(!items || !items.length) return;
          var sec=document.createElement('div'); sec.className='sug-sec';
          var head=document.createElement('div'); head.className='sug-head';
          head.innerHTML='<span>'+p[1]+'</span>';
          var all=document.createElement('button'); all.type='button'; all.className='sug-all'; all.textContent='Use all';
          all.addEventListener('click', function(){
            $(p[2]).value = items.join('\n');
            setStatus(p[1]+' filled.');
          });
          head.appendChild(all);
          sec.appendChild(head);
          items.forEach(function(v){
            var row=document.createElement('button'); row.type='button'; row.className='sug-item';
            row.innerHTML='<span class="sug-txt"></span><span class="sug-add">Use</span>';
            row.querySelector('.sug-txt').textContent=v;
            row.addEventListener('click', function(){
              var el=$(p[2]), cur=el.value.trim();
              el.value = cur ? (cur+'\n'+v) : v;
              row.classList.add('used');
              setStatus(p[1]+' filled.');
            });
            sec.appendChild(row);
          });
          box.appendChild(sec);
        });
        box.hidden=false; setStatus('Click a suggestion to fill the field, or "Use all".');
      })
      .catch(function(){ $('suggestBtn').disabled=false; setStatus('Could not reach the service.',true); });
  });

  var cbMsgs = [];
  var cbSend = $('cbSend');
  function cbRender(){
    var log = $('cbLog'); if(!log) return;
    var h = '';
    cbMsgs.forEach(function(m){
      h += '<div class="' + (m.role==='user'?'chat-q':'chat-a') + '">' + esc(m.content) + '</div>';
    });
    log.innerHTML = h; log.scrollTop = log.scrollHeight;
  }
  if(cbSend) cbSend.addEventListener('click', function(){
    var t = $('cbInput').value.trim(); if(!t) return;
    cbMsgs.push({role:'user', content:t}); $('cbInput').value=''; cbRender();
    cbSend.disabled = true;
    cbMsgs.push({role:'assistant', content:'...'}); cbRender();
    fetch(API+'/api/chat-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:cbMsgs.slice(0,-1)})})
      .then(function(r){return r.json();}).then(function(j){
        cbSend.disabled = false;
        cbMsgs.pop();
        if(j.action === 'ready'){
          if(j.name) $('name').value = j.name;
          if(j.description) $('desc').value = j.description;
          if(j.features) $('feat').value = j.features;
          if(j.users) $('users').value = j.users;
          if(j.tech) $('tech').value = j.tech;
          cbMsgs.push({role:'assistant', content:'Got it - I filled the form. Review it, then continue.'});
          setStatus('Form filled from chat. Review, then Next.');
        } else {
          cbMsgs.push({role:'assistant', content:j.question || 'Tell me more.'});
        }
        cbRender();
      })
      .catch(function(){ cbSend.disabled=false; cbMsgs.pop(); cbMsgs.push({role:'assistant',content:'Could not reach the service.'}); cbRender(); });
  });
  if($('cbInput')) $('cbInput').addEventListener('keydown', function(e){ if(e.key==='Enter') $('cbSend').click(); });

  var importBtn = $('importBtn');
  if(importBtn) importBtn.addEventListener('click', function(){
    $('importBox').hidden = !$('importBox').hidden;
  });
  var importGo = $('importGo');
  if(importGo) importGo.addEventListener('click', function(){
    var txt = $('importText').value.trim();
    if(!txt){ setStatus('Paste some text first.', true); return; }
    importGo.disabled = true; setStatus('<span class="spin"></span>Reading your brief...');
    fetch(API+'/api/import-brief',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:txt})})
      .then(function(r){return r.json();}).then(function(j){
        importGo.disabled = false;
        if(j.name) $('name').value = j.name;
        if(j.description) $('desc').value = j.description;
        if(j.features) $('feat').value = j.features;
        if(j.users) $('users').value = j.users;
        if(j.tech) $('tech').value = j.tech;
        setStatus('Form filled from your brief.');
      }).catch(function(){ importGo.disabled=false; setStatus('Could not read brief.', true); });
  });

  function inlineMd(s){
    s=s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    s=s.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g,'$1<em>$2</em>');
    return s;
  }
  function mdToHtml(md){
    var lines=md.split('\n'), out='', list=null;
    var close=function(){ if(list){ out+='</'+list+'>'; list=null; } };
    for(var i=0;i<lines.length;i++){
      var l=lines[i], t=l.trim();
      var mOl=t.match(/^(\d+)[.)]\s+(.*)$/);
      if(/^###\s+/.test(l)){ close(); out+='<h3>'+inlineMd(l.replace(/^###\s+/,''))+'</h3>'; }
      else if(/^##\s+/.test(l)){ close(); out+='<h2>'+inlineMd(l.replace(/^##\s+/,''))+'</h2>'; }
      else if(/^#\s+/.test(l)){ close(); out+='<h2>'+inlineMd(l.replace(/^#\s+/,''))+'</h2>'; }
      else if(/^[-*]\s+/.test(l)){ if(list!=='ul'){ close(); out+='<ul>'; list='ul'; } out+='<li>'+inlineMd(l.replace(/^[-*]\s+/,''))+'</li>'; }
      else if(mOl){ if(list!=='ol'){ close(); out+='<ol>'; list='ol'; } out+='<li>'+inlineMd(mOl[2])+'</li>'; }
      else if(t===''){ close(); }
      else { close(); out+='<p>'+inlineMd(l)+'</p>'; }
    }
    close();
    return out;
  }

  var _diagSeq = 0;
  function diagram(kind, view){
    var payload={kind:kind, name:$('name').value.trim(), description:$('desc').value.trim(), features:$('feat').value};
    return fetch(API+'/api/diagram',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j || !j.code){ $(view).innerHTML='<div class="empty">Diagram unavailable.</div>'; return; }
        return renderMermaid(j.code, view);
      })
      .catch(function(){ $(view).innerHTML='<div class="empty">Diagram unavailable.</div>'; });
  }

  function renderMermaid(code, view){
    var el = $(view);
    if(!window.mermaid){ el.innerHTML='<div class="empty">Diagram renderer not loaded.</div>'; return; }
    var id = 'mmd' + (++_diagSeq);
    el.innerHTML = '<div class="mermaid"></div>';
    var node = el.querySelector('.mermaid');
    node.textContent = code;
    function showCode(){
      var esc = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      el.innerHTML = '<pre class="diag-code">' + esc + '</pre>';
    }
    try {
      return mermaid.render(id, code).then(function(out){
        el.innerHTML = out.svg;
      }).catch(function(){ showCode(); });
    } catch(e){
      showCode();
    }
  }

  $('genBtn').addEventListener('click', function(){
    var name=$('name').value.trim(), desc=$('desc').value.trim();
    if(!name||!desc){ setStatus('App name and description are required.',true); return; }
    $('genBtn').disabled=true;
    $('outPanel').hidden=false;
    setStatus('<span class="spin"></span>Writing your PRD and diagrams (this takes ~40-70s)...');
    // reset diagram views so a failed retry does not show stale content
    $('viewArch').innerHTML='<div class="empty">Generating...</div>';
    $('viewErd').innerHTML='<div class="empty">Generating...</div>';
    var prdP = fetch(API+'/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,description:desc,features:$('feat').value,users:$('users').value,tech:$('tech').value,template:template,lang:lang})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});});
    var diagP = Promise.all([diagram('arch','viewArch'), diagram('erd','viewErd')]);
    Promise.all([prdP, diagP]).then(function(results){
      var res = results[0];
      $('genBtn').disabled=false;
      if(!res.ok){ setStatus((res.j&&res.j.detail)||'Generation failed.',true); return; }
      prdMd = res.j.markdown || '';
      $('viewPrd').innerHTML = mdToHtml(prdMd);
      // re-check the session so a stale/early state never locks a signed-in user
      fetch(API+'/api/me').then(function(r){return r.json();}).then(function(j){ me = j; renderAccount(); }).catch(function(){}).then(function(){
        $('outLock').hidden = me.logged_in;
        setStatus(me.logged_in ? 'PRD and diagrams ready.' : 'PRD ready. Sign in to unlock and save it.');
      });
      document.querySelector('.out-head').scrollIntoView({behavior:'smooth', block:'start'});
    }).catch(function(){ $('genBtn').disabled=false; setStatus('Could not reach the service.',true); });
  });

  var genMultiBtn = $('genMultiBtn');
  if(genMultiBtn) genMultiBtn.addEventListener('click', function(){
    var name=$('name').value.trim(), desc=$('desc').value.trim();
    if(!name||!desc){ setStatus('App name and description are required.',true); return; }
    genMultiBtn.disabled=true; $('outPanel').hidden=false;
    setStatus('<span class="spin"></span>Writing the full pack: PRD + Tech Spec + User Stories (~90-150s)...');
    fetch(API+'/api/generate-multi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,description:desc,features:$('feat').value,users:$('users').value,tech:$('tech').value,template:template,lang:lang})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){
        genMultiBtn.disabled=false;
        if(!res.ok){ setStatus((res.j&&res.j.detail)||'Generation failed.',true); return; }
        prdMd = res.j.prd || '';
        $('viewPrd').innerHTML = mdToHtml(prdMd);
        if(res.j.tech_spec) reviewBlock('Tech Spec', mdToHtml(res.j.tech_spec));
        if(res.j.user_stories) reviewBlock('User Stories', mdToHtml(res.j.user_stories));
        fetch(API+'/api/me').then(function(r){return r.json();}).then(function(j){ me=j; renderAccount(); }).catch(function(){}).then(function(){
          $('outLock').hidden = me.logged_in;
          setStatus('Full pack ready: PRD + Tech Spec + User Stories.');
        });
        document.querySelector('.out-head').scrollIntoView({behavior:'smooth', block:'start'});
      })
      .catch(function(){ genMultiBtn.disabled=false; setStatus('Could not reach the service.',true); });
  });

  // ---- account + saved projects ----
  var me = { logged_in: false };
  function renderAccount(){
    var box = $('account');
    if(!box) return;
    if(me.logged_in){
      box.innerHTML = '<span style="font-size:.86rem;color:#6b6a65;margin-right:10px">' +
        (me.avatar ? '<img src="'+me.avatar+'" width="22" height="22" style="border-radius:50%;vertical-align:-6px;margin-right:6px">' : '') +
        '@'+me.login + '</span>' +
        '<button class="btn ghost sm" id="logoutBtn" type="button">Sign out</button>';
      $('logoutBtn').addEventListener('click', function(){
        fetch(API+'/auth/logout',{method:'POST'}).then(function(){ location.reload(); });
      });
    } else {
      box.innerHTML = '<a class="btn primary sm" href="/login">Sign in</a>';
    }
  }
  fetch(API+'/api/me').then(function(r){return r.json();}).then(function(j){ me=j; renderAccount(); }).catch(function(){});

  $('saveBtn').addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    if(!me.logged_in){ setStatus('Sign in with GitHub to save projects.', true); return; }
    fetch(API+'/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      name: $('name').value.trim()||'Untitled', template: template, markdown: prdMd, lang: lang,
      payload: {description:$('desc').value, features:$('feat').value, users:$('users').value, tech:$('tech').value}
    })}).then(function(r){return r.json();}).then(function(j){
      if(j.id){ lastProjectId = j.id; setStatus('Saved to your projects.'); } else { setStatus((j.detail)||'Save failed.', true); }
    }).catch(function(){ setStatus('Save failed.', true); });
  });

  var versionBtn = $('versionBtn');
  if(versionBtn) versionBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    if(!me.logged_in){ setStatus('Sign in to save versions.', true); return; }
    if(!lastProjectId){ setStatus('Click Save first, then Save version.', true); return; }
    versionBtn.disabled = true;
    fetch(API+'/api/projects/'+lastProjectId+'/versions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, note:'manual snapshot'})})
      .then(function(r){return r.json();}).then(function(){
        versionBtn.disabled = false; setStatus('Version saved.');
      }).catch(function(){ versionBtn.disabled = false; setStatus('Could not save version.', true); });
  });

  var histBtn = $('histBtn');
  if(histBtn) histBtn.addEventListener('click', function(){
    var panel = $('histPanel');
    if(!lastProjectId){ setStatus('Save the PRD first to track versions.', true); return; }
    fetch(API+'/api/projects/'+lastProjectId+'/versions').then(function(r){return r.json();}).then(function(list){
      var h = '';
      if(!list || !list.length){ h = '<p style="color:#8a8880;font-size:.86rem">No versions yet.</p>'; }
      list.forEach(function(v){
        h += '<div class="hist-item"><div><div class="hi-note">' + (v.note||'snapshot') + '</div>' +
             '<div class="hi-meta">' + (v.created_at||'') + ' &middot; ' + (v.chars||0) + ' chars</div></div>' +
             '<button class="btn ghost sm" data-v="' + v.id + '">Restore</button></div>';
      });
      $('histList').innerHTML = h;
      $('histList').querySelectorAll('[data-v]').forEach(function(b){
        b.addEventListener('click', function(){
          fetch(API+'/api/versions/'+b.dataset.v).then(function(r){return r.json();}).then(function(v){
            if(v && v.markdown){ prdMd = v.markdown; $('viewPrd').innerHTML = mdToHtml(prdMd); setStatus('Version restored.'); }
          });
        });
      });
      panel.hidden = false;
    }).catch(function(){ setStatus('Could not load history.', true); });
  });
  var histClose = $('histClose');
  if(histClose) histClose.addEventListener('click', function(){ $('histPanel').hidden = true; });

  var shareBtn = $('shareBtn');
  if(shareBtn) shareBtn.addEventListener('click', function(){
    if(!me.logged_in){ setStatus('Sign in with GitHub to share a link.', true); return; }
    if(!lastProjectId){ setStatus('Save the PRD first, then share.', true); return; }
    shareBtn.disabled = true;
    fetch(API+'/api/projects/'+lastProjectId+'/share',{method:'POST'}).then(function(r){return r.json();}).then(function(j){
      shareBtn.disabled = false;
      if(j && j.shared){
        var url = location.origin + j.url;
        navigator.clipboard.writeText(url).catch(function(){});
        setStatus('Public link copied: <a href="'+j.url+'" target="_blank">'+url+'</a>');
      } else {
        setStatus('Sharing turned off.');
      }
    }).catch(function(){ shareBtn.disabled = false; setStatus('Share failed.', true); });
  });

  var reviseBtn = $('reviseBtn');
  if(reviseBtn) reviseBtn.addEventListener('click', function(){
    var instr = $('reviseInput').value.trim();
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    if(!instr){ setStatus('Type what you want changed.', true); return; }
    reviseBtn.disabled = true;
    setStatus('<span class="spin"></span>Revising your PRD...');
    fetch(API+'/api/revise',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, instruction:instr, name:$('name').value.trim()})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){
        reviseBtn.disabled = false;
        if(!res.ok){ setStatus((res.j&&res.j.detail)||'Revise failed.', true); return; }
        prdMd = res.j.markdown || prdMd;
        $('viewPrd').innerHTML = mdToHtml(prdMd);
        $('reviseInput').value = '';
        setStatus('PRD revised.');
      })
      .catch(function(){ reviseBtn.disabled = false; setStatus('Could not reach the service.', true); });
  });

  $('copyBtn').addEventListener('click', function(){
    if(!prdMd){ setStatus('Nothing to copy yet.',true); return; }
    navigator.clipboard.writeText(prdMd).then(function(){ setStatus('Copied to clipboard.'); });
  });
  $('dlBtn').addEventListener('click', function(){
    if(!prdMd){ setStatus('Nothing to download yet.',true); return; }
    var blob=new Blob([prdMd],{type:'text/markdown'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='PRD_'+(($('name').value.trim()||'product').replace(/\s+/g,'_'))+'.md';
    a.click();
  });

  var docxBtn = $('docxBtn');
  if(docxBtn) docxBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    docxBtn.disabled = true; setStatus('<span class="spin"></span>Building .docx...');
    fetch(API+'/api/export/docx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, name:$('name').value.trim()||'PRD'})})
      .then(function(r){ if(!r.ok) throw 0; return r.blob(); })
      .then(function(blob){
        docxBtn.disabled = false;
        var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
        a.download='PRD_'+(($('name').value.trim()||'product').replace(/\s+/g,'_'))+'.docx';
        a.click(); setStatus('Downloaded .docx');
      })
      .catch(function(){ docxBtn.disabled=false; setStatus('Could not build .docx.', true); });
  });

  var ticketsBtn = $('ticketsBtn');
  if(ticketsBtn) ticketsBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    ticketsBtn.disabled = true; setStatus('<span class="spin"></span>Breaking into tickets...');
    fetch(API+'/api/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, name:$('name').value.trim(), lang:lang})})
      .then(function(r){return r.json();}).then(function(j){
        ticketsBtn.disabled = false;
        var t = j.tickets || [];
        if(!t.length){ setStatus('No tickets produced.', true); return; }
        var h = '<div class="panel" style="margin-top:16px"><h2 style="margin-bottom:14px">Implementation tickets</h2>';
        t.forEach(function(x){
          h += '<div class="hist-item"><div><div class="hi-note">' + esc(x.title||'') + '</div>' +
               '<div class="hi-meta">' + esc(x.type||'') + ' &middot; ' + esc(x.priority||'') + ' &middot; ' + esc(x.estimate||'') + '</div></div></div>';
        });
        h += '</div>';
        var box = document.createElement('div'); box.innerHTML = h;
        $('viewPrd').appendChild(box);
        setStatus(t.length + ' tickets generated (scroll down).');
      }).catch(function(){ ticketsBtn.disabled=false; setStatus('Could not generate tickets.', true); });
  });

  function reviewBlock(title, html){
    var box = document.createElement('div');
    box.className = 'panel'; box.style.marginTop = '16px';
    box.innerHTML = '<h2 style="margin-bottom:14px">' + title + '</h2>' + html;
    $('viewPrd').appendChild(box);
  }

  var critiqueBtn = $('critiqueBtn');
  if(critiqueBtn) critiqueBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    critiqueBtn.disabled = true; setStatus('<span class="spin"></span>Reviewing...');
    fetch(API+'/api/critique',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, question:'review'})})
      .then(function(r){return r.json();}).then(function(j){
        critiqueBtn.disabled = false;
        var h = '<div style="font-family:Poppins;font-weight:600;font-size:1.4rem">' + (j.score||0) + '/100</div>';
        h += '<p style="color:#6b6a65;margin:6px 0 14px">' + esc(j.verdict||'') + '</p>';
        (j.strengths||[]).forEach(function(s){ h += '<p style="color:var(--green)">+ ' + esc(s) + '</p>'; });
        (j.gaps||[]).forEach(function(s){ h += '<p style="color:#b91c1c">- ' + esc(s) + '</p>'; });
        reviewBlock('Review', h); setStatus('Review ready (scroll down).');
      }).catch(function(){ critiqueBtn.disabled=false; setStatus('Review failed.', true); });
  });

  var estimateBtn = $('estimateBtn');
  if(estimateBtn) estimateBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    estimateBtn.disabled = true; setStatus('<span class="spin"></span>Estimating...');
    fetch(API+'/api/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, question:'estimate'})})
      .then(function(r){return r.json();}).then(function(j){
        estimateBtn.disabled = false;
        var h = '<div style="font-family:Poppins;font-weight:600;font-size:1.4rem">' + (j.weeks||'?') + ' weeks</div>';
        if(j.cost_usd) h += '<p style="color:#6b6a65;margin:6px 0">Est. cost: $' + (j.cost_usd.low||0) + ' - $' + (j.cost_usd.high||0) + '</p>';
        (j.team||[]).forEach(function(t){ h += '<p>• ' + esc(t.role) + ' x' + (t.count||1) + '</p>'; });
        (j.phases||[]).forEach(function(p){ h += '<p style="color:#6b6a65">• ' + esc(p.name) + ' (' + (p.weeks||'?') + 'w)</p>'; });
        reviewBlock('Estimate', h); setStatus('Estimate ready (scroll down).');
      }).catch(function(){ estimateBtn.disabled=false; setStatus('Estimate failed.', true); });
  });

  var chatBtn = $('chatBtn');
  if(chatBtn) chatBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    var q = $('chatInput').value.trim();
    if(!q) return;
    var log = $('chatlog'); log.hidden = false;
    log.innerHTML += '<div class="chat-q">' + esc(q) + '</div>';
    $('chatInput').value = '';
    chatBtn.disabled = true;
    var a = document.createElement('div'); a.className = 'chat-a'; a.textContent = '...'; log.appendChild(a);
    fetch(API+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, question:q})})
      .then(function(r){return r.json();}).then(function(j){
        chatBtn.disabled = false; a.textContent = j.answer || 'No answer.';
      }).catch(function(){ chatBtn.disabled=false; a.textContent = 'Could not answer.'; });
  });
  if($('chatInput')) $('chatInput').addEventListener('keydown', function(e){ if(e.key==='Enter') $('chatBtn').click(); });

  var pdfBtn = $('pdfBtn');
  if(pdfBtn) pdfBtn.addEventListener('click', function(){
    if(!prdMd){ setStatus('Generate a PRD first.', true); return; }
    pdfBtn.disabled = true; setStatus('<span class="spin"></span>Building .pdf...');
    fetch(API+'/api/export/pdf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:prdMd, name:$('name').value.trim()||'PRD'})})
      .then(function(r){ if(!r.ok) throw 0; return r.blob(); })
      .then(function(blob){
        pdfBtn.disabled = false;
        var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
        a.download='PRD_'+(($('name').value.trim()||'product').replace(/\s+/g,'_'))+'.pdf';
        a.click(); setStatus('Downloaded .pdf');
      })
      .catch(function(){ pdfBtn.disabled=false; setStatus('Could not build .pdf.', true); });
  });
})();
