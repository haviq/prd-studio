(function(){
  var $ = function(id){ return document.getElementById(id); };
  function esc(s){ return (s==null?'':String(s)).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function money(n){ return 'Rp ' + (n||0).toLocaleString('id-ID'); }

  fetch('/api/admin/whoami').then(function(r){return r.json();}).then(function(w){
    $('loading').hidden = true;
    if(!w || !w.admin){ $('denied').hidden = false; return; }
    $('content').hidden = false;
    $('who').textContent = 'Signed in as @' + (w.login||'');
    loadStats(); loadUsers(); loadOrders();
  }).catch(function(){ $('loading').hidden = true; $('denied').hidden = false; });

  document.querySelectorAll('#tabs .tab').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('#tabs .tab').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      $('users').hidden = b.dataset.v !== 'users';
      $('orders').hidden = b.dataset.v !== 'orders';
    });
  });

  function loadStats(){
    fetch('/api/admin/stats').then(function(r){return r.json();}).then(function(s){
      if(s.detail){ return; }
      $('stats').innerHTML =
        '<div class="stat"><div class="n">' + (s.users||0) + '</div><div class="l">Users</div></div>' +
        '<div class="stat"><div class="n">' + (s.pro||0) + '</div><div class="l">Pro</div></div>' +
        '<div class="stat"><div class="n">' + (s.generates||0) + '</div><div class="l">PRDs</div></div>' +
        '<div class="stat"><div class="n">' + (s.projects||0) + '</div><div class="l">Projects</div></div>' +
        '<div class="stat"><div class="n">' + (s.paid_orders||0) + '</div><div class="l">Paid orders</div></div>' +
        '<div class="stat"><div class="n" style="font-size:1.05rem">' + money(s.revenue) + '</div><div class="l">Revenue</div></div>' +
        '<div class="stat"><div class="n">' + (s.pending_orders||0) + '</div><div class="l">Pending</div></div>' +
        '<div class="stat"><div class="n">' + (s.shared||0) + '</div><div class="l">Shared</div></div>';
    }).catch(function(){});
  }

  function loadUsers(){
    fetch('/api/admin/users').then(function(r){return r.json();}).then(function(list){
      if(!list || list.detail){ $('userList').innerHTML = '<p style="color:#8a8880">No access.</p>'; return; }
      if(!list.length){ $('userList').innerHTML = '<p style="color:#8a8880">No users yet.</p>'; return; }
      var h = '';
      list.forEach(function(u){
        h += '<div class="proj-row"><div>' +
          '<div class="proj-name">' + esc(u.name||u.login||('user '+u.id)) + ' <span class="plan-badge ' + (u.plan==='pro'?'pro':'free') + '">' + (u.plan||'free') + '</span></div>' +
          '<div class="proj-meta">@' + esc(u.login||'') + ' &middot; ' + esc(u.email||'') + ' &middot; ' + (u.projects||0) + ' projects &middot; ' + (u.actions||0) + ' actions &middot; ' + esc(u.created_at||'') + '</div></div>' +
          '<div class="proj-actions">' +
          '<button class="btn ghost sm" data-plan="pro" data-uid="' + u.id + '">Make Pro</button>' +
          '<button class="btn ghost sm" data-plan="free" data-uid="' + u.id + '">Make Free</button></div></div>';
      });
      $('userList').innerHTML = h;
      $('userList').querySelectorAll('[data-plan]').forEach(function(b){
        b.addEventListener('click', function(){
          fetch('/api/admin/set-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:+b.dataset.uid, plan:b.dataset.plan})})
            .then(function(r){return r.json();}).then(function(){ loadUsers(); loadStats(); });
        });
      });
    }).catch(function(){ $('userList').innerHTML = '<p style="color:#8a8880">Failed to load.</p>'; });
  }

  function loadOrders(){
    fetch('/api/admin/orders').then(function(r){return r.json();}).then(function(list){
      if(!list || list.detail){ $('orderList').innerHTML = '<p style="color:#8a8880">No access.</p>'; return; }
      if(!list.length){ $('orderList').innerHTML = '<p style="color:#8a8880">No orders yet.</p>'; return; }
      var h = '';
      list.forEach(function(o){
        var col = o.status==='paid' ? 'var(--green)' : (o.status==='pending' ? 'var(--orange)' : '#8a8880');
        h += '<div class="proj-row"><div>' +
          '<div class="proj-name">' + esc(o.id) + ' <span style="color:' + col + ';font-weight:600;font-size:.82rem">' + esc(o.status) + '</span></div>' +
          '<div class="proj-meta">@' + esc(o.login||'-') + ' &middot; ' + money(o.amount) + ' &middot; ' + esc(o.method||'') + ' &middot; ' + esc(o.created_at||'') + '</div></div></div>';
      });
      $('orderList').innerHTML = h;
    }).catch(function(){ $('orderList').innerHTML = '<p style="color:#8a8880">Failed to load.</p>'; });
  }
})();
