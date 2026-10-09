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
          '<button class="btn ghost sm" data-open="' + p.id + '">Open</button>' +
          '<button class="btn ghost sm" data-del="' + p.id + '">Delete</button></div></div>';
      });
      box.innerHTML = html;
      box.querySelectorAll('[data-open]').forEach(function(b){
        b.addEventListener('click', function(){ location.href = '/studio?project=' + b.dataset.open; });
      });
      box.querySelectorAll('[data-del]').forEach(function(b){
        b.addEventListener('click', function(){
          if(!confirm('Delete this project?')) return;
          fetch('/api/projects/' + b.dataset.del, {method:'DELETE'}).then(function(){ b.closest('.proj-row').remove(); });
        });
      });
    });
  }).catch(function(){ $('loading').hidden = true; $('anon').hidden = false; });

  var lo = $('logoutBtn');
  if(lo) lo.addEventListener('click', function(){ fetch('/auth/logout',{method:'POST'}).then(function(){ location.href='/'; }); });
})();