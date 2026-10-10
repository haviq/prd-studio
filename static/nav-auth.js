(function(){
  var el = document.getElementById('navAuth');
  if(!el) return;
  function render(me){
    if(me && me.logged_in){
      var img = me.avatar ? '<img src="'+me.avatar+'" width="26" height="26" alt="" style="border-radius:50%;border:1px solid var(--lightgray)">' : '';
      var plan = me.plan || 'free';
      var upgrade = (plan === 'pro')
        ? '<span class="plan-pill pro">Pro</span>'
        : '<a class="plan-pill free" href="/pricing">Upgrade</a>';
      el.innerHTML = '<span class="nav-actions">' + upgrade + '<a href="/account" class="nav-user">' + img + '<span>@' + me.login + '</span></a></span>';
    } else {
      el.innerHTML = '<span class="nav-actions"><a class="nav-signin" href="/login">Sign in</a><a class="btn primary sm" href="/studio">Try free</a></span>';
    }
  }
  fetch('/api/me').then(function(r){return r.json();}).then(render).catch(function(){ render(null); });
})();
