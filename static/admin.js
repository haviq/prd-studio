(function(){
  var $ = function(id){ return document.getElementById(id); };
  function esc(s){ return (s==null?'':String(s)).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function money(n){ return 'Rp ' + (n||0).toLocaleString('id-ID'); }
  function kpi(label, value, sub){
    return '<div class="kpi"><div class="kpi-l">'+label+'</div><div class="kpi-v">'+value+'</div>'+
           (sub?'<div class="kpi-s">'+sub+'</div>':'')+'</div>';
  }
  function toast(msg, err){
    var t = document.getElementById('admToast');
    if(!t){ t = document.createElement('div'); t.id='admToast'; t.className='adm-toast'; document.body.appendChild(t); }
    t.textContent = msg;
    t.className = 'adm-toast show' + (err?' err':'');
    clearTimeout(t._t); t._t = setTimeout(function(){ t.className = 'adm-toast'; }, 2200);
  }

  // ---- access ----
  function showApp(){
    $('loading').hidden = true; $('denied').hidden = true; $('app').hidden = false;
    loadStats(); loadSeries(); loadRecent(); loadUsers(); loadOrders();
  }
  function showDenied(){ $('loading').hidden = true; $('app').hidden = true; $('denied').hidden = false; }
  function check(){ fetch('/api/admin/whoami').then(function(r){return r.json();}).then(function(w){
    if(w && w.admin){ showApp(); } else { showDenied(); }
  }).catch(showDenied); }
  check();

  var codeBtn = $('codeBtn');
  if(codeBtn) codeBtn.addEventListener('click', function(){
    var code = $('code').value.trim(); if(!code) return;
    codeBtn.disabled = true; var st=$('codeStatus'); st.className='status'; st.textContent='Checking...';
    fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code})})
      .then(function(r){ return r.json().then(function(j){ return {ok:r.ok,j:j}; }); })
      .then(function(res){ codeBtn.disabled=false; if(res.ok){ check(); } else { st.className='status err'; st.textContent=(res.j&&res.j.detail)||'Invalid code.'; } })
      .catch(function(){ codeBtn.disabled=false; st.className='status err'; st.textContent='Failed.'; });
  });
  var ci=$('code'); if(ci) ci.addEventListener('keydown', function(e){ if(e.key==='Enter') $('codeBtn').click(); });
  var lo=$('logoutBtn'); if(lo) lo.addEventListener('click', function(){
    fetch('/api/admin/logout',{method:'POST'}).then(function(){ location.reload(); });
  });

  // ---- nav ----
  document.querySelectorAll('.adm-link[data-v]').forEach(function(a){
    a.addEventListener('click', function(){
      document.querySelectorAll('.adm-link[data-v]').forEach(function(x){ x.classList.remove('on'); });
      a.classList.add('on');
      var v = a.dataset.v;
      document.querySelectorAll('.adm-view').forEach(function(s){ s.classList.toggle('on', s.dataset.view===v); });
      var t = $('viewTitle'); if(t) t.textContent = a.textContent.trim();
    });
  });

  var stats = {};
  function loadStats(){
    fetch('/api/admin/stats').then(function(r){return r.json();}).then(function(s){
      stats = s || {};
      $('kpis').innerHTML =
        kpi('Total users', s.users||0, (s.pro||0)+' pro') +
        kpi('PRDs generated', s.generates||0, (s.revises||0)+' revisions') +
        kpi('Projects', s.projects||0, (s.shared||0)+' shared') +
        kpi('Revenue', money(s.revenue), (s.paid_orders||0)+' paid orders');
      $('revKpis').innerHTML =
        kpi('Total revenue', money(s.revenue), (s.paid_orders||0)+' paid') +
        kpi('Pending orders', s.pending_orders||0, 'awaiting payment') +
        kpi('Pro users', s.pro||0, 'active subscribers') +
        kpi('Conversion', (s.users? Math.round((s.pro||0)/s.users*100):0)+'%', 'free to pro');
    }).catch(function(){});
  }

  function bars(container, series, key, color){
    var max = Math.max.apply(null, series.map(function(d){ return d[key]||0; }).concat([1]));
    var h = '';
    series.forEach(function(d){
      var pct = Math.round((d[key]||0)/max*100);
      h += '<div class="bar" title="'+d.date+': '+(d[key]||0)+'"><div class="bar-f" style="height:'+Math.max(2,pct)+'%;background:'+color+'"></div></div>';
    });
    container.innerHTML = '<div class="bars">'+h+'</div>';
  }

  function loadSeries(){
    fetch('/api/admin/timeseries?days=14').then(function(r){return r.json();}).then(function(d){
      var s = d.series || [];
      var c = $('chart');
      if(c){
        var max = Math.max.apply(null, s.map(function(x){return Math.max(x.generates||0, x.signups||0);}).concat([1]));
        var h='';
        s.forEach(function(x){
          var g = Math.round((x.generates||0)/max*100), sg = Math.round((x.signups||0)/max*100);
          h += '<div class="bargroup" title="'+x.date+' | PRDs '+x.generates+' | signups '+x.signups+'">'+
               '<div class="bg gen" style="height:'+Math.max(2,g)+'%"></div>'+
               '<div class="bg sig" style="height:'+Math.max(2,sg)+'%"></div></div>';
        });
        c.innerHTML = '<div class="bars">'+h+'</div>';
      }
      bars($('revChart'), s, 'revenue', 'var(--green)');
    }).catch(function(){});
  }

  function loadRecent(){
    fetch('/api/admin/recent').then(function(r){return r.json();}).then(function(d){
      var f = $('feed'); if(!f) return;
      var h = '';
      (d.activity||[]).forEach(function(a){
        h += '<div class="feed-item"><span class="feed-dot"></span><div><div class="feed-t">'+esc(a.kind)+' &middot; '+esc(a.name||'-')+'</div>'+
             '<div class="feed-m">@'+esc(a.login||'-')+' &middot; '+esc(a.created_at||'')+'</div></div></div>';
      });
      f.innerHTML = h || '<p style="color:#8a8880">No activity yet.</p>';
    }).catch(function(){});
  }

  var allUsers = [];
  function renderUsers(list){
    var box = $('userList'); if(!box) return;
    if(!list.length){ box.innerHTML='<p style="color:#8a8880">No users.</p>'; return; }
    var h='';
    list.forEach(function(u){
      h += '<div class="proj-row"><div>'+
        '<div class="proj-name">'+esc(u.name||u.login||('user '+u.id))+' <span class="plan-badge '+(u.plan==='pro'?'pro':'free')+'">'+(u.plan||'free')+'</span></div>'+
        '<div class="proj-meta">@'+esc(u.login||'')+' &middot; '+esc(u.email||'')+' &middot; '+(u.projects||0)+' projects &middot; '+(u.actions||0)+' actions &middot; '+esc(u.created_at||'')+'</div></div>'+
        '<div class="proj-actions">'+
        '<button class="btn ghost sm" data-plan="pro" data-uid="'+u.id+'">Make Pro</button>'+
        '<button class="btn ghost sm" data-plan="free" data-uid="'+u.id+'">Make Free</button>'+
        '<button class="btn ghost sm" data-del="'+u.id+'" data-login="'+esc(u.login||'')+'" style="color:#b91c1c;border-color:rgba(185,28,28,.3)">Delete</button></div></div>';
    });
    box.innerHTML = h;
    box.querySelectorAll('[data-plan]').forEach(function(b){
      b.addEventListener('click', function(){
        var target = b.dataset.plan;
        b.disabled = true; b.textContent = 'Saving...';
        fetch('/api/admin/set-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:+b.dataset.uid, plan:target})})
          .then(function(r){return r.json();}).then(function(j){
            if(j && j.ok){ toast('@'+b.dataset.uid+' set to ' + target.toUpperCase()); loadUsers(); loadStats(); }
            else { toast('Failed to update plan', true); b.disabled=false; }
          })
          .catch(function(){ toast('Failed to update plan', true); b.disabled=false; });
      });
    });
    box.querySelectorAll('[data-del]').forEach(function(b){
      b.addEventListener('click', function(){
        if(!confirm('Delete user @' + b.dataset.login + ' and all their projects? This cannot be undone.')) return;
        fetch('/api/admin/users/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:+b.dataset.del})})
          .then(function(r){return r.json();}).then(function(){ loadUsers(); loadStats(); });
      });
    });
  }

  var nuBtn = $('nuBtn');
  if(nuBtn) nuBtn.addEventListener('click', function(){
    var login = $('nuLogin').value.trim();
    if(!login){ return; }
    nuBtn.disabled = true; var st=$('nuStatus'); st.className='status'; st.textContent='Creating...';
    fetch('/api/admin/users/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:login, name:$('nuName').value.trim(), email:$('nuEmail').value.trim(), password:($('nuPass')?$('nuPass').value:'')})})
      .then(function(r){ return r.json().then(function(j){ return {ok:r.ok,j:j}; }); })
      .then(function(res){
        nuBtn.disabled = false;
        if(res.ok){ st.className='status'; st.textContent='Created @'+res.j.login; $('nuLogin').value=''; $('nuName').value=''; $('nuEmail').value=''; loadUsers(); loadStats(); }
        else { st.className='status err'; st.textContent=(res.j&&res.j.detail)||'Create failed.'; }
      })
      .catch(function(){ nuBtn.disabled=false; st.className='status err'; st.textContent='Failed.'; });
  });
  function loadUsers(){
    fetch('/api/admin/users').then(function(r){return r.json();}).then(function(list){
      allUsers = list && !list.detail ? list : [];
      renderUsers(allUsers);
    }).catch(function(){});
  }
  var us=$('userSearch');
  if(us) us.addEventListener('input', function(){
    var q = us.value.trim().toLowerCase();
    if(!q){ renderUsers(allUsers); return; }
    renderUsers(allUsers.filter(function(u){ return (u.login||'').toLowerCase().indexOf(q)>=0 || (u.email||'').toLowerCase().indexOf(q)>=0 || (u.name||'').toLowerCase().indexOf(q)>=0; }));
  });

  function loadOrders(){
    fetch('/api/admin/orders').then(function(r){return r.json();}).then(function(list){
      var box = $('orderList'); if(!box) return;
      if(!list || list.detail || !list.length){ box.innerHTML='<p style="color:#8a8880">No orders yet.</p>'; return; }
      var h='';
      list.forEach(function(o){
        var col = o.status==='paid' ? 'var(--green)' : (o.status==='pending' ? 'var(--orange)' : '#8a8880');
        h += '<div class="proj-row"><div>'+
          '<div class="proj-name">'+esc(o.id)+' <span style="color:'+col+';font-weight:600;font-size:.82rem">'+esc(o.status)+'</span></div>'+
          '<div class="proj-meta">@'+esc(o.login||'-')+' &middot; '+money(o.amount)+' &middot; '+esc(o.method||'')+' &middot; '+esc(o.created_at||'')+'</div></div></div>';
      });
      box.innerHTML = h;
    }).catch(function(){});
  }

  // auto-refresh overview every 30s
  setInterval(function(){ if(!$('app').hidden){ loadStats(); loadSeries(); loadRecent(); } }, 30000);
})();
