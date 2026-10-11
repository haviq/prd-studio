(function(){
  // theme init (runs on every page)
  try{
    var saved = localStorage.getItem('prd_theme');
    if(saved === 'dark') document.documentElement.setAttribute('data-theme','dark');
  }catch(e){}
  function toggleTheme(){
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    if(dark){ document.documentElement.removeAttribute('data-theme'); }
    else { document.documentElement.setAttribute('data-theme','dark'); }
    try{ localStorage.setItem('prd_theme', dark ? 'light' : 'dark'); }catch(e){}
  }
  window.__prdToggleTheme = toggleTheme;

  // inject theme toggle into the nav bar
  window.__prdNavTools = function(){
    var host = document.querySelector('nav .inner') || document.querySelector('nav');
    if(!host) return null;
    var box = host.querySelector('.nav-tools');
    if(!box){ box = document.createElement('span'); box.className = 'nav-tools'; host.appendChild(box); }
    return box;
  };
  function injectToggle(){
    if(document.getElementById('themeBtn')) return;
    var box = window.__prdNavTools();
    if(!box) return;
    var b = document.createElement('button');
    b.id = 'themeBtn'; b.className = 'theme-btn'; b.type = 'button';
    b.title = 'Toggle theme'; b.setAttribute('aria-label','Toggle theme');
    b.innerHTML = '\u25d1';
    b.addEventListener('click', toggleTheme);
    box.appendChild(b);
  }
  if(document.body){ injectToggle(); } else { document.addEventListener('DOMContentLoaded', injectToggle); }

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
