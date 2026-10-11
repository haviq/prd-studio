(function(){
  var $ = function(id){ return document.getElementById(id); };
  function esc(s){ return (s==null?'':String(s)).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  fetch('/api/gallery').then(function(r){return r.json();}).then(function(list){
    var g = $('grid');
    if(!list || !list.length){ $('empty').hidden = false; return; }
    var h = '';
    list.forEach(function(p){
      h += '<div class="ex">' +
        '<div class="ex-tag">' + esc(p.template||'PRD') + '</div>' +
        '<h3>' + esc(p.name||'Untitled') + '</h3>' +
        '<p class="ex-input">@' + esc(p.login||'anon') + ' &middot; ' + (p.views||0) + ' views</p>' +
        '<a class="ex-link" href="/p/' + esc(p.share_id) + '/' + esc(p.lang||'en') + '">Open PRD &rarr;</a></div>';
    });
    g.innerHTML = h;
  }).catch(function(){ $('empty').hidden = false; });
})();
