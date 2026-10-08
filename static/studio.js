(function(){
  var API = '';
  var template = 'Mobile App';
  var prdMd = '';
  var $ = function(id){ return document.getElementById(id); };

  document.querySelectorAll('.tpl').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('.tpl').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on'); template = b.dataset.t;
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

  function setStatus(msg, err){ var s=$('status'); s.className='status'+(err?' err':''); s.innerHTML=msg; }

  $('suggestBtn').addEventListener('click', function(){
    var title = $('name').value.trim();
    if(!title){ setStatus('Enter an app name first.', true); return; }
    $('suggestBtn').disabled = true; setStatus('<span class="spin"></span>Thinking of suggestions...');
    fetch(API+'/api/suggest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title,template:template})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){
        $('suggestBtn').disabled=false;
        if(!res.ok){ setStatus((res.j&&res.j.detail)||'Failed.',true); return; }
        var d=res.j, box=$('suggestBox'), html='';
        [['description','Description'],['features','Features'],['users','Target users'],['tech_stack','Tech stack']].forEach(function(p){
          if(d[p[0]] && d[p[0]].length){ html+='<h4>'+p[1]+'</h4>'; d[p[0]].forEach(function(v){ html+='<span class="chip">'+v.replace(/</g,'&lt;')+'</span>'; }); }
        });
        box.innerHTML=html; box.hidden=false; setStatus('Suggestions ready. Copy what you like into the fields.');
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

  $('genBtn').addEventListener('click', function(){
    var name=$('name').value.trim(), desc=$('desc').value.trim();
    if(!name||!desc){ setStatus('App name and description are required.',true); return; }
    $('genBtn').disabled=true; setStatus('<span class="spin"></span>Writing your PRD (this takes ~30-60s)...');
    fetch(API+'/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,description:desc,features:$('feat').value,users:$('users').value,tech:$('tech').value,template:template})})
      .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j};});})
      .then(function(res){
        $('genBtn').disabled=false;
        if(!res.ok){ setStatus((res.j&&res.j.detail)||'Failed.',true); return; }
        prdMd=res.j.markdown||''; $('viewPrd').innerHTML=mdToHtml(prdMd);
        setStatus('PRD ready.');
        document.querySelector('.out-head').scrollIntoView({behavior:'smooth', block:'start'});
      })
      .catch(function(){ $('genBtn').disabled=false; setStatus('Could not reach the service.',true); });
  });

  $('diagBtn').addEventListener('click', function(){
    var name=$('name').value.trim(), desc=$('desc').value.trim();
    if(!name||!desc){ setStatus('App name and description are required.',true); return; }
    $('diagBtn').disabled=true; setStatus('<span class="spin"></span>Generating diagrams...');
    var payload={name:name,description:desc,features:$('feat').value};
    function one(kind, view){ return fetch(API+'/api/diagram',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({kind:kind},payload))})
      .then(function(r){return r.json();}).then(function(j){ if(j.svg_url){ $(view).innerHTML='<img src="'+j.svg_url+'" alt="'+kind+' diagram" />'; } else { $(view).innerHTML='<div class="empty">Diagram unavailable.</div>'; } }).catch(function(){ $(view).innerHTML='<div class="empty">Diagram unavailable.</div>'; }); }
    Promise.all([one('arch','viewArch'), one('erd','viewErd')]).then(function(){
      $('diagBtn').disabled=false; setStatus('Diagrams ready. See the Architecture and ERD tabs.');
    });
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
      name: $('name').value.trim()||'Untitled', template: template, markdown: prdMd,
      payload: {description:$('desc').value, features:$('feat').value, users:$('users').value, tech:$('tech').value}
    })}).then(function(r){return r.json();}).then(function(j){
      if(j.id){ setStatus('Saved to your projects.'); } else { setStatus((j.detail)||'Save failed.', true); }
    }).catch(function(){ setStatus('Save failed.', true); });
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
