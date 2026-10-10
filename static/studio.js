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
      box.innerHTML = '<a class="btn primary sm" href="/auth/github">Sign in with GitHub</a>';
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
})();
