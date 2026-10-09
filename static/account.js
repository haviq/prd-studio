(function(){
  var $ = function(id){ return document.getElementById(id); };

  function badge(plan){
    if(plan === 'pro') return '<span class="plan-badge pro">Pro</span>';
    return '<span class="plan-badge free">Free</span>';
  }

  fetch('/api/me').then(function(r){return r.json();}).then(function(me){
    $('loading').hidden = true;
    if(!me.logged_in){ $('anon').hidden = false; return; }
    $('content').hidden = false;
    $('name').textContent = me.name || me.login;
    $('handle').textContent = '@' + me.login;
    $('email').textContent = me.email || '';
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

    return fetch('/api/projects').then(function(r){return r.json();}).then(function(list){
      var box = $('projects');
      if(!list || !list.length){ box.innerHTML = '<p style="color:#8a8880">No saved projects yet. Generate a PRD in the studio and click Save.</p>'; return; }
      var html = '';
      list.forEach(function(p){
        html += '<div class="proj-row">' +
          '<div><div class="proj-name">' + (p.name||'Untitled').replace(/</g,'&lt;') + '</div>' +
          '<div class="proj-meta">' + (p.template||'') + ' &middot; ' + (p.created_at||'') + '</div></div>' +
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
