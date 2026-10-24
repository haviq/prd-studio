(function(){
  var $ = function(id){ return document.getElementById(id); };

  function badge(plan){
    if(plan === 'pro') return '<span class="plan-badge pro">Pro</span>';
    return '<span class="plan-badge free">Free</span>';
  }

  function esc(s){ return (s==null?'':String(s)).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  fetch('/api/me').then(function(r){return r.json();}).then(function(me){
    $('loading').hidden = true;
    if(!me.logged_in){ $('anon').hidden = false; return; }
    $('content').hidden = false;
    $('name').textContent = me.name || me.login;
    $('handle').textContent = '@' + me.login;
    $('email').textContent = me.email || '';
    if($('setLogin')) $('setLogin').textContent = '@' + me.login;
    if(me.avatar) $('avatar').src = me.avatar; else $('avatar').style.display = 'none';
    var plan = me.plan || 'free';
    $('planBadge').outerHTML = badge(plan);

    var planBox = $('planBox');
    if(plan === 'pro'){
      planBox.innerHTML = '<p style="color:#4a4945">You are on <strong>Pro</strong>. Unlimited PRD generation and saved projects.</p>';
    } else {
      planBox.innerHTML =
        '<p style="color:#4a4945;margin-bottom:14px">You are on the <strong>Free</strong> plan: 10 PRDs per day, unlimited saved projects.</p>' +
        '<a class="btn accent" href="/checkout">Upgrade to Pro</a>';
    }

    // usage
    fetch('/api/usage').then(function(r){return r.json();}).then(function(u){
      if(u && u.totals){
        var gen = u.totals.generate || 0, rev = u.totals.revise || 0;
        $('usageGrid').innerHTML =
          '<div class="stat"><div class="n">' + gen + '</div><div class="l">PRDs generated</div></div>' +
          '<div class="stat"><div class="n">' + rev + '</div><div class="l">Revisions</div></div>' +
          '<div class="stat"><div class="n">' + (u.projects||0) + '</div><div class="l">Saved projects</div></div>' +
          '<div class="stat"><div class="n">' + (u.today||0) + '</div><div class="l">Today</div></div>';
        var rec = u.recent || [];
        if(!rec.length){ $('usageRecent').innerHTML = '<p style="color:#8a8880">No activity yet.</p>'; }
        else {
          var h = '';
          rec.forEach(function(e){
            h += '<div class="proj-row"><div><div class="proj-name">' + esc(e.kind) +
                 (e.name ? ' &middot; ' + esc(e.name) : '') + '</div>' +
                 '<div class="proj-meta">' + esc(e.created_at) + '</div></div></div>';
          });
          $('usageRecent').innerHTML = h;
        }
      }
    }).catch(function(){});

    return fetch('/api/projects').then(function(r){return r.json();}).then(function(list){
      var box = $('projects');
      if(!list || !list.length){ box.innerHTML = '<p style="color:#8a8880">No saved projects yet. Generate a PRD in the studio and click Save.</p>'; return; }
      var html = '';
      list.forEach(function(p){
        html += '<div class="proj-row">' +
          '<div><div class="proj-name">' + esc(p.name||'Untitled') + '</div>' +
          '<div class="proj-meta">' + esc(p.template||'') + ' &middot; ' + esc(p.created_at||'') + '</div></div>' +
          '<div class="proj-actions">' +
          '<button class="btn ghost sm" data-share="' + p.id + '">Share</button>' +
          '<button class="btn ghost sm" data-open="' + p.id + '">Open</button>' +
          '<button class="btn ghost sm" data-del="' + p.id + '">Delete</button></div></div>';
      });
      box.innerHTML = html;
      var ps = $('projSearch');
      if(ps) ps.addEventListener('input', function(){
        var q = ps.value.trim().toLowerCase();
        box.querySelectorAll('.proj-row').forEach(function(row){
          row.hidden = !!q && row.textContent.toLowerCase().indexOf(q) < 0;
        });
      });
      box.querySelectorAll('[data-open]').forEach(function(b){
        b.addEventListener('click', function(){ location.href = '/studio?project=' + b.dataset.open; });
      });
      box.querySelectorAll('[data-share]').forEach(function(b){
        b.addEventListener('click', function(){
          fetch('/api/projects/' + b.dataset.share + '/share', {method:'POST'})
            .then(function(r){return r.json();}).then(function(j){
              if(j && j.shared){
                var url = location.origin + j.url;
                navigator.clipboard.writeText(url).catch(function(){});
                b.textContent = 'Link copied';
                setTimeout(function(){ b.textContent = 'Share'; }, 2000);
              } else {
                b.textContent = 'Share';
              }
            }).catch(function(){});
        });
      });
      box.querySelectorAll('[data-del]').forEach(function(b){
        b.addEventListener('click', function(){
          if(!confirm('Delete this project?')) return;
          fetch('/api/projects/' + b.dataset.del, {method:'DELETE'}).then(function(){ b.closest('.proj-row').remove(); });
        });
      });
    });
  }).catch(function(){ $('loading').hidden = true; $('anon').hidden = false; });

  // ---- AI provider settings ----
  function aiStatus(msg, err){ var s=$('aiStatus'); if(!s) return; s.className='status'+(err?' err':''); s.textContent=msg||''; }
  if($('aiProvider')){
    fetch('/api/ai-settings').then(function(r){return r.json();}).then(function(c){
      if(c && !c.detail){
        $('aiProvider').value = c.provider || '';
        $('aiBaseUrl').value = c.base_url || '';
        $('aiModel').value = c.model || '';
        if(c.has_key) $('aiKey').placeholder = 'saved: ' + (c.key_hint || 'set') + ' (blank = keep)';
      }
    }).catch(function(){});
    $('aiSave').addEventListener('click', function(){
      aiStatus('Saving...');
      fetch('/api/ai-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        provider:$('aiProvider').value, base_url:$('aiBaseUrl').value.trim(), model:$('aiModel').value.trim(), api_key:$('aiKey').value.trim()
      })}).then(function(r){return r.json();}).then(function(j){
        if(j && j.ok){ aiStatus('Saved. New generations will use this model.'); $('aiKey').value=''; $('aiKey').placeholder='leave blank to keep current'; }
        else { aiStatus((j&&j.detail)||'Save failed.', true); }
      }).catch(function(){ aiStatus('Save failed.', true); });
    });
    $('aiClear').addEventListener('click', function(){
      fetch('/api/ai-settings/clear',{method:'POST'}).then(function(){ location.reload(); });
    });
  }

  // ---- teams ----
  function teamMsg(m, err){ var s=$('teamMsg'); if(!s) return; s.className='adm-form-msg'; s.style.color = err?'#b91c1c':'var(--green)'; s.textContent=m||''; }
  function loadTeams(){
    if(!$('teams')) return;
    fetch('/api/teams').then(function(r){return r.json();}).then(function(d){
      var owned = (d && d.owned) || [];
      var box = $('teams');
      if(!owned.length){ box.innerHTML = '<p style="color:#8a8880;font-size:.9rem">No teams yet. Create one above.</p>'; return; }
      var h = '';
      owned.forEach(function(t){
        h += '<div class="proj-row"><div><div class="proj-name">' + esc(t.name) + '</div>' +
             '<div class="proj-meta">created ' + esc(t.created_at||'') + '</div></div>' +
             '<div class="proj-actions"><input placeholder="invite email" data-inv="' + t.id + '" style="width:150px;margin-bottom:0" />' +
             '<button class="btn ghost sm" data-do="' + t.id + '">Invite</button></div></div>';
      });
      box.innerHTML = h;
      box.querySelectorAll('[data-do]').forEach(function(b){
        b.addEventListener('click', function(){
          var inp = box.querySelector('[data-inv="'+b.dataset.do+'"]');
          var email = (inp.value||'').trim();
          if(!email){ return; }
          fetch('/api/teams/'+b.dataset.do+'/invite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email, role:'editor'})})
            .then(function(r){return r.json();}).then(function(j){ teamMsg(j.matched?'Invited @'+email:'Invite saved (user will join on signup).'); loadTeams(); });
        });
      });
    }).catch(function(){});
  }
  if($('teamCreate')) $('teamCreate').addEventListener('click', function(){
    var n = $('teamName').value.trim(); if(!n){ return; }
    fetch('/api/teams',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})})
      .then(function(r){return r.json();}).then(function(j){ if(j.id){ teamMsg('Team created.'); $('teamName').value=''; loadTeams(); } });
  });
  loadTeams();

  // ---- api keys ----
  function keyMsg(m, err){ var s=$('keyMsg'); if(!s) return; s.style.color = err?'#b91c1c':'var(--green)'; s.textContent=m||''; }
  function loadKeys(){
    if(!$('keyList')) return;
    fetch('/api/keys').then(function(r){return r.json();}).then(function(list){
      var box = $('keyList');
      if(!list || !list.length || list.detail){ box.innerHTML = '<p style="color:#8a8880;font-size:.9rem">No API keys yet. Create one to call the API programmatically.</p>'; return; }
      var h = '';
      list.forEach(function(k){
        var col = k.revoked ? '#8a8880' : 'var(--green)';
        h += '<div class="proj-row"><div>' +
          '<div class="proj-name"><code style="font-size:.85rem">' + esc(k.prefix) + '&hellip;</code> ' + esc(k.name||'') +
          (k.revoked ? ' <span class="plan-badge free" style="text-transform:none">revoked</span>' : ' <span style="color:'+col+';font-size:.8rem;font-weight:600">active</span>') + '</div>' +
          '<div class="proj-meta">created ' + esc(k.created_at||'') + (k.last_used_at ? ' &middot; last used ' + esc(k.last_used_at) : ' &middot; never used') + '</div></div>' +
          (k.revoked ? '' : '<div class="proj-actions"><button class="btn ghost sm" data-revoke="' + k.id + '" style="color:#b91c1c;border-color:rgba(185,28,28,.3)">Revoke</button></div>') +
          '</div>';
      });
      box.innerHTML = h;
      box.querySelectorAll('[data-revoke]').forEach(function(b){
        b.addEventListener('click', function(){
          if(!confirm('Revoke this key? Anything using it will immediately lose access.')) return;
          fetch('/api/keys/' + b.dataset.revoke + '/revoke', {method:'POST'}).then(function(){ keyMsg('Key revoked.'); loadKeys(); });
        });
      });
    }).catch(function(){});
  }
  if($('keyCreate')) $('keyCreate').addEventListener('click', function(){
    var name = ($('keyName').value || '').trim() || 'default';
    fetch('/api/keys', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name})})
      .then(function(r){ return r.json(); }).then(function(j){
        if(j && j.api_key){
          showNewKey(j.api_key);
          keyMsg('Key created. Copy it now — it will not be shown again.');
          $('keyName').value = '';
          loadKeys();
        } else {
          keyMsg((j && j.detail) || 'Create failed.', true);
        }
      }).catch(function(){ keyMsg('Create failed.', true); });
  });
  function showNewKey(key){
    var box = $('keyList');
    if(!box) return;
    var d = document.createElement('div');
    d.className = 'panel';
    d.style.cssText = 'margin:0 0 16px;background:#fffbe6;border:1px solid #f0d96c';
    d.innerHTML = '<div style="font-weight:600;margin-bottom:8px">Your new API key (shown once)</div>' +
      '<code id="newKeyVal" style="display:block;background:#0d1117;color:#e6edf3;padding:10px 12px;border-radius:6px;overflow-x:auto;font-size:.85rem">' + esc(key) + '</code>' +
      '<button class="btn accent sm" id="copyNewKey" type="button" style="margin-top:10px">Copy key</button>';
    box.parentNode.insertBefore(d, box);
    d.querySelector('#copyNewKey').addEventListener('click', function(){
      navigator.clipboard.writeText(key).then(function(){
        this.textContent = 'Copied!';
        var b = this; setTimeout(function(){ b.textContent = 'Copy key'; }, 2000);
      }.bind(this)).catch(function(){});
    });
  }

  // ---- data export ----
  if($('exportBtn')) $('exportBtn').addEventListener('click', function(){
    var b = $('exportBtn'); b.disabled = true; b.textContent = 'Preparing...';
    fetch('/api/me/export').then(function(r){ return r.json(); }).then(function(data){
      var blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'prd-studio-export.json';
      document.body.appendChild(a); a.click(); a.remove();
      b.disabled = false; b.textContent = 'Download my data (JSON)';
    }).catch(function(){ b.disabled = false; b.textContent = 'Download my data (JSON)'; });
  });

  loadKeys();

  var lo = $('logoutBtn');
  if(lo) lo.addEventListener('click', function(){ fetch('/auth/logout',{method:'POST'}).then(function(){ location.href='/'; }); });
})();