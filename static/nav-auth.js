(function(){
  var el = document.getElementById('navAuth');
  if(!el) return;
  function render(me){
    if(me && me.logged_in){
      var img = me.avatar ? '<img src="'+me.avatar+'" width="26" height="26" alt="" style="border-radius:50%;border:1px solid var(--lightgray)">' : '';
      el.innerHTML = '<a href="/account" class="nav-user">' + img + '<span>@' + me.login + '</span></a>';
    } else {
      el.innerHTML = '<a class="btn primary sm" href="/auth/github">Sign in with GitHub</a>';
    }
  }
  fetch('/api/me').then(function(r){return r.json();}).then(render).catch(function(){ render(null); });
})();
